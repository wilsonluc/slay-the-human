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


GAMMA = 0.999


def scores(floor, hp=1.0, combats=0.0, kills=0):
    return {"floor": floor / 48, "hp": hp, "combat": combats / 48, "kills": kills / 48}


def run(floors: int, steps: int, won=False, kills=0) -> list[dict]:
    """A run's scores, step by step: floors reached evenly over the steps, one combat won per floor, HP falling to
    nothing for a loss, kills on the last floors; then zero() after the run ends."""
    path = []
    for t in range(steps + 1):
        floor = 1 + (floors - 1) * t // steps
        path.append(scores(floor, hp=1.0 if won else 1.0 - t / steps, combats=floor - 1,
                           kills=max(0, kills - (floors - floor))))
    return path + [reward.zero()]


def discounted_return(path: list[dict], outcome: str) -> float:
    total, discount = 0.0, 1.0
    for before, after in zip(path, path[1:]):
        step = sum(reward.terms(before, after, GAMMA).values())
        if after is path[-1]:
            step += reward.outcome(outcome)
        total += discount * step
        discount *= GAMMA
    return total


class WorkedRunsTest(unittest.TestCase):
    """The properties spec 009 asks of the reward, on whole runs."""

    def test_a_deeper_loss_returns_more_even_against_a_slower_shallow_one(self):
        deep = discounted_return(run(17, 300, kills=2), "loss")
        self.assertGreater(deep, discounted_return(run(5, 100), "loss"))
        self.assertGreater(deep, discounted_return(run(5, 300), "loss"))

    def test_stalling_never_pays(self):
        for floors in (5, 17, 40):
            fast = discounted_return(run(floors, 10 * floors), "loss")
            slow = discounted_return(run(floors, 30 * floors), "loss")
            self.assertGreater(fast, slow, floors)

    def test_a_win_returns_more_than_any_loss_at_the_same_pace(self):
        # At the same pace. A loss reached much faster can return more than a slow win: the discount (0.999) leaves a
        # win 3,000 steps away about 5% of its worth. That favours speed, not losing, and is the discount's to answer.
        for pace in (20, 60):
            win = discounted_return(run(48, 48 * pace, won=True, kills=8), "win")
            for floors in (1, 17, 47, 48):
                loss = discounted_return(run(floors, floors * pace, kills=min(8, floors)), "loss")
                self.assertGreater(win, loss, (pace, floors))

    def test_repeating_a_state_adds_nothing(self):
        state_ = scores(5, hp=0.5, combats=4, kills=1)
        for term, value in reward.terms(state_, state_, GAMMA).items():
            if term in reward.PROGRESS:
                self.assertEqual(value, 0.0, term)
        # Progress never pays twice: a score that falls and rises again pays only the part above its old height.
        healed = scores(5, hp=0.5, combats=3.5, kills=1)
        back = sum(reward.terms(state_, healed, 1.0)[t] + reward.terms(healed, state_, 1.0)[t] for t in reward.PROGRESS)
        self.assertEqual(back, 0.0)

    def test_shaping_adds_up_to_minus_the_starting_scores(self):
        path = run(9, 120)
        report = reward.RunReport(GAMMA, path[0])
        for before, after in zip(path, path[1:]):
            report.add(before, after, terminated=after is path[-1])
        for term, weight in reward.SHAPING.items():
            self.assertAlmostEqual(report.contribution[term], -weight * path[0][term], places=9)
        self.assertGreater(report.contribution["floor"], 0)


class TermsTest(unittest.TestCase):
    def test_hand_worked_step(self):
        before = {"floor": 0.1, "hp": 1.0, "combat": 0.0, "kills": 0.0}
        after = {"floor": 0.2, "hp": 0.5, "combat": 0.0, "kills": 1 / 48}
        parts = reward.terms(before, after, gamma=0.5)
        self.assertAlmostEqual(parts["floor"], 1.0 * 0.1)
        self.assertAlmostEqual(parts["kills"], 1 / 48)
        self.assertAlmostEqual(parts["hp"], 0.25 * (0.5 * 0.5 - 1.0))
        self.assertEqual(parts["combat"], 0.0)

    def test_progress_pays_nothing_when_the_run_ends(self):
        parts = reward.terms(scores(12, kills=3), reward.zero(), GAMMA)
        self.assertEqual((parts["floor"], parts["kills"]), (0.0, 0.0))

    def test_truncated_run_keeps_its_scores(self):
        report = reward.RunReport(0.99, scores(4))
        report.add(scores(4), scores(5), terminated=False)
        self.assertEqual(report.final, scores(5))

    def test_outcome(self):
        self.assertEqual((reward.outcome("win"), reward.outcome("loss"), reward.outcome(None)), (1.0, 0.0, 0.0))

    def test_a_full_run_of_progress_is_on_the_scale_of_a_win(self):
        self.assertEqual(reward.PROGRESS["floor"], reward.OUTCOMES["win"])
        self.assertLessEqual(sum(reward.SHAPING.values()), 0.5)

    def test_definition_hash_follows_the_definition(self):
        base = reward.definition_hash()
        for name, changed in [("PROGRESS", {**reward.PROGRESS, "kills": 2.0}), ("SHAPING", {**reward.SHAPING, "hp": 0.5}),
                              ("OUTCOMES", {"win": 2.0, "loss": 0.0}), ("FULL_RUN", 49),
                              ("REWARD_REVISION", reward.REWARD_REVISION + 1)]:
            with mock.patch.object(reward, name, changed):
                self.assertNotEqual(reward.definition_hash(), base, name)


if __name__ == "__main__":
    unittest.main()
