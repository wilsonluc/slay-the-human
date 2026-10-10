"""A fake game for the tests: speaks docs/protocol.md like the mod, with no game behind it.

It is launched exactly like the game (agent/env/games.py), with Python as the executable:

    python fake_game.py [--mode MODE] [--decisions N] --slay-the-human-run --slay-the-human-agent-port=<port> ...

After each start it plays recorded decisions (recordings/decisions.jsonl) in order, the first N of them, checks each
answer the way the mod does, then ends the run with run_end and waits at ready again. Modes make it misbehave:
hang (stops answering partway through a run), exit (quits partway through), version (another protocol version),
game-version (another game version), unknown (a card the vocabulary lacks), memory (allocates 400 MB and stops answering).
"""

import argparse
import json
import socket
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from agent.bridge import PROTOCOL  # noqa: E402
from agent.env.vocabulary import Vocabulary  # noqa: E402

RECORDINGS = HERE / "recordings" / "decisions.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="normal")
    parser.add_argument("--decisions", type=int, default=0, help="decisions per run (default: every recording)")
    parser.add_argument("--slay-the-human-agent-port", dest="port", type=int, required=True)
    parser.add_argument("--log-file", dest="log", required=True)
    args, _ = parser.parse_known_args()
    decisions = [json.loads(line) for line in RECORDINGS.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.decisions:
        decisions = decisions[:args.decisions]
    log = open(args.log, "w", encoding="utf-8")

    vocabulary = Vocabulary.load()
    sock = socket.create_connection(("127.0.0.1", args.port))
    file = sock.makefile("rw", encoding="utf-8", newline="\n")

    def send(message):
        file.write(json.dumps(message) + "\n")
        file.flush()

    def receive():
        line = file.readline()
        return json.loads(line) if line else None

    send({"type": "hello", "protocol": PROTOCOL + (1 if args.mode == "version" else 0),
          "game_version": "v0.0.0" if args.mode == "game-version" else vocabulary.game_version,
          "game_commit": "fake", "vocabulary": []})
    if receive() is None:
        return 0
    while True:
        send({"type": "ready"})
        start = receive()
        if start is None:
            return 0
        print(f"[SlayTheHuman] run start seed={start['seed']}", file=log, flush=True)
        for number, recorded in enumerate(decisions, start=1):
            if number == 2 and args.mode == "hang":
                time.sleep(3600)
            if number == 2 and args.mode == "memory":
                ballast = bytearray(400 * 2**20)  # noqa: F841, held while it hangs
                time.sleep(3600)
            if number == 2 and args.mode == "exit":
                print("[SlayTheHuman] run error: the fake game was told to quit", file=log, flush=True)
                return 1
            decision = {**recorded, "id": number}
            if args.mode == "unknown":
                decision = json.loads(json.dumps(decision).replace('"STRIKE_IRONCLAD"', '"NOT_A_CARD"'))
            send(decision)
            answer = receive()
            if answer is None or not valid(decision, answer):
                print(f"[SlayTheHuman] run error: bad answer {answer}", file=log, flush=True)
                return 1
        send({"type": "run_end", "outcome": "loss", "floor": decisions[-1]["state"]["run"]["floor"],
              "seed": start["seed"]})


def valid(decision: dict, answer: dict) -> bool:
    if answer.get("type") != "action" or answer.get("id") != decision["id"]:
        return False
    if decision["kind"] == "card_select":
        select = decision["state"]["card_select"]
        indices = answer.get("indices")
        return (isinstance(indices, list) and len(set(indices)) == len(indices) and
                select["min"] <= len(indices) <= select["max"] and all(0 <= i < len(select["cards"]) for i in indices)
                and indices == sorted(indices))
    return isinstance(answer.get("index"), int) and 0 <= answer["index"] < len(decision["actions"])


if __name__ == "__main__":
    sys.exit(main())
