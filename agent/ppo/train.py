"""Trains a PPO policy on several games at once.

    python -m agent.ppo.train [--games 4] [--total-steps 10000000] [...]   a new training run in runs/<training run>/
    python -m agent.ppo.train --resume runs/<training run>                   continue it from its latest checkpoint

Each update: collect a rollout from every game, compute advantages, run the clipped PPO update, and write a row to
metrics.csv. A checkpoint is saved every checkpoint_every updates and whenever training stops: at the step budget, when
too many recent runs failed (the failure budget), on an interrupt, or on an error.
"""

import collections
import copy
import logging
import random
import sys
import time

import numpy as np
import torch

from agent.checkpoint import TrainingRun, identities
from agent.env import encoding, reward
from agent.env.environment import make_environments
from agent.env.vocabulary import Vocabulary
from agent.ppo.buffer import Buffer
from agent.ppo.config import Config, parse
from agent.ppo.model import Policy, as_tensors, masked
from agent.ppo.rollout import Collector

log = logging.getLogger(__name__)


class FailureBudget(Exception):
    """Too many of the most recent runs failed."""


def update(policy: Policy, optimizer: torch.optim.Optimizer, buffer: Buffer, config: Config,
           rng: np.random.Generator, kinds: dict[int, str]) -> dict:
    """One PPO update over the rollout. The learner's metrics come from the first epoch."""
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
            loss = policy_loss + config.value_coef * value_loss - config.entropy_coef * entropy.mean()
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), config.max_grad_norm)
            optimizer.step()

            if epoch == 0:
                with torch.no_grad():
                    stats["approx_kl"].append(float(((ratio - 1) - log_ratio).mean()))
                    stats["clip_fraction"].append(float(((ratio - 1).abs() > config.clip).float().mean()))
                    stats["policy_loss"].append(float(policy_loss))
                    stats["value_loss"].append(float(value_loss))
                    stats["entropy"].append(float(entropy.mean()))
                    for kind, value_ in zip(batch["kind"], entropy.tolist()):
                        entropy_of[kinds.get(int(kind), "other")].append(value_)
    returns, values = buffer.returns.ravel(), buffer.value.ravel()
    variance = np.var(returns)
    metrics = {name: float(np.mean(values_)) for name, values_ in stats.items()}
    metrics["explained_variance"] = float(1 - np.var(returns - values) / variance) if variance > 0 else 0.0
    for kind in encoding.KINDS:
        metrics[f"entropy_{kind}"] = float(np.mean(entropy_of[kind])) if entropy_of[kind] else ""
    return metrics


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
        "legal_actions": float(buffer.mask.sum(-1).mean()),
        "failed_runs": sum(failed(run) for run in ended),
    }
    for term in reward.WEIGHTS:
        metrics[f"contribution_{term}"] = mean([run["run"]["contribution"][term] for run in finished if run["run"]])
    return metrics


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
        self.collector = Collector(envs, self.policy, config.seed, config.device)
        self.buffer = Buffer(config.steps, len(envs))
        self.kinds = {vocabulary.index("KIND", kind): kind for kind in encoding.KINDS}
        self.updates = self.steps = 0
        # The most recent runs: a failed run's outcome, else None.
        self.window: collections.deque = collections.deque(maxlen=config.failure_window)
        self._snapshot: dict | None = None

    # Checkpoints

    def state(self) -> dict:
        return {
            "model": self.policy.state_dict(), "optimizer": self.optimizer.state_dict(),
            "updates": self.updates, "steps": self.steps,
            "torch_rng": torch.get_rng_state(), "sampling_rng": [g.get_state() for g in self.collector.generators],
            "minibatch_rng": self.rng.bit_generator.state, "game_seed_rng": [env.rng_state() for env in self.envs],
            "window": list(self.window), "vocabulary_keys": list(self.vocabulary.keys),
            "identities": identities(self.vocabulary),
        }

    def restore(self, state: dict) -> None:
        self.policy.load_state_dict(state["model"])
        self.optimizer.load_state_dict(state["optimizer"])
        self.updates, self.steps = state["updates"], state["steps"]
        torch.set_rng_state(state["torch_rng"])
        for generator, saved in zip(self.collector.generators, state["sampling_rng"]):
            generator.set_state(saved)
        self.rng.bit_generator.state = state["minibatch_rng"]
        for env, saved in zip(self.envs, state["game_seed_rng"]):
            env.set_rng_state(saved)
        self.window.extend(state["window"])
        self._snapshot = copy.deepcopy(self.state())

    # The loop

    def train(self) -> str:
        """Trains until the step budget; returns why it stopped. A checkpoint is saved whenever it stops, holding the
        last completed update."""
        if self._snapshot is None:
            self._snapshot = copy.deepcopy(self.state())
        try:
            while self.steps < self.config.total_steps:
                self._one_update()
                if self.updates % self.config.checkpoint_every == 0:
                    self.run.save(self._snapshot)
            reason = "step budget"
            log.info("stopping: reached %d steps (the step budget %d)", self.steps, self.config.total_steps)
        except BaseException as e:
            self.run.save(self._snapshot)
            log.error("stopping after update %d: %s: %s", self.updates, type(e).__name__, e)
            raise
        self.run.save(self._snapshot)
        return reason

    def _one_update(self) -> None:
        began = time.monotonic()
        ended, last_value = self.collector.collect(self.buffer)
        self.buffer.finish(last_value, self.config.gamma, self.config.lam)
        collected = time.monotonic()
        learner = update(self.policy, self.optimizer, self.buffer, self.config, self.rng, self.kinds)
        finished = time.monotonic()
        self.updates += 1
        self.steps += self.buffer.steps * self.buffer.games
        self.window.extend(run["outcome"] if failed(run) else None for run in ended)
        elapsed = finished - began
        row = {"update": self.updates, "step": self.steps, "time": round(time.time(), 1), **learner,
               "learning_rate": self.optimizer.param_groups[0]["lr"],
               "steps_per_second": self.buffer.steps * self.buffer.games / elapsed,
               "update_share": (finished - collected) / elapsed, **game_metrics(ended, self.buffer)}
        self.run.write_metrics(row)
        self._snapshot = copy.deepcopy(self.state())
        log.info("update %d: step %d, %.1f steps/s, %d runs ended, mean floor %s, failed %d", self.updates, self.steps,
                 row["steps_per_second"], row["runs"], row["mean_floor"], row["failed_runs"])
        failures = [outcome for outcome in self.window if outcome is not None]
        if len(failures) > self.config.failure_budget:
            reasons = collections.Counter(failures).most_common(3)
            raise FailureBudget(f"{len(failures)} of the last {len(self.window)} runs failed, past the budget of "
                                f"{self.config.failure_budget}; most common reasons: {reasons}")


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
