"""Tests for encoding.py on recorded decisions of every kind. Run: python -m unittest discover -s agent/tests -t ."""

import copy
import json
import unittest
from pathlib import Path

import numpy as np

from agent.env import encoding
from agent.env.encoding import Encoder, EncodingError
from agent.env.vocabulary import Vocabulary

RECORDINGS = Path(__file__).with_name("recordings") / "decisions.jsonl"
CARD_FIELDS = {"id", "type", "rarity", "upgrade", "vars", "keywords", "enchantment", "affliction"}
HAND_FIELDS = CARD_FIELDS | {"cost", "costs_x", "star_cost", "target", "playable", "preview"}


def recordings() -> list[dict]:
    return [json.loads(line) for line in RECORDINGS.read_text(encoding="utf-8").splitlines() if line.strip()]


def cards_in(state: dict):
    """Every card object in a decision's state, with whether it is a hand card."""
    yield from ((card, False) for card in state["run"]["deck"])
    combat = state.get("combat")
    if combat:
        yield from ((card, True) for card in combat["hand"])
        for pile in ("draw", "discard", "exhaust"):
            yield from ((card, False) for card in combat[pile])
    for kind in ("card_reward", "card_select"):
        if kind in state:
            yield from ((card, False) for card in state[kind]["cards"])
    if "bundle" in state:
        yield from ((card, False) for bundle in state["bundle"]["bundles"] for card in bundle)
    if "shop" in state:
        yield from ((item["card"], False) for item in state["shop"]["items"] if item["card"])
    if "reward" in state:
        yield from ((r["card"], False) for r in state["reward"]["rewards"] if r["card"])


class RecordingsTest(unittest.TestCase):
    def test_every_kind_is_recorded(self):
        kinds = {decision["kind"] for decision in recordings()}
        self.assertEqual(kinds, set(encoding.KINDS))

    def test_a_mid_combat_selection_and_a_multi_card_selection_are_recorded(self):
        selections = [d for d in recordings() if d["kind"] == "card_select"]
        self.assertTrue(any("combat" in d["state"] for d in selections))
        self.assertTrue(any(d["state"]["card_select"]["max"] > 1 for d in selections))

    def test_everything_a_player_can_look_up_is_in_the_state(self):
        for decision in recordings():
            state = decision["state"]
            self.assertIn("map", state)
            self.assertIn("boss", state["run"])
            for card, in_hand in cards_in(state):
                self.assertEqual(set(card), HAND_FIELDS if in_hand else CARD_FIELDS, card)
            if "combat" in state:
                self.assertIn("encounter", state["combat"])
                self.assertTrue(all("combat_id" in enemy for enemy in state["combat"]["enemies"]))


class EncodingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vocabulary = Vocabulary.load()
        cls.encoder = Encoder(cls.vocabulary)
        cls.shapes = None

    def test_every_recording_encodes_to_the_same_shapes_in_range(self):
        shapes = None
        for decision in recordings():
            obs, mask = self.encoder.encode(decision)
            got = {name: (array.shape, array.dtype) for name, array in obs.items()}
            shapes = shapes or got
            self.assertEqual(got, shapes, decision["kind"])
            self.assertEqual(mask.shape, (encoding.ACTION_COUNT,))
            for name, array in obs.items():
                self.assertTrue(np.isfinite(array).all(), name)
                if array.dtype == np.float32:
                    self.assertLessEqual(np.abs(array).max(initial=0), 20, name)
                if name.endswith("_present"):
                    self.assertTrue(set(np.unique(array)) <= {0.0, 1.0}, name)
                if name.endswith("_ids") or name == "global_ids":
                    self.assertTrue(((array >= 0) & (array < len(self.vocabulary))).all(), name)

    def test_mask_is_exactly_the_legal_actions_and_maps_back(self):
        for decision in recordings():
            living = self.encoder.living(decision)
            legal = self.encoder.actions(decision, living)
            _, mask = self.encoder.encode(decision)
            self.assertEqual(set(np.flatnonzero(mask)), set(legal))
            if decision["kind"] == "card_select":
                select = decision["state"]["card_select"]
                expected = len(select["cards"]) + (select["min"] == 0)
                self.assertEqual(int(mask.sum()), expected)
            else:
                self.assertEqual(int(mask.sum()), len(decision["actions"]))
                self.assertEqual(sorted(legal.values()), list(range(len(decision["actions"]))))

    def test_ids_map_back_to_the_vocabulary(self):
        for decision in recordings():
            obs, _ = self.encoder.encode(decision)
            deck = decision["state"]["run"]["deck"]
            for i, card in enumerate(deck):
                self.assertEqual(self.vocabulary.keys[obs["deck_ids"][i, 0] - 1], f"CARD.{card['id']}")
            relics = decision["state"]["run"]["relics"]
            for i, relic in enumerate(relics):
                self.assertEqual(self.vocabulary.keys[obs["relics_ids"][i] - 1], f"RELIC.{relic['id']}")

    def test_picked_cards_are_marked_and_masked(self):
        decision = next(d for d in recordings() if d["kind"] == "card_select" and d["state"]["card_select"]["max"] > 1)
        obs, mask = self.encoder.encode(decision, frozenset({0}))
        self.assertEqual(obs["choices"][0, encoding.CARD_FLOATS], 1.0)
        self.assertFalse(mask[encoding.segment("card", 0)])
        self.assertTrue(mask[encoding.segment("card", 1)])

    def test_a_decision_that_does_not_fit_raises_naming_the_set(self):
        decision = copy.deepcopy(recordings()[0])
        card = decision["state"]["run"]["deck"][0]
        decision["state"]["run"]["deck"] = [card] * (encoding.DECK + 1)
        with self.assertRaisesRegex(EncodingError, f"deck has {encoding.DECK + 1} entries"):
            self.encoder.encode(decision)

    def test_largest_sizes_are_recorded(self):
        for decision in recordings():
            self.encoder.encode(decision)
        self.assertGreater(self.encoder.largest["deck"], 0)

    def test_route_summaries(self):
        points = [{"type": t, "row": r, "col": 0} for t, r in
                  [("Monster", 0), ("Elite", 1), ("RestSite", 1), ("Boss", 2)]]
        children = [[1, 2], [3], [3], []]
        routes = encoding._routes(points, children)
        self.assertEqual(routes[0][:2], [0, 1], "fewest and most elites from the start")
        self.assertEqual(routes[0][2:4], [0, 1], "fewest and most rest sites")
        self.assertEqual(routes[1][:2], [1, 1])


if __name__ == "__main__":
    unittest.main()
