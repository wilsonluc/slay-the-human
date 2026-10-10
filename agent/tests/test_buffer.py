"""Tests for ppo/buffer.py on hand-worked values. Run: python -m unittest discover -s agent/tests -t ."""

import unittest

import numpy as np

from agent.ppo.buffer import Buffer, gae


def column(*values, dtype=np.float32):
    return np.array(values, dtype)[:, None]


class GaeTest(unittest.TestCase):
    gamma, lam = 0.9, 0.5

    def test_rollout_end_bootstraps_from_the_last_value(self):
        reward, value = column(1, 0), column(0.5, 0.25)
        advantage = gae(reward, value, column(0, 0, dtype=bool), column(0, 0, dtype=bool), column(0, 0),
                        np.array([2.0]), self.gamma, self.lam)
        delta1 = 0 + 0.9 * 2.0 - 0.25
        delta0 = 1 + 0.9 * 0.25 - 0.5
        np.testing.assert_allclose(advantage[:, 0], [delta0 + 0.9 * 0.5 * delta1, delta1], rtol=1e-6)

    def test_terminated_adds_no_value_and_stops_the_flow_back(self):
        reward, value = column(0, -1, 1), column(0.5, 0.25, 0.75)
        terminated = column(0, 1, 0, dtype=bool)
        advantage = gae(reward, value, terminated, column(0, 0, 0, dtype=bool), column(0, 0, 0), np.array([3.0]),
                        self.gamma, self.lam)
        delta2 = 1 + 0.9 * 3.0 - 0.75
        delta1 = -1 - 0.25
        delta0 = 0 + 0.9 * 0.25 - 0.5
        np.testing.assert_allclose(advantage[:, 0], [delta0 + 0.45 * delta1, delta1, delta2], rtol=1e-6)

    def test_truncated_bootstraps_from_its_own_observation(self):
        reward, value = column(0, 0.5, 0), column(0.5, 0.25, 0.75)
        truncated = column(0, 1, 0, dtype=bool)
        advantage = gae(reward, value, column(0, 0, 0, dtype=bool), truncated, column(0, 4.0, 0), np.array([0.0]),
                        self.gamma, self.lam)
        delta2 = 0 + 0 - 0.75
        delta1 = 0.5 + 0.9 * 4.0 - 0.25
        delta0 = 0 + 0.9 * 0.25 - 0.5
        np.testing.assert_allclose(advantage[:, 0], [delta0 + 0.45 * delta1, delta1, delta2], rtol=1e-6)

    def test_games_are_independent_columns(self):
        reward = np.array([[1, 0], [0, 1]], np.float32)
        value = np.zeros((2, 2), np.float32)
        none = np.zeros((2, 2), bool)
        both = gae(reward, value, none, none, np.zeros((2, 2), np.float32), np.zeros(2, np.float32), 0.9, 0.5)
        first = gae(reward[:, :1], value[:, :1], none[:, :1], none[:, :1], np.zeros((2, 1), np.float32),
                    np.zeros(1, np.float32), 0.9, 0.5)
        np.testing.assert_allclose(both[:, :1], first)


class BufferTest(unittest.TestCase):
    def test_minibatches_cover_every_step_once(self):
        buffer = Buffer(steps=4, games=3)
        buffer.action[:] = np.arange(12).reshape(4, 3)
        buffer.finish(np.zeros(3, np.float32), 0.9, 0.5)
        seen = np.concatenate([batch["action"] for batch in buffer.minibatches(5, np.random.default_rng(0))])
        self.assertEqual(sorted(seen), list(range(12)))
        np.testing.assert_allclose(buffer.returns, buffer.advantage + buffer.value)


if __name__ == "__main__":
    unittest.main()
