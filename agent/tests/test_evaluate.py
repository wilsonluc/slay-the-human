"""Tests for evaluate.py and the evaluation seeds. Run: python -m unittest discover -s agent/tests -t ."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from agent import evaluate
from agent.checkpoint import TrainingRun
from agent.env.environment import SEED_CHARACTERS
from agent.env.seeds import evaluation_seeds, seeds_hash
from agent.env.vocabulary import Vocabulary
from agent.ppo.model import Policy, as_tensors, masked
from agent.ppo.train import Trainer
from agent.tests.fake_env import FakeEnvironment
from agent.tests.test_train import small

ROOT = Path(__file__).resolve().parents[2]
FAKE_GAME = Path(__file__).with_name("fake_game.py")


class SeedsTest(unittest.TestCase):
    def test_the_seed_set(self):
        seeds = evaluation_seeds()
        self.assertEqual(len(seeds), 200)
        self.assertEqual(len(set(seeds)), 200)
        self.assertTrue(all(len(s) == 10 and set(s) <= set(SEED_CHARACTERS) for s in seeds))
        self.assertEqual(seeds_hash(), seeds_hash(list(seeds)))
        self.assertNotEqual(seeds_hash(), seeds_hash(seeds[1:]))


class EvaluateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.manual_seed(0)
        cls.vocabulary = Vocabulary.load()
        cls.policy = Policy(len(cls.vocabulary), 8, 16, 32)
        cls.seeds = evaluation_seeds()[:6]

    def envs(self, count, **settings):
        return [FakeEnvironment(seed=100 + i, name=f"fake{i}", **settings) for i in range(count)]

    def test_best_action_is_the_masked_argmax(self):
        env = FakeEnvironment()
        obs, _ = env.reset(seed="ABC")
        mask = env.action_masks()
        with torch.no_grad():
            logits, _ = self.policy(as_tensors({k: v[None] for k, v in obs.items()}))
        want = int(torch.argmax(masked(logits, torch.as_tensor(mask)[None])[0]))
        self.assertEqual(evaluate.chooser(self.policy, "best")(obs, mask, np.random.default_rng(0)), want)
        self.assertTrue(mask[want])

    def test_result_fields_and_summary(self):
        result = evaluate.evaluate(self.envs(2), self.policy, ["best", "sampled"], self.vocabulary, self.seeds,
                                   {"checkpoint": "x"})
        for field in ("checkpoint", "seeds", "game_build", "git_commit", "vocabulary", "schema", "protocol", "reward",
                      "summary", "runs"):
            self.assertIn(field, result)
        self.assertEqual(len(result["runs"]), 12)
        self.assertEqual(set(result["runs"][0]), {"seed", "mode", "outcome", "floor", "act", "steps"})
        best = result["summary"]["best"]
        self.assertEqual(best["runs"], 6)
        self.assertAlmostEqual(best["mean_floor"], np.mean([r["floor"] for r in result["runs"] if r["mode"] == "best"]))
        self.assertTrue(best["valid"])

    def test_the_same_seeds_give_the_same_results_whatever_the_games(self):
        first = evaluate.play_all(self.envs(1), self.seeds, ["best", "sampled"], self.policy)
        second = evaluate.play_all(self.envs(3), self.seeds, ["best", "sampled"], self.policy)
        self.assertEqual(first, second)

    def test_the_random_agent(self):
        rows = evaluate.play_all(self.envs(2), self.seeds, ["random"], None)
        self.assertEqual([r["seed"] for r in rows], self.seeds)
        self.assertEqual(rows, evaluate.play_all(self.envs(1), self.seeds, ["random"], None))

    def test_failed_runs_are_counted_apart_and_too_many_make_it_invalid(self):
        rows = evaluate.play_all(self.envs(2, fail_every=1), self.seeds, ["best"], self.policy)
        summary = evaluate.summarize(rows)["best"]
        self.assertEqual(summary["failed"], 6)
        self.assertFalse(summary["valid"])
        rows[0]["outcome"] = rows[1]["outcome"] = "loss"
        rows[0]["floor"], rows[1]["floor"] = 4, 8
        summary = evaluate.summarize(rows)["best"]
        self.assertEqual((summary["failed"], summary["mean_floor"]), (4, 6.0))

    def test_a_checkpoint_loads_for_evaluation(self):
        root = Path(tempfile.mkdtemp())
        config = small(total_steps=200)
        run = TrainingRun.create(config.as_dict(), self.vocabulary, root=root)
        Trainer(config, run, self.envs(2), self.vocabulary).train()
        policy, about = evaluate.load_policy(run.checkpoint_file, self.vocabulary)
        self.assertEqual((about["training_run"], about["update"]), (run.folder.name, 1))
        self.assertEqual(policy.embedding.weight.shape[1], config.embed)

    def test_the_command_runs_on_the_fake_game(self):
        before = set((ROOT / "runs").glob("eval-*")) if (ROOT / "runs").exists() else set()
        command = f'"{sys.executable}" "{FAKE_GAME}" --decisions 3'
        done = subprocess.run([sys.executable, "-m", "agent.evaluate", "random", "--games", "1", "--seeds", "2",
                               "--game-command", command], cwd=ROOT, capture_output=True, text=True, timeout=300)
        made = set((ROOT / "runs").glob("eval-*")) - before
        try:
            self.assertEqual(done.returncode, 0, done.stderr[-2000:])
            (folder,) = made
            result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["summary"]["random"]["runs"], 2)
            self.assertEqual(len(list(folder.glob("*.trace.jsonl"))), 2, "every evaluation run keeps its trace")
        finally:
            for folder in made:
                shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
