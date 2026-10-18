"""Trains a PPO policy on several games at once.

    python -m agent.ppo.train [--games 4] [--total-steps 10000000] [...]   a new training run in runs/<training run>/
    python -m agent.ppo.train --resume runs/<training run>                   continue it from its latest checkpoint

Each update: collect a rollout from every game, compute advantages, run the clipped PPO update, and write a row to
metrics.csv. A checkpoint is saved every checkpoint_every updates and whenever training stops: at the step budget, when
too many recent runs failed (the failure budget), on an interrupt, or on an error.

A file named stop in the training run's folder requests a stop that lets the games' runs finish: from the next update,
no game starts a new run, training goes on with the steps the runs in progress still play, and once every game is idle
it stops, with a checkpoint, and removes the file.
"""

import collections
import copy
import csv
import io
import json
import logging
import os
import random
import sys
import time

import numpy as np
import torch

from agent import evaluate
from agent.checkpoint import TrainingRun, identities
from agent.env.seeds import evaluation_seeds
from agent.env import encoding, reward
from agent.env.environment import make_environments
from agent.env.vocabulary import Vocabulary
from agent.ppo.buffer import Buffer
from agent.ppo.config import Config, parse
from agent.ppo.model import Policy, as_tensors, masked
from agent.ppo.rollout import Collector

STOP_FILE = "stop"

log = logging.getLogger(__name__)


class FailureBudget(Exception):
    """Too many of the most recent runs failed."""


def update(policy: Policy, optimizer: torch.optim.Optimizer, buffer: Buffer, config: Config,
           rng: np.random.Generator, kinds: dict[int, str]) -> dict:
    """One PPO update over the rollout. The losses and entropies come from the first epoch; approximate KL and the clip
    fraction from the last, so they measure how far the whole update moved the policy."""
    policy.train()
    stats = collections.defaultdict(list)
    entropy_of = collections.defaultdict(list)
    for epoch in range(config.epochs):
        for batch in buffer.minibatches(config.minibatch, rng):
            obs = as_tensors(batch["obs"], config.device)
            mask = torch.as_tensor(batch["mask"], device=config.device)
            action = torch.as_tensor(batch["action"], device=config.device)
            old_log_prob = torch.as_tensor(batch["log_prob"], device=config.device)
            advantage = torch.as_tensor(batch["advantage"], device=config.device)
            returns = torch.as_tensor(batch["returns"], device=config.device)
            if len(advantage) > 1:
                advantage = (advantage - advantage.mean()) / (advantage.std() + 1e-8)

            logits, value = policy(obs)
            distribution = torch.distributions.Categorical(logits=masked(logits, mask))
            log_prob, entropy = distribution.log_prob(action), distribution.entropy()
            log_ratio = log_prob - old_log_prob
            ratio = log_ratio.exp()
            policy_loss = -torch.min(ratio * advantage,
                                     ratio.clamp(1 - config.clip, 1 + config.clip) * advantage).mean()
            value_loss = 0.5 * ((value - returns) ** 2).mean()
            loss = policy_loss + config.value_coef * value_loss - config.entropy_coef * by_kind(entropy, batch["kind"])
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), config.max_grad_norm)
            optimizer.step()

            if epoch == config.epochs - 1:
                with torch.no_grad():
                    stats["approx_kl"].append(float(((ratio - 1) - log_ratio).mean()))
                    stats["clip_fraction"].append(float(((ratio - 1).abs() > config.clip).float().mean()))
            if epoch == 0:
                with torch.no_grad():
                    stats["policy_loss"].append(float(policy_loss))
                    stats["value_loss"].append(float(value_loss))
                    stats["entropy"].append(float(entropy.mean()))
                    for kind, value_ in zip(batch["kind"], entropy.tolist()):
                        entropy_of[kinds.get(int(kind), "other")].append(value_)
    returns, values = buffer.returns[buffer.filled], buffer.value[buffer.filled]
    variance = np.var(returns)
    metrics = {name: float(np.mean(values_)) for name, values_ in stats.items()}
    metrics["explained_variance"] = float(1 - np.var(returns - values) / variance) if variance > 0 else 0.0
    for kind in encoding.KINDS:
        metrics[f"entropy_{kind}"] = float(np.mean(entropy_of[kind])) if entropy_of[kind] else ""
    return metrics


def learning_rate(config: Config, steps: int) -> float:
    """Falls linearly with the steps taken, from the set learning rate at the start to zero at the step budget."""
    return config.lr * max(0.0, 1 - steps / config.total_steps)


