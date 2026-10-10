"""Tests for bridge.py and random_agent.py, with a fake mod on a real socket. Run: python -m unittest discover -s agent/tests -t ."""

import json
import os
import random
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from agent import random_agent
from agent.bridge import PROTOCOL, Bridge, BridgeError

# Decisions shaped as in docs/protocol.md.
RUN = {
    "character": "IRONCLAD", "hp": 80, "max_hp": 80, "gold": 99, "ascension": 0, "act": 1, "floor": 1,
    "deck": [{"id": "STRIKE_IRONCLAD", "upgraded": False}], "relics": [{"id": "BURNING_BLOOD", "counter": None}],
    "potions": [None],
}
DECISION = {
    "type": "decision",
    "id": 1,
    "kind": "combat",
    "state": {
        "run": RUN,
        "combat": {
            "turn": 1,
            "player": {"hp": 80, "max_hp": 80, "block": 0, "energy": 3, "max_energy": 3, "stars": 0, "powers": []},
            "hand": [{"id": "STRIKE_IRONCLAD", "upgraded": False, "cost": 1, "costs_x": False, "star_cost": -1,
                      "type": "Attack", "target": "AnyEnemy", "playable": True}],
            "draw": [], "discard": [], "exhaust": [],
            "enemies": [{"id": "NIBBIT", "alive": True, "hp": 20, "max_hp": 20, "block": 0, "powers": [],
                         "intents": [{"type": "Attack", "damage": 6, "hits": 1}]}],
        },
    },
    "actions": [{"kind": "play", "card": 0, "target": 0}, {"kind": "end_turn"}],
}
CARD = {"id": "BASH", "upgraded": False, "type": "Attack", "rarity": "Basic"}


def card_select(decision_id: int, cards: int, low: int, high: int) -> dict:
    return {"type": "decision", "id": decision_id, "kind": "card_select", "actions": [],
            "state": {"run": RUN, "card_select": {"purpose": "upgrade", "min": low, "max": high,
                                                  "cards": [CARD] * cards}}}


HELLO = {"type": "hello", "protocol": PROTOCOL, "game_version": "v0.107.1", "game_commit": "59260271"}
RUN_END = {"type": "run_end", "outcome": "loss", "floor": 3, "seed": "ABC"}


class FakeMod:
    """Plays the mod's side: connects to the bridge, says hello, then sends and receives what a test asks."""

    def __init__(self, port: int, protocol: int = PROTOCOL):
        self.received: list[dict] = []
        self._sock = socket.create_connection(("127.0.0.1", port))
        self._file = self._sock.makefile("rw", encoding="utf-8", newline="\n")
        self.send({**HELLO, "protocol": protocol})
        self.received.append(self.receive())

    def send(self, message: dict) -> None:
        self._file.write(json.dumps(message) + "\n")
        self._file.flush()

    def send_raw(self, line: str) -> None:
        self._file.write(line + "\n")
        self._file.flush()

    def receive(self) -> dict | None:
        line = self._file.readline()
        return json.loads(line) if line else None

    def close(self) -> None:
        self._file.close()
        self._sock.close()


def connect(bridge: Bridge, protocol: int = PROTOCOL) -> FakeMod:
    """Connects a fake mod while the bridge accepts, and returns it once the handshake is done."""
    mods: list[FakeMod] = []
    thread = threading.Thread(target=lambda: mods.append(FakeMod(bridge.port, protocol)))
    thread.start()
    try:
        bridge.accept()
    finally:
        thread.join()
    return mods[0]


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.bridge = Bridge(accept_timeout=5)

    def test_handshake_exchanges_hellos(self):
        mod = connect(self.bridge)
        self.assertEqual(mod.received, [{"type": "hello", "protocol": PROTOCOL}])
        self.assertEqual(self.bridge.hello, HELLO)
        mod.close()

    def test_version_mismatch_names_both_versions(self):
        with self.assertRaisesRegex(BridgeError, f"the game speaks {PROTOCOL + 1}, the agent {PROTOCOL}"):
            connect(self.bridge, protocol=PROTOCOL + 1)

    def test_no_connection_times_out(self):
        with self.assertRaisesRegex(BridgeError, "did not connect within 0.2 seconds"):
            Bridge(accept_timeout=0.2).accept()

    def test_start_waits_for_ready_then_sends_seed_and_character(self):
        mod = connect(self.bridge)
        mod.send({"type": "ready"})
        self.bridge.start("ABC", "IRONCLAD")
        self.assertEqual(mod.receive(), {"type": "start", "seed": "ABC", "character": "IRONCLAD"})
        mod.close()

    def test_start_without_ready_fails(self):
        mod = connect(self.bridge)
        mod.send(DECISION)
        with self.assertRaisesRegex(BridgeError, "expected ready, got 'decision'"):
            self.bridge.start("ABC", "IRONCLAD")
        mod.close()

    def test_decisions_answered_then_run_end_returned_and_connection_kept(self):
        mod = connect(self.bridge)
        mod.send(DECISION)
        mod.send(RUN_END)
        seen = []
        end = self.bridge.play(lambda decision: seen.append(decision) or 1)
        self.assertEqual(seen, [DECISION])
        self.assertEqual(mod.receive(), {"type": "action", "id": 1, "index": 1})
        self.assertEqual(end, RUN_END)
        mod.send({"type": "ready"})
        self.bridge.start("DEF", "IRONCLAD")
        self.assertEqual(mod.receive()["seed"], "DEF")
        mod.close()

    def test_card_select_answered_with_indices(self):
        mod = connect(self.bridge)
        mod.send(card_select(1, cards=3, low=0, high=2))
        mod.send(RUN_END)
        self.bridge.play(lambda decision: [0, 2])
        self.assertEqual(mod.receive(), {"type": "action", "id": 1, "indices": [0, 2]})
        mod.close()

    def test_disconnect_fails(self):
        mod = connect(self.bridge)
        mod.send(DECISION)
        mod.close()
        with self.assertRaisesRegex(BridgeError, "closed the connection"):
            self.bridge.play(lambda decision: 0)

    def test_silence_times_out(self):
        mod = connect(self.bridge)
        with self.assertRaises(TimeoutError):
            self.bridge.next(timeout=0.2)
        mod.close()

    def test_line_that_is_not_json_fails(self):
        mod = connect(self.bridge)
        mod.send_raw("not json")
        with self.assertRaisesRegex(BridgeError, "not JSON"):
            self.bridge.play(lambda decision: 0)
        mod.close()

    def test_unknown_message_type_fails(self):
        mod = connect(self.bridge)
        mod.send({"type": "surprise"})
        with self.assertRaisesRegex(BridgeError, "expected decision or run_end, got 'surprise'"):
            self.bridge.play(lambda decision: 0)
        mod.close()


