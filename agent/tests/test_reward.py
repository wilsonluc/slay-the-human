"""Tests for reward.py on hand-worked values. Run: python -m unittest discover -s agent/tests -t ."""

import unittest
from unittest import mock

from agent.env import reward


def state(floor=1, hp=80, max_hp=80, combats_won=0, elites=0, bosses=0, enemies=None):
    result = {"run": {"floor": floor, "hp": hp, "max_hp": max_hp, "combats_won": combats_won, "elites_killed": elites,
                      "bosses_killed": bosses}}
    if enemies is not None:
        result["combat"] = {"enemies": [{"combat_id": i, "hp": h, "max_hp": m, "alive": h > 0} for i, h, m in enemies]}
    return result


class ScoresTest(unittest.TestCase):
    def test_hand_worked_scores(self):
        scores = reward.Scores()(state(floor=12, hp=40, max_hp=80, combats_won=6, elites=2, bosses=1))
        self.assertEqual(scores, {"floor": 12 / 48, "hp": 0.5, "combat": 6 / 48, "kills": 3 / 48})

    def test_combat_fraction_counts_every_enemy_seen(self):
        scores = reward.Scores()
        self.assertEqual(scores(state(enemies=[(1, 10, 20)]))["combat"], 0.5 / 48)
        # A summon adds its HP: 10 of 40 removed. The score falls, as it should when the fight gets bigger.
        self.assertEqual(scores(state(enemies=[(1, 10, 20), (2, 20, 20)]))["combat"], 0.25 / 48)
        # The first enemy dies and leaves the list; it still counts, as fully removed only once it is seen dead.
        self.assertEqual(scores(state(enemies=[(1, 0, 20), (2, 20, 20)]))["combat"], 0.5 / 48)
        self.assertEqual(scores(state(enemies=[(2, 20, 20)]))["combat"], 0.5 / 48)

    def test_winning_a_fight_never_lowers_the_combat_score(self):
        scores = reward.Scores()
        during = scores(state(combats_won=2, enemies=[(1, 1, 30)]))["combat"]
        after = scores(state(combats_won=3))["combat"]
        self.assertGreater(after, during)
        self.assertEqual(after, 3 / 48)
        # The next combat starts from nothing removed.
        self.assertEqual(scores(state(combats_won=3, enemies=[(5, 30, 30)]))["combat"], 3 / 48)


class ShapingTest(unittest.TestCase):
    def test_hand_worked_step(self):
        before = {"floor": 0.1, "hp": 1.0, "combat": 0.0, "kills": 0.0}
        after = {"floor": 0.2, "hp": 0.5, "combat": 0.0, "kills": 0.0}
        parts = reward.shaping(before, after, gamma=0.5)
        self.assertAlmostEqual(parts["floor"], 0.25 * (0.5 * 0.2 - 0.1))
        self.assertAlmostEqual(parts["hp"], 0.25 * (0.5 * 0.5 - 1.0))
        self.assertEqual(parts["combat"], 0.0)

    def test_terminated_run_telescopes_to_minus_the_first_scores(self):
        gamma = 0.9
        path = [{"floor": f / 48, "hp": h, "combat": c / 48, "kills": 0.0}
                for f, h, c in [(1, 1.0, 0), (2, 0.8, 1), (3, 0.6, 1.5), (4, 0.3, 3)]]
        path.append(reward.zero())
        report = reward.RunReport(gamma, path[0])
        for before, after in zip(path, path[1:]):
            report.add(before, after, terminated=after is path[-1])
        for term, weight in reward.WEIGHTS.items():
            self.assertAlmostEqual(report.contribution[term], -weight * path[0][term])
        self.assertEqual(report.final, path[-2], "the scores just before the end, not the zeros after it")
        self.assertEqual(report.highest["floor"], 4 / 48)

    def test_truncated_run_keeps_its_scores(self):
        report = reward.RunReport(0.99, {"floor": 0.1, "hp": 1.0, "combat": 0.0, "kills": 0.0})
        after = {"floor": 0.2, "hp": 1.0, "combat": 0.0, "kills": 0.0}
        report.add({"floor": 0.1, "hp": 1.0, "combat": 0.0, "kills": 0.0}, after, terminated=False)
        self.assertEqual(report.final, after)

    def test_outcome(self):
        self.assertEqual((reward.outcome("win"), reward.outcome("loss"), reward.outcome(None)), (1.0, -1.0, 0.0))

    def test_weighted_scores_stay_within_one(self):
        self.assertLessEqual(sum(reward.WEIGHTS.values()), 1.0)

    def test_definition_hash_follows_the_definition(self):
        base = reward.definition_hash()
        for name, changed in [("WEIGHTS", {**reward.WEIGHTS, "hp": 0.5}), ("OUTCOMES", {"win": 2.0, "loss": -1.0}),
                              ("FULL_RUN", 49), ("REWARD_REVISION", reward.REWARD_REVISION + 1)]:
            with mock.patch.object(reward, name, changed):
                self.assertNotEqual(reward.definition_hash(), base, name)


if __name__ == "__main__":
    unittest.main()
