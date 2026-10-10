"""The training environment: one game process, played a step at a time in the Gymnasium shape.

    obs, info = env.reset(seed=None)
    obs, reward, terminated, truncated, info = env.step(action)
    mask = env.action_masks()

The game plays runs back to back; each reset starts the next one. Only a win or a loss is terminated. A run that fails
(the game exits, the connection closes, or no decision comes within hang_seconds of an action) is truncated, logged as an
error, and the next reset launches the game again; so is a run that reaches step_cap steps. An action the mask does not
allow raises, naming it, and the episode ends as an error: nothing picks an action in its place.

Each run leaves a record in the run folder: a full trace (every decision, action, outcome reward and reward term score)
for evaluation runs, failed runs and one in trace_every training runs, else one row in summary.jsonl with the seed,
outcome, floor, steps, reward term results, failure reason and the action indices, which replay the run exactly.
"""

import json
import logging
import subprocess
import random
from pathlib import Path

import numpy as np

from agent.bridge import Bridge, BridgeError
from agent.env import games, reward
from agent.env.encoding import Encoder, describe
from agent.env.vocabulary import Vocabulary

SEED_CHARACTERS = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"

log = logging.getLogger(__name__)


class IllegalAction(Exception):
    """The learner chose an action the mask does not allow."""


def canonical_seed(seed: str) -> str:
    """A game seed as the game reads it: upper case, O as 0 and I as 1."""
    return seed.strip().upper().replace("O", "0").replace("I", "1")


