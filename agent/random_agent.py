"""Makes every decision at random: a stand-in agent that exercises the bridge and the game.

    python -m agent.random_agent [--runs N] [--seed N] [--game-seeds S1,S2,...] [--character ID] [--time-scale X]
                                 [--no-launch]

Launches one game from the game copy (agent/env/games.py) and plays N runs back to back in it. Prints seed=<n> first,
then one line per run: seed= character= outcome= floor= decisions= per_second= trace=, and at the end the totals.
Game seeds come from the agent seed, so the same --seed replays the same runs; --game-seeds fixes the first runs'.
Each run's choices depend only on the agent seed and that run's game seed, so a run replays the same wherever it falls.
--no-launch prints port=<n> and waits for a game launched some other way to connect. Game logs and traces go in
runs/<time>/.
"""

import argparse
import json
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from agent.bridge import Bridge, BridgeError
from agent.env import games

# The game's own seed alphabet: no I or O, which it reads as 1 and 0.
SEED_CHARACTERS = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
MESSAGE_TIMEOUT = 120.0


def game_seed(rng: random.Random) -> str:
    return "".join(rng.choice(SEED_CHARACTERS) for _ in range(10))


def pick(decision: dict, rng: random.Random) -> int | list[int]:
    """A uniform choice: one action, or for card_select a uniform count of distinct cards within min and max."""
    if decision["kind"] == "card_select":
        select = decision["state"]["card_select"]
        cards = len(select["cards"])
        count = rng.randint(select["min"], min(select["max"], cards))
        return sorted(rng.sample(range(cards), count))
    return rng.randrange(len(decision["actions"]))


def play_runs(bridge: Bridge, runs: int, agent_seed: int, character: str, out: Path, game_seeds: list[str] = ()):
    """Plays runs back to back on a connected game, then closes the connection. Yields one summary dict per run."""
    seeds = random.Random(agent_seed)
    for number in range(1, runs + 1):
        seed = game_seeds[number - 1] if number <= len(game_seeds) else game_seed(seeds)
        rng = random.Random(f"{agent_seed}/{seed}")
        trace_path = out / f"run-{number}.trace.jsonl"
        decisions = 0
        with trace_path.open("w", encoding="utf-8") as trace:

            def choose(decision: dict) -> int | list[int]:
                nonlocal decisions
                decisions += 1
                answer = pick(decision, rng)
                trace.write(json.dumps({"decision": decision, "answer": answer}) + "\n")
                return answer

            bridge.start(seed, character, MESSAGE_TIMEOUT)
            started = time.monotonic()
            end = bridge.play(choose, MESSAGE_TIMEOUT)
        elapsed = time.monotonic() - started
        yield {"seed": end.get("seed", seed), "character": character, "outcome": end["outcome"], "floor": end["floor"],
               "decisions": decisions, "per_second": decisions / elapsed if elapsed else 0.0, "trace": trace_path}
    # Close only once the game is back at the main menu, so it quits cleanly instead of failing a write.
    ready = bridge.receive(MESSAGE_TIMEOUT)
    if ready.get("type") != "ready":
        raise BridgeError(f"expected ready, got {ready.get('type')!r}")
    bridge.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=1, help="runs to play in one game process (default 1)")
    parser.add_argument("--seed", type=int, help="seed for the choices and game seeds (default: a new random one)")
    parser.add_argument("--game-seeds", default="", help="the first runs' game seeds, comma-separated (default: drawn from --seed)")
    parser.add_argument("--character", default="IRONCLAD", help="character ID (default IRONCLAD)")
    parser.add_argument("--time-scale", type=float, default=20, help="game speed (default 20)")
    parser.add_argument("--no-launch", action="store_true", help="wait for a game launched some other way")
    args = parser.parse_args()
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**31)
    out = Path("runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    # The seed first, so runs that fail can still be replayed.
    print(f"seed={seed}", flush=True)

    bridge = Bridge()
    game = None
    log = out / "game.log"
    total_decisions, began = 0, time.monotonic()
    try:
        if args.no_launch:
            print(f"port={bridge.port}", flush=True)
        else:
            game = games.launch(bridge.port, log.resolve(), args.time_scale)
        bridge.accept()
        game_seeds = [s for s in args.game_seeds.split(",") if s]
        for run in play_runs(bridge, args.runs, seed, args.character, out, game_seeds):
            total_decisions += run["decisions"]
            print(" ".join(f"{key}={value:.1f}" if isinstance(value, float) else f"{key}={value}"
                           for key, value in run.items()), flush=True)
        if game and (code := game.wait(timeout=60)) != 0:
            raise BridgeError(f"the game exited with code {code}")
    except (BridgeError, TimeoutError, games.GameCopyError, subprocess.TimeoutExpired) as e:
        print(f"agent: {e or type(e).__name__}", file=sys.stderr)
        if log.exists():
            errors = [line for line in log.read_text(encoding="utf-8", errors="replace").splitlines()
                      if "run error" in line or "RunFailed" in line]
            for line in errors[-3:]:
                print(f"game: {line}", file=sys.stderr)
        return 1
    finally:
        if game and game.poll() is None:
            game.kill()
    elapsed = time.monotonic() - began
    print(f"agent_seed={seed} runs={args.runs} decisions={total_decisions} per_second={total_decisions / elapsed:.1f} "
          f"log={log}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
