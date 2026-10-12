"""The evaluation seeds (evaluation_seeds.json): a fixed list that training never plays, so every checkpoint is
measured on the same dungeons. The file says how the list was made."""

import hashlib
import json
from pathlib import Path

FILE = Path(__file__).with_name("evaluation_seeds.json")


def evaluation_seeds() -> list[str]:
    return json.loads(FILE.read_text(encoding="utf-8"))["seeds"]


def seeds_hash(seeds: list[str] | None = None) -> str:
    """SHA-256 of the seeds in order: an evaluation names the set it was measured on."""
    return hashlib.sha256("\n".join(evaluation_seeds() if seeds is None else seeds).encode()).hexdigest()


EVALUATION = frozenset(evaluation_seeds())
