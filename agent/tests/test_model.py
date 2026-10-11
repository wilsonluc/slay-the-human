"""Tests for ppo/model.py on recorded decisions. Run: python -m unittest discover -s agent/tests -t ."""

import unittest

import numpy as np
import torch

from agent.env import encoding
from agent.env.encoding import ENEMIES, HAND, Encoder, segment
from agent.env.vocabulary import Vocabulary
from agent.ppo.model import Policy, as_tensors, masked
from agent.tests.test_encoding import recordings

HAND_KEYS = ["hand_ids", "hand", "hand_present"]
ENEMY_KEYS = ["enemies_ids", "enemies", "enemies_present", "enemy_powers_ids", "enemy_powers", "enemy_powers_present",
              "intents_ids", "intents", "intents_present"]
REWARD_KEYS = ["rewards_ids", "rewards", "rewards_present"]


def permuted(obs: dict, keys: list[str], order: list[int]) -> dict:
    result = {key: value.copy() for key, value in obs.items()}
    for key in keys:
        result[key][:len(order)] = obs[key][order]
    return result


class PolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.manual_seed(0)
        vocabulary = Vocabulary.load()
        cls.encoder = Encoder(vocabulary)
        cls.policy = Policy(len(vocabulary))
        cls.decisions = recordings()

    def run_policy(self, *observations):
        batch = {key: np.stack([obs[key] for obs in observations]) for key in observations[0]}
        with torch.no_grad():
            return self.policy(as_tensors(batch))

    def encoded(self, kind, test=lambda d: True):
        decision = next(d for d in self.decisions if d["kind"] == kind and test(d))
        return self.encoder.encode(decision)

    def test_every_recording_gives_one_logit_per_action_and_a_value(self):
        observations = [self.encoder.encode(d)[0] for d in self.decisions]
        logits, value = self.run_policy(*observations)
        self.assertEqual(logits.shape, (len(observations), encoding.ACTION_COUNT))
        self.assertEqual(value.shape, (len(observations),))
        self.assertTrue(torch.isfinite(logits).all() and torch.isfinite(value).all())

    def test_reordering_the_hand_reorders_its_logits_only(self):
        obs, mask = self.encoded("combat", lambda d: len(d["state"]["combat"]["hand"]) >= 3)
        count = int(obs["hand_present"].sum())
        order = list(reversed(range(count)))
        (logits, value), (logits2, value2) = self.run_policy(obs), self.run_policy(permuted(obs, HAND_KEYS, order))
        play = slice(segment("play"), segment("play") + HAND * (1 + ENEMIES))
        cards, cards2 = logits[0, play].view(HAND, -1), logits2[0, play].view(HAND, -1)
        torch.testing.assert_close(cards2[:count], cards[order])
        torch.testing.assert_close(logits2[0, play.stop:], logits[0, play.stop:])
        torch.testing.assert_close(value2, value)

    def test_reordering_enemies_reorders_their_targets_only(self):
        obs, _ = self.encoded("combat")
        # A second enemy: the first one copied, at half its HP.
        for key in ENEMY_KEYS:
            obs[key][1] = obs[key][0]
        obs["enemies"][1, 0] *= 0.5
        count = 2
        order = list(reversed(range(count)))
        (logits, value), (logits2, value2) = self.run_policy(obs), self.run_policy(permuted(obs, ENEMY_KEYS, order))
        play = slice(segment("play"), segment("play") + HAND * (1 + ENEMIES))
        cards, cards2 = logits[0, play].view(HAND, -1), logits2[0, play].view(HAND, -1)
        torch.testing.assert_close(cards2[:, 0], cards[:, 0])  # no target
        torch.testing.assert_close(cards2[:, 1:1 + count], cards[:, [1 + i for i in order]])
        torch.testing.assert_close(value2, value)

    def test_reordering_rewards_reorders_their_logits_only(self):
        obs, _ = self.encoded("reward", lambda d: len(d["state"]["reward"]["rewards"]) >= 2)
        count = int(obs["rewards_present"].sum())
        order = list(reversed(range(count)))
        (logits, value), (logits2, value2) = self.run_policy(obs), self.run_policy(permuted(obs, REWARD_KEYS, order))
        start = segment("reward")
        torch.testing.assert_close(logits2[0, start:start + count], logits[0, start:start + count][order])
        torch.testing.assert_close(logits2[0, :start], logits[0, :start])
        torch.testing.assert_close(value2, value)

    def test_illegal_actions_get_no_probability_and_no_gradient(self):
        obs, mask = self.encoded("combat")
        batch = as_tensors({key: value[None] for key, value in obs.items()})
        mask = torch.as_tensor(mask)[None]
        logits, _ = self.policy(batch)
        logits.retain_grad()
        distribution = torch.distributions.Categorical(logits=masked(logits, mask))
        self.assertTrue((distribution.probs[~mask] == 0).all())
        legal = mask.nonzero()[0, 1]
        (-distribution.log_prob(legal[None]) - distribution.entropy()).sum().backward()
        self.assertTrue((logits.grad[~mask] == 0).all())
        self.assertTrue((logits.grad[mask] != 0).any())

    def test_entropy_counts_legal_actions_only(self):
        obs, mask = self.encoded("combat")
        logits, _ = self.run_policy(obs)
        mask = torch.as_tensor(mask)[None]
        entropy = torch.distributions.Categorical(logits=masked(logits, mask)).entropy()
        legal_only = torch.distributions.Categorical(logits=logits[mask]).entropy()
        torch.testing.assert_close(entropy[0], legal_only)


if __name__ == "__main__":
    unittest.main()
