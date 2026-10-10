"""Tests for bridge.py and random_agent.py, with a fake mod on a real socket. Run: python -m unittest discover agent"""

import json
import random
import socket
import subprocess
import sys
import threading
import unittest
from pathlib import Path

from bridge import PROTOCOL, Bridge, BridgeError

# A decision shaped as in docs/protocol.md.
DECISION = {
    "type": "decision",
    "id": 1,
    "state": {
        "act": 1, "floor": 1, "turn": 1,
        "player": {"hp": 80, "max_hp": 80, "block": 0, "energy": 3, "max_energy": 3, "stars": 0, "powers": []},
        "hand": [{"id": "STRIKE_IRONCLAD", "upgraded": False, "cost": 1, "costs_x": False, "star_cost": -1,
                  "type": "Attack", "target": "AnyEnemy", "playable": True}],
        "draw": 5, "discard": 0, "exhaust": 0,
        "potions": [None],
        "enemies": [{"id": "NIBBIT", "alive": True, "hp": 20, "max_hp": 20, "block": 0, "powers": [],
                     "intents": [{"type": "Attack", "damage": 6, "hits": 1}]}],
    },
    "actions": [{"kind": "play", "card": 0, "target": 0}, {"kind": "end_turn"}],
}


class FakeMod:
    """Plays the mod's side: connects to the bridge and sends the given lines after the handshake."""

    def __init__(self, port: int, protocol: int = PROTOCOL):
        self.received: list[dict] = []
        self._sock = socket.create_connection(("127.0.0.1", port))
        self._file = self._sock.makefile("rw", encoding="utf-8", newline="\n")
        self.send({"type": "hello", "protocol": protocol})
        self.received.append(self.receive())

    def send(self, message: dict) -> None:
        self._file.write(json.dumps(message) + "\n")
        self._file.flush()

    def send_raw(self, line: str) -> None:
        self._file.write(line + "\n")
        self._file.flush()

    def receive(self) -> dict:
        return json.loads(self._file.readline())

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
    def test_handshake_sends_hello_with_version(self):
        bridge = Bridge(accept_timeout=5)
        mod = connect(bridge)
        self.assertEqual(mod.received, [{"type": "hello", "protocol": PROTOCOL}])
        mod.close()

    def test_version_mismatch_names_both_versions(self):
        bridge = Bridge(accept_timeout=5)
        with self.assertRaisesRegex(BridgeError, f"the game speaks {PROTOCOL + 1}, the agent {PROTOCOL}"):
            connect(bridge, protocol=PROTOCOL + 1)

    def test_no_connection_times_out(self):
        with self.assertRaisesRegex(BridgeError, "did not connect within 0.2 seconds"):
            Bridge(accept_timeout=0.2).accept()

    def test_decision_answered_with_chosen_index_then_run_end_returned(self):
        bridge = Bridge(accept_timeout=5)
        mod = connect(bridge)
        mod.send(DECISION)
        mod.send({"type": "run_end", "outcome": "loss", "floor": 3})
        seen = []
        end = bridge.run(lambda decision: seen.append(decision) or 1)
        self.assertEqual(seen, [DECISION])
        self.assertEqual(mod.receive(), {"type": "action", "id": 1, "index": 1})
        self.assertEqual(end, {"type": "run_end", "outcome": "loss", "floor": 3})
        mod.close()

    def test_disconnect_before_run_end_fails(self):
        bridge = Bridge(accept_timeout=5)
        mod = connect(bridge)
        mod.send(DECISION)
        mod.close()
        with self.assertRaisesRegex(BridgeError, "closed the connection before the run ended"):
            bridge.run(lambda decision: 0)

    def test_line_that_is_not_json_fails(self):
        bridge = Bridge(accept_timeout=5)
        mod = connect(bridge)
        mod.send_raw("not json")
        with self.assertRaisesRegex(BridgeError, "not JSON"):
            bridge.run(lambda decision: 0)
        mod.close()

    def test_unknown_message_type_fails(self):
        bridge = Bridge(accept_timeout=5)
        mod = connect(bridge)
        mod.send({"type": "surprise"})
        with self.assertRaisesRegex(BridgeError, "expected decision or run_end, got 'surprise'"):
            bridge.run(lambda decision: 0)
        mod.close()


class RandomAgentTest(unittest.TestCase):
    """Runs random_agent.py as tools/run.sh does, against a fake mod."""

    def play(self, seed: int, decisions: int) -> list[int]:
        agent = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("random_agent.py")), "--seed", str(seed)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        port = int(agent.stdout.readline().removeprefix("port="))
        mod = FakeMod(port)
        indices = []
        for i in range(1, decisions + 1):
            mod.send({**DECISION, "id": i, "actions": [{"kind": "end_turn"}] * 5})
            answer = mod.receive()
            self.assertEqual(answer["id"], i)
            self.assertIn(answer["index"], range(5))
            indices.append(answer["index"])
        mod.send({"type": "run_end", "outcome": "loss", "floor": 2})
        out, err = agent.communicate(timeout=10)
        mod.close()
        self.assertEqual(agent.returncode, 0, err)
        self.assertRegex(out, rf"agent_seed={seed} decisions={decisions} per_second=[0-9.]+")
        return indices

    def test_same_seed_same_choices(self):
        self.assertEqual(self.play(seed=1, decisions=20), self.play(seed=1, decisions=20))

    def test_choices_follow_the_seed(self):
        expected = [random.Random(7).randrange(5) for _ in range(1)]
        self.assertEqual(self.play(seed=7, decisions=1), expected)


if __name__ == "__main__":
    unittest.main()
