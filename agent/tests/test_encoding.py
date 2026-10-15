"""Tests for encoding.py on recorded decisions of every kind. Run: python -m unittest discover -s agent/tests -t ."""

import copy
import json
import unittest
from unittest import mock
from pathlib import Path

import numpy as np

from agent.env import encoding
from agent.env.encoding import Encoder, EncodingError
from agent.env.vocabulary import Vocabulary

RECORDINGS = Path(__file__).with_name("recordings") / "decisions.jsonl"
CARD_FIELDS = {"id", "type", "rarity", "upgrade", "cost", "costs_x", "star_cost", "vars", "keywords", "enchantment",
               "affliction"}
HAND_FIELDS = CARD_FIELDS | {"target", "playable", "preview"}
# Where a card's cost and copies sit among its floats, and the run's sizes among the global numbers.
COST = 3 + encoding.NUMBERS + 2
COPIES = COST + 5
DECK_SIZE, HAND_SIZE, DRAW_SIZE, DISCARD_SIZE, EXHAUST_SIZE, POTIONS_HELD, POTION_SLOTS = range(
    encoding.GLOBAL_FLOATS - 7, encoding.GLOBAL_FLOATS)


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
            self.assertEqual(got, {name: (shape, np.dtype(dtype)) for name, (shape, dtype) in encoding.OBSERVATION.items()},
                             decision["kind"])
            self.assertEqual(mask.shape, (encoding.ACTION_COUNT,))
            for name, array in obs.items():
                self.assertTrue(np.isfinite(array).all(), name)
                if array.dtype == np.float32:
                    self.assertLessEqual(np.abs(array).max(initial=0), 20, name)
                if name.endswith("_present"):
                    self.assertTrue(set(np.unique(array)) <= {0.0, 1.0}, name)
                if name.endswith("_ids") or name == "global_ids":
                    self.assertTrue(((array >= 0) & (array < len(self.vocabulary))).all(), name)

    def test_schema_hash_follows_the_schema(self):
        base = encoding.schema_hash()
        self.assertEqual(base, encoding.schema_hash())
        for name, changed in [("ACTIONS", encoding.ACTIONS + [("extra", 1)]), ("KINDS", encoding.KINDS[:-1]),
                              ("SCHEMA_REVISION", encoding.SCHEMA_REVISION + 1),
                              ("OBSERVATION", {**encoding.OBSERVATION, "cells": ((1,), "float32")})]:
            with mock.patch.object(encoding, name, changed):
                self.assertNotEqual(encoding.schema_hash(), base, name)

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
            elif decision["kind"] == "reward":
                # Proceeding waits while a card reward or gold can be taken (the recording offers one).
                proceed = next(i for i, a in enumerate(decision["actions"]) if a["kind"] == "proceed")
                self.assertEqual(sorted(legal.values()), [i for i in range(len(decision["actions"])) if i != proceed])
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

    def test_every_potion_slot_the_game_can_give_fits(self):
        # 3 slots to start, plus Alchemical Coffer's 4, Potion Belt's 2 and Phial Holster's 1.
        decision = copy.deepcopy(next(d for d in recordings() if any(d["state"]["run"]["potions"])))
        potion = next(p for p in decision["state"]["run"]["potions"] if p)
        decision["state"]["run"]["potions"] = [dict(potion) for _ in range(10)]
        obs, _ = self.encoder.encode(decision)
        self.assertEqual(obs["potions_present"].sum(), 10)

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


def recorded(kind: str) -> dict:
    return copy.deepcopy(next(d for d in recordings() if d["kind"] == kind))