class RandomPickTest(unittest.TestCase):
    def test_card_select_picks_distinct_cards_within_min_and_max(self):
        for low, high, cards in [(0, 1, 3), (1, 1, 5), (2, 3, 4), (0, 5, 2), (3, 3, 3)]:
            counts = set()
            for seed in range(200):
                chosen = random_agent.pick(card_select(1, cards, low, high), random.Random(seed))
                self.assertEqual(len(chosen), len(set(chosen)))
                self.assertTrue(all(0 <= i < cards for i in chosen))
                self.assertTrue(low <= len(chosen) <= min(high, cards), (low, high, cards, chosen))
                counts.add(len(chosen))
            self.assertEqual(counts, set(range(low, min(high, cards) + 1)), "every allowed count is reachable")

    def test_other_kinds_pick_one_action(self):
        for seed in range(50):
            self.assertIn(random_agent.pick(DECISION, random.Random(seed)), range(len(DECISION["actions"])))


class RandomAgentTest(unittest.TestCase):
    """Runs the random agent as a separate process, with --no-launch, against a fake mod."""

    def play(self, seed: int, runs: int, decisions: int) -> tuple[list[str], list[int]]:
        with tempfile.TemporaryDirectory() as cwd:
            agent = subprocess.Popen(
                [sys.executable, "-m", "agent.random_agent", "--seed", str(seed), "--runs", str(runs), "--no-launch"],
                cwd=cwd, env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[2])},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(agent.stdout.readline().strip(), f"seed={seed}", "the seed is printed first")
            port = int(agent.stdout.readline().removeprefix("port="))
            mod = FakeMod(port)
            seeds, indices = [], []
            for _ in range(runs):
                mod.send({"type": "ready"})
                start = mod.receive()
                self.assertEqual((start["type"], start["character"]), ("start", "IRONCLAD"))
                seeds.append(start["seed"])
                for i in range(1, decisions + 1):
                    mod.send({**DECISION, "id": i, "actions": [{"kind": "end_turn"}] * 5})
                    answer = mod.receive()
                    self.assertEqual(answer["id"], i)
                    indices.append(answer["index"])
                mod.send({**RUN_END, "seed": start["seed"]})
            mod.send({"type": "ready"})
            self.assertIsNone(mod.receive(), "the agent closes the connection at the last ready")
            out, err = agent.communicate(timeout=10)
            mod.close()
        self.assertEqual(agent.returncode, 0, err)
        self.assertEqual(out.count("outcome=loss"), runs)
        self.assertRegex(out, rf"agent_seed={seed} runs={runs} decisions={runs * decisions} per_second=[0-9.]+")
        return seeds, indices

    def test_same_seed_same_runs(self):
        self.assertEqual(self.play(seed=1, runs=2, decisions=10), self.play(seed=1, runs=2, decisions=10))

    def test_game_seeds_differ_between_runs_and_use_the_game_alphabet(self):
        seeds, _ = self.play(seed=7, runs=3, decisions=1)
        self.assertEqual(len(set(seeds)), 3)
        self.assertTrue(all(len(s) == 10 and set(s) <= set(random_agent.SEED_CHARACTERS) for s in seeds))


if __name__ == "__main__":
    unittest.main()