def by_kind(values: torch.Tensor, kinds) -> torch.Tensor:
    """The mean of each decision kind's mean: every kind in the minibatch weighs the same, however many of its steps
    there are. Averaged over steps, the entropy bonus would go almost all to combat, and the rare decisions that build
    the deck (card rewards, rest sites, the map) would settle on one choice early and stop trying the others."""
    _, kind = torch.unique(torch.as_tensor(kinds, device=values.device), return_inverse=True)
    sums = torch.zeros(int(kind.max()) + 1, device=values.device, dtype=values.dtype).index_add(0, kind, values)
    return (sums / torch.bincount(kind)).mean()


def game_metrics(ended: list[dict], buffer: Buffer) -> dict:
    """The game's numbers over the runs that ended since the last row."""
    finished = [run for run in ended if run["seed"] is not None]
    mean = lambda values: float(np.mean(values)) if values else ""
    metrics = {
        "runs": len(ended),
        "win_rate": mean([run["outcome"] == "win" for run in finished]),
        "mean_floor": mean([run["floor"] for run in finished]),
        "mean_act": mean([run["act"] for run in finished]),
        "mean_steps_per_run": mean([run["steps"] for run in finished]),
        "mean_return": mean([run["return"] for run in finished]),
        "turns_per_combat": mean([run["run"]["turns_per_combat"] for run in finished
                                  if run["run"] and run["run"].get("turns_per_combat") is not None]),
        "legal_actions": float(buffer.mask[buffer.filled].sum(-1).mean()),
        "card_rewards_taken": share([run["run"]["card_rewards"] for run in finished if run["run"]]),
        "failed_runs": sum(failed(run) for run in ended),
    }
    for term in reward.WEIGHTS:
        metrics[f"contribution_{term}"] = mean([run["run"]["contribution"][term] for run in finished if run["run"]])
    return metrics


def share(counts: list[dict]) -> float | str:
    """Cards picked out of card rewards offered, over the runs."""
    offered = sum(count["offered"] for count in counts)
    return sum(count["taken"] for count in counts) / offered if offered else ""


# A game that exits mid-run closes the connection. The game's own crashes do (10 to 20 a day, in its garbage collector's
# finalizers, at no particular state); the game is relaunched, and these runs do not count against the failure budget.
CRASH = "the game closed the connection"


def failed(run: dict) -> bool:
    """A run that failed: the game stopped, hung or disconnected, or the run never started. The step limit is not a
    failure."""
    return str(run["outcome"]).startswith("failed")


