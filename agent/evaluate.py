"""Evaluates a checkpoint, or the random agent, on the evaluation seeds (agent/env/seeds.py).

    python -m agent.evaluate runs/<training run>/checkpoint.pt [--games 4] [--modes best,sampled] [--seeds N]
    python -m agent.evaluate random [--games 4]

Every seed is played once per mode: "best", the policy's best action (the masked argmax), which is the official
result; "sampled", actions sampled from the policy; and for the random agent "random", a uniform legal action. A
seed's sampling uses a generator seeded from the seed and the mode, so the results do not depend on which game played
which seed, nor on how many games ran. The result goes to runs/eval-<time>/result.json: each seed's outcome, floor, act
and steps, and per mode the mean floor, win rate, share of runs past each act's boss and failed runs, with everything
that identifies what was measured.
"""

import argparse
import hashlib
import json
import logging
import queue
import shlex
import sys
import threading
from datetime import datetime
from pathlib import Path

import numpy as np
import torch

from agent.bridge import BridgeError
from agent.checkpoint import TrainingRun, _git, identities
from agent.env import games
from agent.env.environment import make_environments
from agent.env.seeds import evaluation_seeds, seeds_hash
from agent.env.vocabulary import Vocabulary
from agent.ppo.config import Config
from agent.ppo.model import Policy, as_tensors, masked

# An evaluation whose failed runs pass this share of its runs is not a measurement of the policy.
MAX_FAILED = 0.10
ACTS = 3

log = logging.getLogger(__name__)


def seed_generator(seed: str, mode: str) -> np.random.Generator:
    return np.random.default_rng(int.from_bytes(hashlib.sha256(f"{mode}:{seed}".encode()).digest()[:8], "little"))


def chooser(policy: Policy | None, mode: str):
    """A function (obs, mask, rng) -> action for the mode: the masked argmax, a sample, or a uniform legal action."""
    def choose(obs, mask, rng):
        if policy is None:
            return int(rng.choice(np.flatnonzero(mask)))
        with torch.inference_mode():
            logits, _ = policy(as_tensors({key: value[None] for key, value in obs.items()}))
        logits = masked(logits, torch.as_tensor(mask)[None])[0]
        if mode == "best":
            return int(torch.argmax(logits))
        probs = torch.softmax(logits, -1).double().numpy()
        return int(rng.choice(len(probs), p=probs / probs.sum()))
    return choose


def play(env, seed: str, mode: str, choose) -> dict:
    """One evaluation run of a seed. A run the game never starts, or that fails, is reported as failed."""
    rng = seed_generator(seed, mode)
    try:
        obs, info = env.reset(seed=seed, options={"evaluation": True})
    except BridgeError as e:
        return {"seed": seed, "mode": mode, "outcome": f"failed: the run did not start: {e}", "floor": 0, "act": 0,
                "steps": 0}
    steps = 0
    while True:
        obs, _, terminated, truncated, info = env.step(choose(obs, env.action_masks(), rng))
        steps += 1
        if terminated or truncated:
            return {"seed": seed, "mode": mode, "outcome": info["outcome"], "floor": info["floor"],
                    "act": info.get("act", 0), "steps": steps}


def play_all(envs: list, seeds: list[str], modes: list[str], policy: Policy | None) -> list[dict]:
    """Every seed in every mode, shared among the games; the rows come back in seed and mode order."""
    work: queue.Queue = queue.Queue()
    for mode in modes:
        for seed in seeds:
            work.put((seed, mode))
    rows: dict[tuple[str, str], dict] = {}
    errors: list[BaseException] = []
    choosers = {mode: chooser(policy, mode) for mode in modes}
    threads = torch.get_num_threads()
    torch.set_num_threads(1)  # one thread per game already

    def worker(env):
        try:
            while not errors:
                try:
                    seed, mode = work.get_nowait()
                except queue.Empty:
                    return
                rows[(seed, mode)] = play(env, seed, mode, choosers[mode])
        except BaseException as e:  # re-raised below, after every game stops
            errors.append(e)

    if policy is not None:
        policy.eval()
    workers = [threading.Thread(target=worker, args=(env,)) for env in envs]
    try:
        for thread in workers:
            thread.start()
        for thread in workers:
            thread.join()
    finally:
        torch.set_num_threads(threads)
    if errors:
        raise errors[0]
    return [rows[(seed, mode)] for mode in modes for seed in seeds]


