"""Makes every decision at random: a stand-in agent that exercises the bridge (specs 004 and 005).

    python agent/random_agent.py [--seed N] [--trace FILE]

Prints port=<n> once listening, for tools/run.sh, and at the end
agent_seed=<n> decisions=<n> per_second=<x>, where per_second is over the whole run.
With --trace, writes each decision and the answer given as one JSON line.
"""

import argparse
import contextlib
import json
import random
import sys
import time

from bridge import Bridge, BridgeError


def pick(decision: dict, rng: random.Random) -> int | list[int]:
    """A uniform choice: one action, or for card_select a uniform count of distinct cards within min and max."""
    if decision["kind"] == "card_select":
        select = decision["state"]["card_select"]
        cards = len(select["cards"])
        count = rng.randint(select["min"], min(select["max"], cards))
        return sorted(rng.sample(range(cards), count))
    return rng.randrange(len(decision["actions"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, help="seed for the choices (default: a new random one)")
    parser.add_argument("--trace", help="file to write each decision and choice to, as JSON lines")
    args = parser.parse_args()
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**31)
    rng = random.Random(seed)
    decisions = 0

    with open(args.trace, "w", encoding="utf-8") if args.trace else contextlib.nullcontext() as trace:

        def choose(decision: dict) -> int | list[int]:
            nonlocal decisions
            decisions += 1
            answer = pick(decision, rng)
            if trace:
                trace.write(json.dumps({"decision": decision, "answer": answer}) + "\n")
            return answer

        try:
            bridge = Bridge()
            print(f"port={bridge.port}", flush=True)
            bridge.accept()
            start = time.monotonic()
            bridge.run(choose)
        except BridgeError as e:
            print(f"agent: {e}", file=sys.stderr)
            return 1
    elapsed = time.monotonic() - start
    print(f"agent_seed={seed} decisions={decisions} per_second={decisions / elapsed:.1f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
