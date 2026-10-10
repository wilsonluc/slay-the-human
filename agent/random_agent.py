"""Picks every action at random among the legal ones: the baseline agent, and the speed command for the environment.

    python -m agent.random_agent [--games N] [--runs R] [--seed S] [--character ID] [--trace-every K]
                                 [--think-seconds T --think-count C] [--time-scale X] [--game-command CMD]
    python -m agent.random_agent --replay runs/<time>/summary.jsonl --row I

Launches N games from the game copy (one environment each, start-ups staggered) and plays R runs in all across them,
one thread per game. Prints seed=<n> first, a line per run, then steps per second (per game and in total), runs per
hour, the mean and largest floor, and the largest size seen of each observation set. Each run's choices depend only on
the agent seed and that run's game seed, so a run replays the same wherever it falls. --think-seconds T --think-count C
sleeps T seconds before each of the first C actions, to check the game waits. --replay plays a summary row's seed and
action indices again and checks the outcome, floor and steps match. Records go in runs/<time>/.
"""

import argparse
import json
import logging
import random
import shlex
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from agent.env.environment import Environment, make_environments


def pick(mask: np.ndarray, rng: random.Random) -> int:
    """A uniform choice among the legal actions."""
    return int(rng.choice(np.flatnonzero(mask).tolist()))


class Think:
    """Sleeps before each of the first few actions, across every game."""

    def __init__(self, seconds: float, count: int) -> None:
        self._lock, self._seconds, self._left = threading.Lock(), seconds, count

    def __call__(self) -> None:
        with self._lock:
            if self._left <= 0:
                return
            self._left -= 1
        time.sleep(self._seconds)


def play(env: Environment, agent_seed: int, think: Think) -> dict:
    """One run with random actions; returns its summary."""
    obs, info = env.reset()
    rng = random.Random(f"{agent_seed}/{info['seed']}")
    steps, started = 0, time.monotonic()
    while True:
        think()
        obs, reward, terminated, truncated, info = env.step(pick(env.action_masks(), rng))
        steps += 1
        if terminated or truncated:
            elapsed = time.monotonic() - started
            return {"game": env.name, "seed": info["seed"], "outcome": info["outcome"], "floor": info["floor"],
                    "steps": steps, "per_second": steps / elapsed if elapsed else 0.0}


def replay(path: str, row: int, args) -> int:
    record = json.loads(Path(path).read_text(encoding="utf-8").splitlines()[row])
    env = Environment(Path(path).parent / "replay", character=args.character, time_scale=args.time_scale,
                      game_command=shlex.split(args.game_command) if args.game_command else None)
    try:
        env.reset(seed=record["seed"])
        for steps, action in enumerate(record["actions"], start=1):
            obs, reward, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
    finally:
        env.close()
    got = (info["outcome"], info["floor"], steps)
    want = (record["outcome"], record["floor"], record["steps"])
    print(f"replay seed={record['seed']} outcome={got[0]} floor={got[1]} steps={got[2]} matches={got == want}")
    return 0 if got == want else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--games", type=int, default=1, help="games to run at once (default 1)")
    parser.add_argument("--runs", type=int, default=1, help="runs to play in all (default 1)")
    parser.add_argument("--seed", type=int, help="agent seed (default: a new random one)")
    parser.add_argument("--character", default="IRONCLAD", help="character ID (default IRONCLAD)")
    parser.add_argument("--trace-every", type=int, default=100, help="keep a full trace of one in this many runs")
    parser.add_argument("--think-seconds", type=float, default=0.0, help="seconds to sleep before each of the first actions")
    parser.add_argument("--think-count", type=int, default=0, help="how many actions to sleep before (default 0)")
    parser.add_argument("--time-scale", type=float, default=20, help="game speed (default 20)")
    parser.add_argument("--game-command", help="a command to run instead of the game (the tests' fake game)")
    parser.add_argument("--replay", help="a summary.jsonl to replay a row of")
    parser.add_argument("--row", type=int, default=0, help="the row of --replay, from 0")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    if args.replay:
        return replay(args.replay, args.row, args)

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**31)
    print(f"seed={seed}", flush=True)
    out = Path("runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
    began = time.monotonic()
    envs = make_environments(args.games, out, seed=seed, character=args.character, trace_every=args.trace_every,
                             time_scale=args.time_scale,
                             game_command=shlex.split(args.game_command) if args.game_command else None)
    launched = time.monotonic()
    lock, left, results, errors = threading.Lock(), [args.runs], [], []
    think = Think(args.think_seconds, args.think_count)

    def worker(env: Environment) -> None:
        try:
            while True:
                with lock:
                    if left[0] == 0:
                        return
                    left[0] -= 1
                result = play(env, seed, think)
                with lock:
                    results.append(result)
                    print(" ".join(f"{k}={v:.1f}" if isinstance(v, float) else f"{k}={v}" for k, v in result.items()),
                          flush=True)
        except Exception as e:  # reported below; the other games finish their runs
            errors.append(f"{env.name}: {type(e).__name__}: {e}")

    threads = [threading.Thread(target=worker, args=(env,)) for env in envs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for env in envs:
        env.close()
    elapsed = time.monotonic() - launched
    steps = sum(r["steps"] for r in results)
    floors = [r["floor"] for r in results]
    largest: dict[str, int] = {}
    for env in envs:
        for name, size in env.encoder.largest.items():
            largest[name] = max(largest.get(name, 0), size)
    print(f"agent_seed={seed} games={args.games} runs={len(results)} steps={steps} "
          f"steps_per_second={steps / elapsed:.1f} per_game={steps / elapsed / args.games:.1f} "
          f"runs_per_hour={len(results) / elapsed * 3600:.0f} mean_floor={np.mean(floors) if floors else 0:.1f} "
          f"max_floor={max(floors, default=0)} launch_seconds={launched - began:.0f} out={out}", flush=True)
    print("largest " + " ".join(f"{name}={size}" for name, size in sorted(largest.items())), flush=True)
    for error in errors:
        print(f"agent: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
