"""Tests for the PPO trainer on the fake environment. Run: python -m unittest discover -s agent/tests -t ."""

import csv
import tempfile
import unittest
from pathlib import Path

import torch

from agent.checkpoint import TrainingRun
from agent.env.vocabulary import Vocabulary
from agent.ppo.config import Config, parse
from agent.ppo.train import STOP_FILE, FailureBudget, Trainer, by_kind
from agent.tests.fake_env import FakeEnvironment

# Columns that depend on the machine's speed, not on the seed.
TIMING = {"time", "steps_per_second", "update_share"}


def small(**overrides) -> Config:
    """A config for tests: a small model, rollouts of one fake episode per game."""
    settings = dict(seed=1, games=2, steps=100, total_steps=400, checkpoint_every=1000, minibatch=100, embed=8,
                    hidden=16, state=32)
    settings.update(overrides)
    return Config(**settings)


def rows(run: TrainingRun) -> list[dict]:
    with run.metrics_file.open(encoding="utf-8") as file:
        return list(csv.DictReader(file))


def without_timing(row: dict) -> dict:
    return {key: value for key, value in row.items() if key not in TIMING}


class EntropyByKindTest(unittest.TestCase):
    def test_a_rare_kind_pulls_as_much_as_a_common_one(self):
        # 99 combat steps and one card reward: each kind's steps together get the same share of the bonus's gradient.
        entropy = torch.cat([torch.full((99,), 1.0), torch.zeros(1)]).requires_grad_()
        bonus = by_kind(entropy, [7] * 99 + [3])
        self.assertAlmostEqual(float(bonus), 0.5)
        bonus.backward()
        self.assertAlmostEqual(float(entropy.grad[:99].sum()), float(entropy.grad[99]))


class TrainerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vocabulary = Vocabulary.load()

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def trainer(self, config: Config, **env_settings) -> Trainer:
        run = TrainingRun.create(config.as_dict(), self.vocabulary, root=self.root / str(len(list(self.root.iterdir()))))
        envs = [FakeEnvironment(seed=i, name=f"fake{i}", **env_settings) for i in range(config.games)]
        return Trainer(config, run, envs, self.vocabulary)

    def test_one_update_changes_the_weights_and_writes_finite_metrics(self):
        trainer = self.trainer(small(total_steps=200))
        before = [p.detach().clone() for p in trainer.policy.parameters()]
        trainer.train()
        self.assertTrue(any(not torch.equal(a, b) for a, b in zip(before, trainer.policy.parameters())))
        (row,) = rows(trainer.run)
        for name in ("approx_kl", "clip_fraction", "entropy", "value_loss", "policy_loss", "explained_variance",
                     "steps_per_second", "update_share", "mean_return", "legal_actions", "entropy_event"):
            self.assertTrue(row[name] != "" and float(row[name]) == float(row[name]), name)
        self.assertEqual(row["runs"], "2")

    def test_the_same_seed_gives_the_same_metrics(self):
        first, second = self.trainer(small()), self.trainer(small())
        first.train()
        second.train()
        self.assertEqual([without_timing(r) for r in rows(first.run)], [without_timing(r) for r in rows(second.run)])

    def test_three_games(self):
        trainer = self.trainer(small(games=3, total_steps=300))
        trainer.train()
        self.assertEqual(rows(trainer.run)[0]["runs"], "3")

    def test_training_stops_at_the_step_budget_with_a_checkpoint(self):
        trainer = self.trainer(small(total_steps=400))
        self.assertEqual(trainer.train(), "step budget")
        self.assertEqual(len(rows(trainer.run)), 2)
        self.assertEqual(trainer.run.load(self.vocabulary)["updates"], 2)

    def test_training_stops_at_the_failure_budget_naming_the_reasons(self):
        trainer = self.trainer(small(failure_budget=2, total_steps=10_000), fail_every=1)
        with self.assertRaises(FailureBudget) as stopped:
            trainer.train()
        self.assertIn("past the budget of 2", str(stopped.exception))
        self.assertIn("told to fail", str(stopped.exception))
        # Each game's episodes fail halfway, so the first rollout already has 4 failures.
        self.assertEqual(trainer.run.load(self.vocabulary)["updates"], 1)

    def test_an_interrupt_saves_the_last_completed_update(self):
        trainer = self.trainer(small(total_steps=10_000))
        envs, steps = trainer.envs, [0]
        step = envs[0].step

        def interrupted(action):
            steps[0] += 1
            if steps[0] == 250:
                raise KeyboardInterrupt
            return step(action)

        envs[0].step = interrupted
        with self.assertRaises(KeyboardInterrupt):
            trainer.train()
        self.assertEqual(trainer.run.load(self.vocabulary)["updates"], 2)

    def test_a_requested_stop_lets_the_runs_in_progress_finish(self):
        # Rollouts of 60 steps, episodes of 100: the stop is requested during the first rollout, so the second plays
        # the last 40 steps of each run and starts none.
        trainer = self.trainer(small(steps=60, minibatch=60, total_steps=10_000))
        stop, step, calls = trainer.run.folder / STOP_FILE, trainer.envs[0].step, [0]

        def requesting(action):
            calls[0] += 1
            if calls[0] == 30:
                stop.touch()
            return step(action)

        trainer.envs[0].step = requesting
        self.assertEqual(trainer.train(), "stop requested")
        self.assertEqual([row["runs"] for row in rows(trainer.run)], ["0", "2"])
        self.assertEqual(trainer.steps, 2 * 60 + 2 * 40)
        self.assertEqual([env._episodes for env in trainer.envs], [1, 1])
        self.assertFalse(stop.exists(), "the request is used up")
        self.assertEqual(trainer.run.load(self.vocabulary)["updates"], 2)

    def test_the_step_limit_is_not_a_failure(self):
        trainer = self.trainer(small(failure_budget=0, total_steps=400), truncate_at=50)
        trainer.train()
        self.assertEqual(rows(trainer.run)[-1]["failed_runs"], "0")

    def test_generations_are_evaluated_kept_and_pruned(self):
        trainer = self.trainer(small(total_steps=800, evaluate_every=200, evaluation_seeds=2, generations_kept=1))
        trainer.train()
        folder = trainer.run.folder
        with (folder / "generations.csv").open(encoding="utf-8") as file:
            generations = list(csv.DictReader(file))
        self.assertEqual([int(g["update"]) for g in generations], [1, 2, 3, 4])
        self.assertTrue(all(g["runs"] == "2" for g in generations))
        self.assertEqual(len(list((folder / "generations").glob("*.json"))), 4, "every result stays")
        kept = {p.name for p in (folder / "generations").glob("*.pt")}
        best = max(generations, key=lambda g: (g["valid"] == "True", float(g["win_rate"]), float(g["mean_floor"])))
        self.assertEqual(kept, {"update-4.pt", best["file"]})
        self.assertEqual(trainer.run.load(self.vocabulary)["evaluated"], 800)

    def test_every_setting_is_a_flag(self):
        config, resume = parse(["--gamma", "0.99", "--games", "8", "--seed", "3", "--resume", "runs/x"])
        self.assertEqual((config.gamma, config.games, config.seed, resume), (0.99, 8, 3, "runs/x"))

    def test_ppo_learns_a_reward_that_comes_at_the_end(self):
        """The reward only comes on an episode's last step, 10 to 100 steps after the choices that earn it. Random
        play averages 0; the best play gets 1."""
        trainer = self.trainer(small(games=4, lr=1e-3, total_steps=16_000, minibatch=200, embed=16, hidden=32,
                                     state=64))
        trainer.train()
        last = [float(row["mean_return"]) for row in rows(trainer.run)[-5:]]
        self.assertGreaterEqual(sum(last) / len(last), 0.8, last)


if __name__ == "__main__":
    unittest.main()
