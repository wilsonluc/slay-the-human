"""Rollout storage, GAE and minibatches. Pure arrays: no environments, no model.

Arrays are [steps, games, ...]: each game fills its own column. IDs are stored as int32 to halve the observations'
size; the model reads them as int64.
"""

import numpy as np

from agent.env.encoding import ACTION_COUNT, OBSERVATION


def gae(reward, value, terminated, truncated, bootstrap, last_value, gamma: float, lam: float) -> np.ndarray:
    """Advantages, [steps, games]. A terminated step adds no value after it; a truncated step adds its bootstrap value
    (the value of the observation it returned); the rollout's last step adds last_value, the value of the observation
    after it. An episode's end stops the advantage flowing back from the next episode."""
    steps = reward.shape[0]
    advantage = np.zeros_like(reward, dtype=np.float32)
    following = np.zeros(reward.shape[1:], np.float32)
    for t in reversed(range(steps)):
        next_value = value[t + 1] if t + 1 < steps else last_value
        next_value = np.where(terminated[t], 0.0, np.where(truncated[t], bootstrap[t], next_value))
        delta = reward[t] + gamma * next_value - value[t]
        ended = terminated[t] | truncated[t]
        following = delta + gamma * lam * np.where(ended, 0.0, following)
        advantage[t] = following
    return advantage


class Buffer:
    def __init__(self, steps: int, games: int) -> None:
        self.steps, self.games = steps, games
        self.obs = {key: np.zeros((steps, games, *shape), np.int32 if dtype == "int64" else np.float32)
                    for key, (shape, dtype) in OBSERVATION.items()}
        self.mask = np.zeros((steps, games, ACTION_COUNT), bool)
        self.action = np.zeros((steps, games), np.int64)
        self.log_prob = np.zeros((steps, games), np.float32)
        self.value = np.zeros((steps, games), np.float32)
        self.reward = np.zeros((steps, games), np.float32)
        self.terminated = np.zeros((steps, games), bool)
        self.truncated = np.zeros((steps, games), bool)
        self.bootstrap = np.zeros((steps, games), np.float32)
        self.kind = np.zeros((steps, games), np.int64)  # the decision kind's vocabulary index (global_ids[0])

    def store(self, t: int, game: int, obs: dict, mask, action: int, log_prob: float, value: float) -> None:
        for key, array in obs.items():
            self.obs[key][t, game] = array
        self.mask[t, game] = mask
        self.action[t, game], self.log_prob[t, game], self.value[t, game] = action, log_prob, value
        self.kind[t, game] = obs["global_ids"][0]

    def result(self, t: int, game: int, reward: float, terminated: bool, truncated: bool, bootstrap: float = 0.0):
        self.reward[t, game], self.terminated[t, game], self.truncated[t, game] = reward, terminated, truncated
        self.bootstrap[t, game] = bootstrap

    def finish(self, last_value: np.ndarray, gamma: float, lam: float) -> None:
        self.advantage = gae(self.reward, self.value, self.terminated, self.truncated, self.bootstrap, last_value,
                             gamma, lam)
        self.returns = self.advantage + self.value

    def minibatches(self, size: int, rng: np.random.Generator):
        """Shuffled minibatches over every step of every game, as flat arrays."""
        count = self.steps * self.games
        order = rng.permutation(count)
        flat = lambda array: array.reshape(count, *array.shape[2:])
        for start in range(0, count, size):
            rows = order[start:start + size]
            yield {
                "obs": {key: flat(array)[rows] for key, array in self.obs.items()},
                "mask": flat(self.mask)[rows], "action": flat(self.action)[rows],
                "log_prob": flat(self.log_prob)[rows], "advantage": flat(self.advantage)[rows],
                "returns": flat(self.returns)[rows], "kind": flat(self.kind)[rows],
            }
