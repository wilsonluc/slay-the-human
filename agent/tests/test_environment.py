"""Tests for environment.py against the fake game. Run: python -m unittest discover -s agent/tests -t ."""

import json
import random
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import numpy as np

from agent.bridge import BridgeError
from agent.env import encoding, games, reward
from agent.env.environment import Environment, IllegalAction
from agent.env.vocabulary import VocabularyError

FAKE_GAME = Path(__file__).with_name("fake_game.py")
RECORDINGS = Path(__file__).with_name("recordings") / "decisions.jsonl"


def fake(mode: str = "normal", decisions: int = 0) -> list[str]:
    return [sys.executable, str(FAKE_GAME), "--mode", mode, "--decisions", str(decisions)]


def play(env: Environment, rng: random.Random, seed: str | None = None):
    """Plays one episode with random legal actions; returns the steps' (reward, terminated, truncated, info)."""
    obs, info = env.reset(seed=seed)
    steps = []
    while True:
        action = int(rng.choice(np.flatnonzero(env.action_masks())))
        obs, step_reward, terminated, truncated, info = env.step(action)
        steps.append((step_reward, terminated, truncated, info))
        if terminated or truncated:
            return steps


class EnvironmentTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.out = Path(self.dir.name)
        self.envs = []

    def tearDown(self):
        for env in self.envs:
            env.close()
        self.dir.cleanup()

    def env(self, mode="normal", decisions=0, **kwargs) -> Environment:
        env = Environment(self.out, game_command=fake(mode, decisions), hang_seconds=kwargs.pop("hang_seconds", 10),
                          **kwargs)
        self.envs.append(env)
        return env

    def test_gymnasium_shape(self):
        env = self.env()
        obs, info = env.reset(seed="abcio")
        self.assertEqual(info["seed"], "ABC10", "the seed as the game reads it")
        self.assertEqual(set(info), {"seed", "floor", "act", "kind", "outcome", "outcome_reward", "scores"})
        self.assertEqual(env.action_masks().shape, (encoding.ACTION_COUNT,))
        steps = play(env, random.Random(1))
        rewards, terminated, truncated, last = steps[-1]
        self.assertTrue(terminated and not truncated)
        self.assertEqual((last["outcome"], last["outcome_reward"]), ("loss", 0.0))  # a loss costs nothing of its own
        self.assertEqual(set(last["run"]), {"contribution", "highest", "final", "turns_per_combat", "card_rewards"})
        self.assertGreater(last["run"]["turns_per_combat"], 0, "the recordings include a combat")
        self.assertTrue(all(not t and not tr for _, t, tr, _ in steps[:-1]))

    def test_card_rewards_are_counted_once_per_rewards_screen(self):
        env = self.env()
        env.reset(seed="ABC")
        screen = lambda *types: {"kind": "reward", "actions": [], "state": {"reward": {"rewards": [
            {"type": t} for t in types]}}}
        pick = {"kind": "card_reward", "actions": [{"kind": "pick", "card": 0}, {"kind": "alternative"}]}
        combat = {"kind": "combat", "actions": []}
        # Two card rewards on one screen: the gold is taken (the screen comes back), one card picked, one left.
        for decision, answer in [(screen("gold", "card", "card"), 0), (screen("card", "card"), 0), (pick, 0),
                                 (screen("card"), 0), (combat, 0),
                                 (screen("card"), 0), (pick, 1), (screen("card"), 0), (combat, 0)]:
            env._count_cards(decision, answer)
        self.assertEqual(env._cards, {"offered": 3, "taken": 1})

    def test_a_new_seed_is_drawn_and_recorded(self):
        env = self.env()
        _, info = env.reset()
        self.assertEqual(len(info["seed"]), 10)

    def test_ten_runs_in_one_game_process(self):
        env = self.env(decisions=3)
        rng = random.Random(2)
        for _ in range(10):
            self.assertTrue(play(env, rng)[-1][1])
        self.assertEqual(env._launches, 1)

    def test_a_hang_is_truncated_logged_and_relaunched(self):
        env = self.env(mode="hang", hang_seconds=1)
        with self.assertLogs("agent.env.environment", "ERROR") as logs:
            steps = play(env, random.Random(3))
        _, terminated, truncated, info = steps[-1]
        self.assertTrue(truncated and not terminated)
        self.assertTrue(info["outcome"].startswith("failed"))
        self.assertIn("floor", logs.output[0])
        env.reset()
        self.assertEqual(env._launches, 2)

    def test_a_game_that_quits_is_truncated_with_its_reason(self):
        env = self.env(mode="exit")
        with self.assertLogs("agent.env.environment", "ERROR"):
            steps = play(env, random.Random(4))
        self.assertIn("told to quit", steps[-1][3]["outcome"])

    def test_a_run_autoslay_fails_is_named_by_its_line_not_as_a_crash(self):
        env = self.env(mode="autoslay")
        with self.assertLogs("agent.env.environment", "ERROR"):
            steps = play(env, random.Random(4))
        outcome = steps[-1][3]["outcome"]
        self.assertTrue(outcome.startswith("failed: AutoSlay failed the run: Cannot access a disposed object."), outcome)
        self.assertNotIn("closed the connection", outcome)
        self.assertNotIn("seed=", outcome, "the reason groups across seeds")

    def test_a_crash_keeps_its_error_output_and_names_its_exit_code(self):
        env = self.env(mode="crash")
        with self.assertLogs("agent.env.environment", "ERROR"):
            steps = play(env, random.Random(4))
        outcome = steps[-1][3]["outcome"]
        self.assertIn("the game closed the connection", outcome)
        self.assertIn("the game exited with code 0xe0434352", outcome)
        errors = games.error_file(env._log).read_text(encoding="utf-8")
        self.assertIn("the fake game crashed", errors)

    def test_training_never_plays_an_evaluation_seed(self):
        from agent.env.seeds import evaluation_seeds
        env = self.env()
        with self.assertRaises(ValueError):
            env.reset(seed=evaluation_seeds()[0])
        obs, info = env.reset(seed=evaluation_seeds()[0], options={"evaluation": True})
        self.assertEqual(info["seed"], evaluation_seeds()[0])

    def test_drawn_seeds_avoid_the_evaluation_seeds(self):
        from agent.env import environment as module
        env = self.env()
        # The seed the environment would draw next, made an evaluation seed.
        rng = random.Random()
        rng.setstate(env._rng.getstate())
        clash = "".join(rng.choice(module.SEED_CHARACTERS) for _ in range(10))
        with mock.patch.object(module, "EVALUATION_SEEDS", frozenset({clash})):
            self.assertNotEqual(env._draw_seed(), clash)

    def test_a_decision_too_big_for_the_observation_is_truncated_and_training_goes_on(self):
        env = self.env(mode="overflow")
        with self.assertLogs("agent.env.environment", "ERROR"):
            steps = play(env, random.Random(5))
        self.assertTrue(steps[-1][2])
        self.assertIn("does not fit the observation", steps[-1][3]["outcome"])
        env.reset()  # the next run starts a new game
        self.assertEqual(env._launches, 2)

    @unittest.skipUnless(sys.platform == "win32", "memory is read on Windows")
    def test_a_game_past_the_memory_limit_is_stopped(self):
        env = self.env(mode="memory", memory_limit_gb=0.2, hang_seconds=30)
        with self.assertLogs("agent.env.environment", "ERROR"):
            steps = play(env, random.Random(11))
        self.assertTrue(steps[-1][2])
        self.assertIn("past the 0.2 GB limit", steps[-1][3]["outcome"])
        self.assertGreater(env.peak_memory, 0.2 * 2**30, "the peak includes the reading past the limit")

    def test_an_illegal_action_raises_naming_it_and_relaunches(self):
        env = self.env()
        env.reset()
        illegal = int(np.flatnonzero(~env.action_masks())[0])
        with self.assertLogs("agent.env.environment", "ERROR"), self.assertRaisesRegex(IllegalAction, "mask does not allow"):
            env.step(illegal)
        self.assertTrue(list(self.out.glob("*.trace.jsonl")), "the failed run keeps its full trace")
        env.reset()
        self.assertEqual(env._launches, 2)

    def test_step_limit(self):
        env = self.env(step_cap=2)
        steps = play(env, random.Random(5))
        self.assertEqual(len(steps), 2)
        self.assertTrue(steps[-1][2])
        self.assertEqual(steps[-1][3]["outcome"], "step_limit")

    def test_every_step_carries_the_outcome_reward_and_scores_and_shaping_recomputes(self):
        gamma = 0.9
        env = self.env(gamma=gamma, trace_every=1)
        steps = play(env, random.Random(6))
        for step_reward, terminated, _, info in steps:
            self.assertEqual(set(info["scores"]), set(reward.WEIGHTS))
        trace = [json.loads(line) for line in next(self.out.glob("*.trace.jsonl")).read_text().splitlines()]
        rows = trace[:-1]
        scores = [row["scores"] for row in rows] + [reward.zero()]
        for i, (step_reward, terminated, _, info) in enumerate(steps):
            expected = sum(reward.terms(scores[i], scores[i + 1], gamma).values()) + info["outcome_reward"]
            if scores[i + 1] == scores[i] and not terminated:
                continue  # a pick within a selection
            self.assertAlmostEqual(step_reward, expected, places=5)
        other = sum(sum(reward.terms(a, b, 0.5).values()) for a, b in zip(scores, scores[1:]))
        self.assertIsInstance(other, float, "the same scores give the shaping for another discount")

    def test_records(self):
        env = self.env(trace_every=2, decisions=3)
        rng = random.Random(7)
        for _ in range(4):
            play(env, rng)
        summary = [json.loads(line) for line in (self.out / "summary.jsonl").read_text().splitlines()]
        self.assertEqual(len(summary), 4)
        self.assertEqual(set(summary[0]) >= {"seed", "outcome", "floor", "steps", "contribution", "highest", "final",
                                             "failure", "actions"}, True)
        self.assertEqual(len(list(self.out.glob("*.trace.jsonl"))), 2, "one in trace_every runs keeps a full trace")

    def test_a_summary_row_replays(self):
        env = self.env(decisions=4)
        first = play(env, random.Random(8))
        row = json.loads((self.out / "summary.jsonl").read_text().splitlines()[-1])
        env.reset(seed=row["seed"])
        for action in row["actions"]:
            result = env.step(action)
        self.assertEqual(result[4]["outcome"], first[-1][3]["outcome"])

    def test_multi_card_picks_in_any_order_are_sent_sorted(self):
        decisions = [json.loads(line) for line in RECORDINGS.read_text().splitlines() if line.strip()]
        index = next(i for i, d in enumerate(decisions)
                     if d["kind"] == "card_select" and d["state"]["card_select"]["max"] > 1)
        env = self.env(decisions=index + 1)
        env.reset()
        rng = random.Random(9)
        while env._decision["kind"] != "card_select" or env._decision["state"]["card_select"]["max"] <= 1:
            env.step(int(rng.choice(np.flatnonzero(env.action_masks()))))
        select = env._decision["state"]["card_select"]
        cards = len(select["cards"])
        first, second = cards - 1, 0
        mask = env.action_masks()
        self.assertTrue(mask[encoding.segment("card", first)])
        self.assertEqual(bool(mask[encoding.segment("confirm")]), select["min"] == 0)
        env.step(encoding.segment("card", first))
        self.assertFalse(env.action_masks()[encoding.segment("card", first)], "a picked card cannot be picked again")
        if select["max"] > 1 and second != first:
            result = env.step(encoding.segment("card", second))
            if not (result[2] or result[3]) and env._decision["kind"] == "card_select":
                env.step(encoding.segment("confirm"))
        # The fake game checks the picks arrive sorted and within the limits; a bad answer would fail the run.

    def test_refusals(self):
        with self.assertRaisesRegex(BridgeError, "protocol mismatch"):
            self.env(mode="version").reset()
        with self.assertRaisesRegex(VocabularyError, "the game is v0.0.0"):
            self.env(mode="game-version").reset()
        env = self.env(mode="unknown")
        with self.assertRaisesRegex(VocabularyError, "CARD.NOT_A_CARD"):
            play(env, random.Random(10))


if __name__ == "__main__":
    unittest.main()