class Trainer:
    def __init__(self, config: Config, run: TrainingRun, envs: list, vocabulary: Vocabulary) -> None:
        self.config, self.run, self.envs, self.vocabulary = config, run, envs, vocabulary
        torch.manual_seed(config.seed)
        self.policy = Policy(len(vocabulary), config.embed, config.hidden, config.state).to(config.device)
        self.optimizer = torch.optim.Adam(self.policy.parameters(), lr=config.lr, eps=1e-5)
        self.rng = np.random.default_rng(config.seed)
        # Collection runs one decision at a time, which is faster on the CPU (a GPU's per-call cost outweighs its
        # speed at batch size one), so with a GPU the update trains on it and the games play a CPU copy.
        self.player = self.policy if config.device == "cpu" else copy.deepcopy(self.policy).cpu()
        self.collector = Collector(envs, self.player, config.seed)
        self.buffer = Buffer(config.steps, len(envs))
        self.kinds = {vocabulary.index("KIND", kind): kind for kind in encoding.KINDS}
        self.updates = self.steps = 0
        self.evaluated = 0  # the step of the last generation
        # The most recent runs: a failed run's outcome, else None (a game crash too).
        self.window: collections.deque = collections.deque(maxlen=config.failure_window)
        self._snapshot: dict | None = None

    # Checkpoints

    def state(self) -> dict:
        return {
            "model": self.policy.state_dict(), "optimizer": self.optimizer.state_dict(),
            "parameter_names": [name for name, _ in self.policy.named_parameters()],
            "updates": self.updates, "steps": self.steps,
            "torch_rng": torch.get_rng_state(), "sampling_rng": [g.get_state() for g in self.collector.generators],
            "minibatch_rng": self.rng.bit_generator.state, "game_seed_rng": [env.rng_state() for env in self.envs],
            "evaluated": self.evaluated, "vocabulary_keys": list(self.vocabulary.keys),
            "identities": identities(self.vocabulary),
        }

    def restore(self, state: dict) -> None:
        self.policy.load_state_dict(state["model"])
        if self.player is not self.policy:
            self.player.load_state_dict(state["model"])
        self.optimizer.load_state_dict(state["optimizer"])
        self.updates, self.steps = state["updates"], state["steps"]
        torch.set_rng_state(state["torch_rng"])
        for generator, saved in zip(self.collector.generators, state["sampling_rng"]):
            generator.set_state(saved)
        self.rng.bit_generator.state = state["minibatch_rng"]
        for env, saved in zip(self.envs, state["game_seed_rng"]):
            env.set_rng_state(saved)
        # The window starts empty: resuming a run the failure budget stopped is the call that its failures are dealt with.
        self.evaluated = state.get("evaluated", 0)
        self._snapshot = copy.deepcopy(self.state())

    # The loop

    def train(self) -> str:
        """Trains until the step budget; returns why it stopped. A checkpoint is saved whenever it stops, holding the
        last completed update."""
        if self._snapshot is None:
            self._snapshot = copy.deepcopy(self.state())
        stop = self.run.folder / STOP_FILE
        try:
            while self.steps < self.config.total_steps:
                if stop.exists() and not self.collector.draining:
                    self.collector.draining = True
                    log.info("stop requested: no new runs; finishing %d runs in progress", self._in_progress())
                if self.collector.draining and self.collector.idle:
                    break
                self._one_update()
                if self.collector.draining:
                    log.info("draining: %d runs in progress", self._in_progress())
                elif self.steps // self.config.evaluate_every > self.evaluated // self.config.evaluate_every:
                    self._generation()
                if self.updates % self.config.checkpoint_every == 0:
                    self.run.save(self._snapshot)
            if self.collector.draining:
                reason = "stop requested"
                stop.unlink(missing_ok=True)
                log.info("stopping: requested, every game's run has finished")
            else:
                reason = "step budget"
                log.info("stopping: reached %d steps (the step budget %d)", self.steps, self.config.total_steps)
        except BaseException as e:
            self.run.save(self._snapshot)
            log.error("stopping after update %d: %s: %s", self.updates, type(e).__name__, e)
            raise
        self.run.save(self._snapshot)
        return reason

    def _in_progress(self) -> int:
        return sum(obs is not None for obs in self.collector.obs)

    def _one_update(self) -> None:
        began = time.monotonic()
        ended, last_value = self.collector.collect(self.buffer)
        self.buffer.finish(last_value, self.config.gamma, self.config.lam)
        collected = time.monotonic()
        for group in self.optimizer.param_groups:
            group["lr"] = learning_rate(self.config, self.steps)
        learner = update(self.policy, self.optimizer, self.buffer, self.config, self.rng, self.kinds)
        if self.player is not self.policy:
            self.player.load_state_dict(self.policy.state_dict())
        finished = time.monotonic()
        self.updates += 1
        filled = int(self.buffer.filled.sum())
        self.steps += filled
        self.window.extend(run["outcome"] if failed(run) and CRASH not in run["outcome"] else None for run in ended)
        elapsed = finished - began
        row = {"update": self.updates, "step": self.steps, "time": round(time.time(), 1), **learner,
               "learning_rate": self.optimizer.param_groups[0]["lr"],
               "steps_per_second": filled / elapsed,
               "update_share": (finished - collected) / elapsed, **game_metrics(ended, self.buffer)}
        self.run.write_metrics(row)
        self._snapshot = copy.deepcopy(self.state())
        log.info("update %d: step %d, %.1f steps/s, %d runs ended, mean floor %s, failed %d", self.updates, self.steps,
                 row["steps_per_second"], row["runs"], row["mean_floor"], row["failed_runs"])
        # Per game: seconds in the game's steps, in the policy, and waiting for the slowest game; the most memory it held.
        log.info("update %d timing: %s", self.updates, " ".join(
            f"{env.name}=game {t['game']:.0f}s/policy {t['policy']:.0f}s/waited {t['waited']:.0f}s"
            f"/peak {env.peak_memory / 2**30:.1f} GB"
            for env, t in zip(self.envs, self.collector.timing)))
        failures = [outcome for outcome in self.window if outcome is not None]
        if len(failures) > self.config.failure_budget:
            reasons = collections.Counter(failures).most_common(3)
            raise FailureBudget(f"{len(failures)} of the last {len(self.window)} runs failed, past the budget of "
                                f"{self.config.failure_budget}; most common reasons: {reasons}")


    def _generation(self) -> None:
        """Evaluates the policy on the evaluation seeds with its best action and keeps it as a generation. The games'
        runs in progress are ended (their next reset launches them again); collection then starts fresh runs."""
        began = time.monotonic()
        folder = self.run.folder / "generations"
        folder.mkdir(exist_ok=True)
        name = f"update-{self.updates}"
        about = {"checkpoint": str(folder / f"{name}.pt"), "training_run": self.run.folder.name,
                 "update": self.updates, "step": self.steps}
        result = evaluate.evaluate(self.envs, self.player, ["best"], self.vocabulary,
                                   evaluation_seeds()[:self.config.evaluation_seeds], about)
        self.collector.obs = [None] * len(self.envs)
        seconds = time.monotonic() - began
        self.run.save_to(self._snapshot, folder / f"{name}.pt")
        (folder / f"{name}.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        best = result["summary"]["best"]
        row = {"update": self.updates, "step": self.steps, "time": round(time.time(), 1),
               **{key: best[key] for key in ("mean_floor", "win_rate", "act1_boss", "act2_boss", "act3_boss",
                                             "runs", "failed", "valid")},
               "seconds": round(seconds, 1), "file": f"{name}.pt"}
        self._write_generation_row(row)
        self._prune_generations()
        self.evaluated = self.steps
        self._snapshot["evaluated"] = self.evaluated
        log.info("generation at update %d: mean floor %.2f, win rate %.3f, failed %d of %d%s, %.0f s",
                 self.updates, best["mean_floor"], best["win_rate"], best["failed"], best["runs"],
                 "" if best["valid"] else " (invalid)", seconds)

    def _write_generation_row(self, row: dict) -> None:
        path = self.run.folder / "generations.csv"
        line = io.StringIO()
        writer = csv.DictWriter(line, fieldnames=list(row), lineterminator="\n")
        if not path.exists():
            writer.writeheader()
        writer.writerow(row)
        with path.open("a", encoding="utf-8", newline="") as file:
            file.write(line.getvalue())
            file.flush()
            os.fsync(file.fileno())

    def _prune_generations(self) -> None:
        """Keeps the checkpoints of the best generation and the latest generations_kept; the rest lose their file
        (their row and result stay)."""
        with (self.run.folder / "generations.csv").open(encoding="utf-8") as file:
            rows = list(csv.DictReader(file))
        keep = {row["file"] for row in rows[-self.config.generations_kept:]}
        keep.add(max(rows, key=generation_key)["file"])
        for row in rows:
            path = self.run.folder / "generations" / row["file"]
            if row["file"] not in keep and path.exists():
                path.unlink()


def generation_key(row: dict) -> tuple:
    """Which generation is best: the highest win rate, then the highest mean floor (all that matters while no run
    wins). An invalid evaluation is never the best."""
    return (row["valid"] == "True" or row["valid"] is True, float(row["win_rate"]), float(row["mean_floor"]))


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stderr)
    config, resume = parse(argv)
    vocabulary = Vocabulary.load()
    if resume:
        run = TrainingRun(resume)
        config = Config(**run.record()["config"])
        state = run.load(vocabulary)
        run.trim_metrics(state["updates"])
        log.info("resuming %s from update %d (step %d)", run.folder, state["updates"], state["steps"])
    else:
        if config.seed is None:
            config.seed = random.SystemRandom().randrange(2**31)
        run = TrainingRun.create(config.as_dict(), vocabulary)
        state = None
        log.info("training run %s, seed %d", run.folder, config.seed)
    # The log also goes to the training run's folder, with the rest of its record.
    file_log = logging.FileHandler(run.folder / "train.log", encoding="utf-8")
    file_log.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logging.getLogger().addHandler(file_log)
    envs = make_environments(config.games, run.folder, seed=config.seed, character=config.character,
                             gamma=config.gamma, hang_seconds=config.hang_seconds, step_cap=config.step_cap,
                             trace_every=config.trace_every, time_scale=config.time_scale, vocabulary=vocabulary)
    trainer = Trainer(config, run, envs, vocabulary)
    try:
        if state is not None:
            trainer.restore(state)
        trainer.train()
    finally:
        trainer.collector.close()
        for env in envs:
            env.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