def failed(row: dict) -> bool:
    return str(row["outcome"]).startswith("failed")


def summarize(rows: list[dict]) -> dict:
    """Per mode: runs, failed runs, and over the runs that did not fail the mean floor, win rate and the share past
    each act's boss (a run that reached the next act; act 3's boss is a win). Past MAX_FAILED, the mode is invalid."""
    summary = {}
    for mode in dict.fromkeys(row["mode"] for row in rows):
        own = [row for row in rows if row["mode"] == mode]
        played = [row for row in own if not failed(row)]
        n = len(played) or 1
        wins = sum(row["outcome"] == "win" for row in played)
        bosses = {f"act{act}_boss": sum(row["act"] > act for row in played) / n for act in range(1, ACTS)}
        bosses[f"act{ACTS}_boss"] = wins / n
        summary[mode] = {
            "runs": len(own), "failed": len(own) - len(played),
            "mean_floor": sum(row["floor"] for row in played) / n, "win_rate": wins / n, **bosses,
            "valid": (len(own) - len(played)) <= MAX_FAILED * len(own),
        }
    return summary


def evaluate(envs: list, policy: Policy | None, modes: list[str], vocabulary: Vocabulary,
             seeds: list[str] | None = None, about: dict | None = None) -> dict:
    """The full result of evaluating a policy (or the random agent, policy None)."""
    seeds = evaluation_seeds() if seeds is None else seeds
    rows = play_all(envs, seeds, modes, policy)
    try:
        build, version, _ = games.targeted()
    except (OSError, games.GameCopyError):
        build = version = None
    return {
        **(about or {}),
        "seeds": {"count": len(seeds), "hash": seeds_hash(seeds), "all": len(seeds) == len(evaluation_seeds())},
        "game_build": build, "game_version": version, "git_commit": _git("rev-parse", "HEAD"),
        **identities(vocabulary), "time": datetime.now().isoformat(timespec="seconds"),
        "summary": summarize(rows), "runs": rows,
    }


def load_policy(path: Path, vocabulary: Vocabulary) -> tuple[Policy, dict]:
    """A checkpoint's policy on the CPU, checked against the current code, and what identifies it."""
    run = TrainingRun(path.parent if path.parent.name != "generations" else path.parent.parent)
    run.checkpoint_file = path
    config = Config(**run.record()["config"])
    state = run.load(vocabulary)
    policy = Policy(len(vocabulary), config.embed, config.hidden, config.state)
    policy.load_state_dict(state["model"])
    return policy, {"checkpoint": str(path), "training_run": run.folder.name, "update": state["updates"],
                    "step": state["steps"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agent.evaluate", description=__doc__.splitlines()[0])
    parser.add_argument("checkpoint", help="a checkpoint .pt file, or 'random' for the random agent")
    parser.add_argument("--games", type=int, default=4, help="games to run at once (default 4)")
    parser.add_argument("--modes", default="best,sampled", help="for a checkpoint: best, sampled, or both (default)")
    parser.add_argument("--seeds", type=int, help="only the first N evaluation seeds (default all)")
    parser.add_argument("--game-command", help="a command to run instead of the game (the tests' fake game)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stderr)
    vocabulary = Vocabulary.load()
    if args.checkpoint == "random":
        policy, about, modes = None, {"checkpoint": "random"}, ["random"]
    else:
        policy, about = load_policy(Path(args.checkpoint), vocabulary)
        modes = args.modes.split(",")
    seeds = evaluation_seeds()[:args.seeds] if args.seeds else None
    out = Path("runs") / datetime.now().strftime("eval-%Y%m%d-%H%M%S")
    envs = make_environments(args.games, out, vocabulary=vocabulary,
                             game_command=shlex.split(args.game_command) if args.game_command else None)
    try:
        result = evaluate(envs, policy, modes, vocabulary, seeds, about)
    finally:
        for env in envs:
            env.close()
    (out / "result.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    for mode, summary in result["summary"].items():
        print(f"{mode}: mean floor {summary['mean_floor']:.2f}, win rate {summary['win_rate']:.3f}, "
              f"past act 1 boss {summary['act1_boss']:.3f}, act 2 {summary['act2_boss']:.3f}, "
              f"failed {summary['failed']}/{summary['runs']}{'' if summary['valid'] else ' (invalid)'}")
    print(f"result: {out / 'result.json'}")
    return 0 if all(summary["valid"] for summary in result["summary"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