class DeckBuildingTest(unittest.TestCase):
    """Spec 014: the rewards screen, and what the policy sees of its deck, piles, cards and potions."""

    @classmethod
    def setUpClass(cls):
        cls.encoder = Encoder(Vocabulary.load())

    def legal(self, decision: dict) -> dict:
        return self.encoder.actions(decision, self.encoder.living(decision))

    def test_proceeding_waits_until_no_card_reward_or_gold_is_left(self):
        decision = recorded("reward")
        rewards = decision["state"]["reward"]["rewards"]
        self.assertTrue({"card", "gold"} & {r["type"] for r in rewards}, "the recording offers a card reward or gold")
        self.assertNotIn(encoding.segment("proceed"), self.legal(decision))
        potion = {"type": "potion", "id": "FIRE_POTION", "amount": None, "group": None, "card": None}
        decision["state"]["reward"]["rewards"] = [potion]
        decision["actions"] = [{"kind": "take", "reward": 0}, {"kind": "proceed"}]
        self.assertIn(encoding.segment("proceed"), self.legal(decision), "a potion may be left")
        decision["state"]["reward"]["rewards"], decision["actions"] = [], [{"kind": "proceed"}]
        self.assertIn(encoding.segment("proceed"), self.legal(decision), "nothing left")

    def test_a_card_reward_no_longer_offered_does_not_hold_the_screen(self):
        # A skipped card reward stays listed but is not offered again.
        decision = recorded("reward")
        rewards = decision["state"]["reward"]["rewards"]
        decision["actions"] = [a for a in decision["actions"]
                               if a["kind"] != "take" or rewards[a["reward"]]["type"] not in ("card", "gold")]
        self.assertIn(encoding.segment("proceed"), self.legal(decision))

    def test_the_card_reward_screen_keeps_skip(self):
        decision = recorded("card_reward")
        skip = decision["state"]["card_reward"]["alternatives"].index("Skip")
        self.assertIn(encoding.segment("option", skip), self.legal(decision))

    def test_copies_and_deck_size(self):
        decision = recorded("map")
        deck = decision["state"]["run"]["deck"]
        first = deck[0]
        copies = sum(card["id"] == first["id"] and card["upgrade"] == first["upgrade"] for card in deck)
        obs, _ = self.encoder.encode(decision)
        self.assertAlmostEqual(obs["deck"][0, COPIES], encoding.slog(copies), places=5)
        self.assertAlmostEqual(obs["global"][DECK_SIZE], encoding.slog(len(deck)), places=5)
        # The same deck with every card doubled: the same mix, twice the copies and the size.
        decision["state"]["run"]["deck"] = deck + copy.deepcopy(deck)
        doubled, _ = self.encoder.encode(decision)
        self.assertAlmostEqual(doubled["deck"][0, COPIES], encoding.slog(2 * copies), places=5)
        self.assertAlmostEqual(doubled["global"][DECK_SIZE], encoding.slog(2 * len(deck)), places=5)

    def test_an_upgraded_copy_counts_apart(self):
        decision = recorded("map")
        deck = decision["state"]["run"]["deck"]
        decision["state"]["run"]["deck"] = deck + [dict(deck[0], upgrade=deck[0]["upgrade"] + 1)]
        obs, _ = self.encoder.encode(decision)
        self.assertAlmostEqual(obs["deck"][len(deck), COPIES], encoding.slog(1), places=5)

    def test_offered_cards_count_the_copies_the_deck_holds(self):
        decision = recorded("card_reward")
        offered = decision["state"]["card_reward"]["cards"][0]
        held = sum(card["id"] == offered["id"] and card["upgrade"] == offered["upgrade"]
                   for card in decision["state"]["run"]["deck"])
        decision["state"]["run"]["deck"] += [copy.deepcopy(offered), copy.deepcopy(offered)]
        obs, _ = self.encoder.encode(decision)
        self.assertAlmostEqual(obs["choices"][0, COPIES], encoding.slog(held + 2), places=5)

    def test_the_hand_and_combat_piles_have_their_sizes(self):
        decision = recorded("combat")
        combat = decision["state"]["combat"]
        obs, _ = self.encoder.encode(decision)
        for index, pile in [(HAND_SIZE, "hand"), (DRAW_SIZE, "draw"), (DISCARD_SIZE, "discard"),
                            (EXHAUST_SIZE, "exhaust")]:
            self.assertAlmostEqual(obs["global"][index], encoding.slog(len(combat[pile])), places=5, msg=pile)

    def test_a_full_potion_belt_and_one_with_a_free_slot_differ(self):
        decision = copy.deepcopy(next(d for d in recordings() if any(d["state"]["run"]["potions"])))
        potion = next(p for p in decision["state"]["run"]["potions"] if p)
        decision["state"]["run"]["potions"] = [dict(potion), dict(potion), None]
        free, _ = self.encoder.encode(decision)
        decision["state"]["run"]["potions"] = [dict(potion), dict(potion), dict(potion)]
        full, _ = self.encoder.encode(decision)
        self.assertAlmostEqual(free["global"][POTIONS_HELD], encoding.slog(2), places=5)
        self.assertAlmostEqual(full["global"][POTIONS_HELD], encoding.slog(3), places=5)
        self.assertAlmostEqual(free["global"][POTION_SLOTS], encoding.slog(3), places=5)
        self.assertAlmostEqual(full["global"][POTION_SLOTS], encoding.slog(3), places=5)

    def test_cards_outside_the_hand_have_their_cost(self):
        decision = recorded("card_reward")
        card = decision["state"]["card_reward"]["cards"][0]
        card.update(cost=2, costs_x=False, star_cost=-1)
        obs, _ = self.encoder.encode(decision)
        np.testing.assert_allclose(obs["choices"][0, COST:COST + 5], [encoding.slog(2), 0, 0, 1, 0], rtol=1e-6)
        card.update(cost=-1, costs_x=True)
        obs, _ = self.encoder.encode(decision)
        np.testing.assert_allclose(obs["choices"][0, COST:COST + 5], [0, 1, 0, 0, 0])
        deck_card = decision["state"]["run"]["deck"][0]
        self.assertAlmostEqual(obs["deck"][0, COST], encoding.slog(max(deck_card["cost"], 0)), places=5)

    def test_every_number_of_a_card_is_kept(self):
        numbers = {"Damage": 6, "Block": 0, "CalculationBase": 1, "ExtraDamage": 2, "CalculatedDamage": 3, "Cards": 4}
        self.assertEqual(encoding._numbers(numbers), [6, 0, 1, 2, 3, 4, 0, 0])
        too_many = {f"N{i}": i for i in range(encoding.NUMBERS + 1)}
        with self.assertRaisesRegex(EncodingError, f"past the {encoding.NUMBERS} the observation holds"):
            encoding._numbers(too_many)

    def test_a_special_card_reward_is_seen_as_a_card(self):
        decision = recorded("reward")
        card = copy.deepcopy(decision["state"]["run"]["deck"][0])
        rewards = decision["state"]["reward"]["rewards"]
        rewards.append({"type": "special_card", "id": card["id"], "amount": None, "group": None, "card": card})
        obs, _ = self.encoder.encode(decision)
        slot = len(rewards) - 1
        self.assertEqual(obs["reward_cards_present"].sum(), 1.0)
        self.assertEqual(obs["reward_cards_present"][slot], 1.0)
        self.assertEqual(obs["reward_cards_ids"][slot, 0], obs["deck_ids"][0, 0])
