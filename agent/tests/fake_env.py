"""A fake environment for the trainer's tests: the environment's interface (agent/env/environment.py) and its
observation shapes (encoding.OBSERVATION), with no game.

An episode is LENGTH steps. On every CHOICE_EVERY-th step two options are legal, at positions drawn at random, and the
good one is marked in its numbers; on the others only end_turn is legal. The reward is 0 until the last step, which
gives (good choices - half) / half: random play averages 0, the best play gets +1. So the reward comes long after the
choices that earn it.

fail_every truncates every n-th episode partway as a failure; truncate_at truncates every episode at that step, like
the step limit.
"""

import random

import numpy as np

from agent.env import encoding, reward
from agent.env.encoding import segment
from agent.env.vocabulary import Vocabulary

LENGTH = 100
CHOICE_EVERY = 10
CHOICES = LENGTH // CHOICE_EVERY
KIND_INDEX = Vocabulary.load().index("KIND", "event")


class FakeEnvironment:
    def __init__(self, seed: int = 0, name: str = "fake", fail_every: int = 0, truncate_at: int = 0) -> None:
        self.name, self.fail_every, self.truncate_at = name, fail_every, truncate_at
        self._kind_index = KIND_INDEX
        self._rng = random.Random(seed)
        self._episodes = 0

    def reset(self, seed: str | None = None, options: dict | None = None) -> tuple[dict, dict]:
        self._episodes += 1
        self._seed = seed or f"FAKE{self._rng.randrange(10**6):06d}"
        self._step, self._good = 0, 0
        self._decide()
        return self._obs, self._info(None)

    def step(self, action: int) -> tuple[dict, float, bool, bool, dict]:
        if not self._mask[action]:
            raise ValueError(f"illegal action {encoding.describe(action)}")
        self._good += int(action == self._good_action)
        self._step += 1
        if self.fail_every and self._episodes % self.fail_every == 0 and self._step == LENGTH // 2:
            return self._end("failed: the fake game was told to fail", 0.0, terminated=False)
        if self._step == LENGTH:
            half = CHOICES / 2
            return self._end("loss", (self._good - half) / half, terminated=True)
        if self.truncate_at and self._step == self.truncate_at:
            self._decide()
            return self._end("step_limit", 0.0, terminated=False)
        self._decide()
        return self._obs, 0.0, False, False, self._info(None)

    def action_masks(self) -> np.ndarray:
        return self._mask

    def close(self) -> None:
        pass

    def rng_state(self):
        return self._rng.getstate()

    def set_rng_state(self, state) -> None:
        self._rng.setstate(state)

    def _decide(self) -> None:
        obs = {key: np.zeros(shape, dtype) for key, (shape, dtype) in encoding.OBSERVATION.items()}
        obs["global_ids"][0] = self._kind_index
        obs["global"][0] = self._step / LENGTH
        mask = np.zeros(encoding.ACTION_COUNT, bool)
        if self._step % CHOICE_EVERY == 0:
            slots = self._rng.sample(range(encoding.OPTIONS), 2)
            for slot in slots:
                obs["options_present"][slot] = 1
                obs["options"][slot, 3] = 1
                mask[segment("option", slot)] = True
            obs["options"][slots[0], 0] = 1  # marks the good one
            self._good_action = segment("option", slots[0])
        else:
            mask[segment("end_turn")] = True
            self._good_action = None
        self._obs, self._mask = obs, mask

    def _end(self, outcome: str, step_reward: float, terminated: bool):
        info = self._info(outcome)
        zero = reward.zero()
        info["run"] = {"contribution": dict(zero), "highest": dict(zero), "final": dict(zero)}
        return self._obs, step_reward, terminated, not terminated, info

    def _info(self, outcome) -> dict:
        return {"seed": self._seed, "floor": self._step // CHOICE_EVERY, "act": 1, "kind": "event", "outcome": outcome,
                "outcome_reward": 0.0, "scores": reward.zero()}