class Environment:
    def __init__(self, out: Path, character: str = "IRONCLAD", seed: int = 0, gamma: float = 0.999,
                 hang_seconds: float = 120.0, step_cap: int = 5000, trace_every: int = 100, time_scale: float = 20,
                 game_command: list[str] | None = None, vocabulary: Vocabulary | None = None, name: str = "game") -> None:
        self.out, self.character, self.gamma = Path(out), character, gamma
        self.hang_seconds, self.step_cap, self.trace_every = hang_seconds, step_cap, trace_every
        self.time_scale, self.game_command, self.name = time_scale, game_command, name
        self.vocabulary = vocabulary or Vocabulary.load()
        self.encoder = Encoder(self.vocabulary)
        self.out.mkdir(parents=True, exist_ok=True)
        self._rng = random.Random(seed)
        self._bridge: Bridge | None = None
        self._game = None
        self._launches = 0
        self._in_run = False
        self._runs = 0
        self._largest: dict[str, int] = {}

    # Gymnasium shape

    def reset(self, seed: str | None = None, options: dict | None = None) -> tuple[dict, dict]:
        options = options or {}
        if self._in_run or self._game is None or self._game.poll() is not None:
            self._relaunch()
        self._runs += 1
        self._seed = canonical_seed(seed) if seed else "".join(self._rng.choice(SEED_CHARACTERS) for _ in range(10))
        self._evaluation = bool(options.get("evaluation"))
        self._trace: list[dict] = []
        self._actions: list[int] = []
        self._steps = 0
        self._failure: str | None = None
        self._scores_of = reward.Scores()
        try:
            self._bridge.start(self._seed, self.character, self.hang_seconds)
            message = self._bridge.next(self.hang_seconds)
        except (BridgeError, TimeoutError, OSError) as e:
            self._kill()
            raise BridgeError(f"{self.name}: the game did not start the run: {e or 'timed out'}") from e
        if message["type"] != "decision":
            raise BridgeError(f"{self.name}: the run ended before its first decision")
        self._in_run = True
        self._load(message)
        self._report = reward.RunReport(self.gamma, self._scores)
        return self._obs, self._info(None)

    def step(self, action: int) -> tuple[dict, float, bool, bool, dict]:
        if not self._in_run:
            raise RuntimeError("step() before reset()")
        action = int(action)
        if not (0 <= action < len(self._mask)) or not self._mask[action]:
            self._failure = f"illegal action {describe(action) if 0 <= action < len(self._mask) else action}"
            log.error("%s: the learner chose %s at a %s decision (floor %s, seed %s); the run ends as an error",
                      self.name, self._failure, self._decision["kind"], self._floor(), self._seed)
            self._kill()
            self._finish(self._failure)
            raise IllegalAction(f"{self.name}: {self._failure}, which the mask does not allow")
        self._steps += 1
        self._actions.append(action)
        before, decision = self._scores, self._decision
        answer = self._legal[action]
        message = None
        try:
            message = self._answer(answer)
        except (BridgeError, TimeoutError, OSError) as e:
            self._failure = f"failed: {self._game_error() or e or 'no decision within the hang time'}"
        self._record(decision, action, before)
        if self._failure:
            log.error("%s: run failed at a %s decision (floor %s, seed %s): %s; game log %s", self.name,
                      decision["kind"], self._floor(), self._seed, self._failure, self._log)
            self._kill()
            return self._end(before, terminated=False, outcome=self._failure, outcome_reward=0.0, step_reward=0.0)
        if message is not None and message["type"] == "run_end":
            outcome = message["outcome"]
            after = reward.zero()
            step_reward = reward.outcome(outcome) + sum(reward.shaping(before, after, self.gamma).values())
            self._report.add(before, after, terminated=True)
            self._scores = after
            self._in_run = False
            return self._end(before, terminated=True, outcome=outcome, outcome_reward=reward.outcome(outcome),
                             step_reward=step_reward, floor=message.get("floor"))
        if message is not None:
            self._load(message)
        step_reward = sum(reward.shaping(before, self._scores, self.gamma).values())
        self._report.add(before, self._scores, terminated=False)
        if self._steps >= self.step_cap:
            # The game's run is still going, so the next reset launches the game again.
            self._failure = "step_limit"
            return self._end(before, terminated=False, outcome="step_limit", outcome_reward=0.0,
                             step_reward=step_reward)
        return self._obs, step_reward, False, False, self._info(None)

    def action_masks(self) -> np.ndarray:
        return self._mask

    def close(self) -> None:
        """Quits the game: cleanly from the main menu, or by killing it mid-run."""
        if self._in_run or self._bridge is None:
            self._kill()
            return
        try:
            # Close only once the game waits at the main menu, so it quits instead of failing a write.
            self._bridge.wait_ready(self.hang_seconds)
            self._bridge.close()
            self._game.wait(timeout=self.hang_seconds)
        except (BridgeError, TimeoutError, OSError, subprocess.TimeoutExpired):
            pass
        self._kill()

    # The game

    def _relaunch(self) -> None:
        self._kill()
        self._launches += 1
        self._bridge = Bridge(accept_timeout=self.hang_seconds)
        self._log = self.out / f"{self.name}-{self._launches}.log"
        self._game = games.launch(self._bridge.port, self._log.resolve(), self.time_scale, self.game_command)
        hello = self._bridge.accept()
        self.vocabulary.check(hello)
        self._bridge.wait_ready(self.hang_seconds)
        log.info("%s: launched (%s), game %s", self.name, self._launches, hello.get("game_version"))
        self._in_run = False

    def _kill(self) -> None:
        if self._game is not None and self._game.poll() is None:
            self._game.kill()
            self._game.wait()
        if self._bridge is not None:
            try:
                self._bridge.close()
            except OSError:
                pass
        self._game = self._bridge = None
        self._in_run = False

    def _game_error(self) -> str | None:
        """The game log's own error line about the run, when there is one."""
        try:
            lines = self._log.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return None
        errors = [line for line in lines if "run error" in line or "RunFailed" in line]
        return errors[-1].strip() if errors else None

    def _answer(self, answer) -> dict | None:
        """Answers the decision. A pick within a card selection only marks the card, until the selection is sent."""
        if isinstance(answer, tuple):
            select = self._decision["state"]["card_select"]
            if answer[0] == "pick":
                self._picked = self._picked | {answer[1]}
                if len(self._picked) < select["max"]:
                    self._obs, self._mask = self.encoder.encode(self._decision, self._picked)
                    self._legal = self.encoder.actions(self._decision, self.encoder.living(self._decision), self._picked)
                    return None
            self._bridge.answer(self._decision, sorted(self._picked))
        else:
            self._bridge.answer(self._decision, answer)
        return self._bridge.next(self.hang_seconds)

    def _load(self, decision: dict) -> None:
        self._decision = decision
        self._picked: frozenset = frozenset()
        self._obs, self._mask = self.encoder.encode(decision)
        self._legal = self.encoder.actions(decision, self.encoder.living(decision))
        self._scores = self._scores_of(decision["state"])
        for name, size in self.encoder.largest.items():
            if size > self._largest.get(name, -1):
                self._largest[name] = size
                log.info("%s: largest %s so far: %d", self.name, name, size)

    def _floor(self):
        return self._decision["state"]["run"]["floor"]

    # Records

    def _record(self, decision: dict, action: int, before: dict) -> None:
        self._trace.append({"decision": decision, "action": action, "scores": before})

    def _end(self, before, terminated: bool, outcome: str, outcome_reward: float, step_reward: float,
             floor=None) -> tuple[dict, float, bool, bool, dict]:
        if self._trace:
            self._trace[-1]["outcome_reward"] = outcome_reward
        self._finish(outcome, floor)
        info = self._info(outcome, outcome_reward)
        info["run"] = self._report.as_dict()
        return self._obs, step_reward, terminated, not terminated, info

    def _finish(self, outcome: str, floor=None) -> None:
        """Writes the run's record: a full trace for evaluation runs, failed runs and one in trace_every training
        runs, and a summary row for every run."""
        record = {"seed": self._seed, "outcome": outcome, "floor": floor if floor is not None else self._floor(),
                  "steps": self._steps, **self._report.as_dict(), "failure": self._failure, "actions": self._actions}
        failed = self._failure is not None and self._failure != "step_limit"
        if self._evaluation or failed or self._runs % self.trace_every == 0:
            path = self.out / f"{self.name}-run-{self._runs}.trace.jsonl"
            with path.open("w", encoding="utf-8") as trace:
                for row in self._trace:
                    trace.write(json.dumps(row) + "\n")
                trace.write(json.dumps({"end": record}) + "\n")
        with (self.out / "summary.jsonl").open("a", encoding="utf-8") as summary:
            summary.write(json.dumps({"game": self.name, "run": self._runs, **record}) + "\n")

    def _info(self, outcome, outcome_reward: float = 0.0) -> dict:
        return {"seed": self._seed, "floor": self._floor(), "kind": self._decision["kind"], "outcome": outcome,
                "outcome_reward": outcome_reward, "scores": dict(self._scores)}


def make_environments(count: int, out: Path, seed: int = 0, **kwargs) -> list[Environment]:
    """count environments, each with its own game, launched one after another: each game reaches its main menu before
    the next starts, so start-ups never pile up."""
    environments = []
    try:
        for i in range(count):
            environment = Environment(out, seed=seed * 1000 + i, name=f"game{i}", **kwargs)
            environment._relaunch()
            environments.append(environment)
    except BaseException:
        for environment in environments:
            environment.close()
        raise
    return environments
