"""A training run's folder, runs/<training run>/: its record (config.json), its metrics (metrics.csv) and its latest
checkpoint (checkpoint.pt). The games' logs, traces and summary.jsonl go in the same folder.

config.json records everything that produced the run: the config, the seed, the git commit and whether the tree was
dirty, the game build, and the vocabulary, schema, protocol and reward identities. A checkpoint carries the same
identities and refuses to load where the current code differs, naming each difference. The one migration: a vocabulary
that has only grown since the checkpoint, which loads with an embedding row added for each new value.
"""

import csv
import io
import json
import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path

import torch

from agent.bridge import PROTOCOL
from agent.env import encoding, games, reward
from agent.env.vocabulary import Vocabulary

ROOT = Path(__file__).resolve().parents[1]


class CheckpointMismatch(Exception):
    """A checkpoint was made by code whose vocabulary, schema, protocol or reward differ from the current code's."""


def identities(vocabulary: Vocabulary) -> dict:
    return {"vocabulary": vocabulary.hash, "schema": encoding.schema_hash(), "protocol": PROTOCOL,
            "reward": reward.definition_hash()}


def _git(*args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


class TrainingRun:
    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        self.config_file = self.folder / "config.json"
        self.metrics_file = self.folder / "metrics.csv"
        self.checkpoint_file = self.folder / "checkpoint.pt"

    @classmethod
    def create(cls, config: dict, vocabulary: Vocabulary, root: Path = Path("runs")) -> "TrainingRun":
        run = cls(Path(root) / datetime.now().strftime("%Y%m%d-%H%M%S"))
        run.folder.mkdir(parents=True)
        try:
            build, version, _ = games.targeted()
        except (OSError, games.GameCopyError):
            build = version = None
        record = {
            "config": config,
            "seed": config["seed"],
            "git_commit": _git("rev-parse", "HEAD"),
            "git_dirty": _git("status", "--porcelain") != "",
            "game_build": build,
            "game_version": version,
            **identities(vocabulary),
            "python": platform.python_version(),
            "torch": torch.__version__,
            "started": datetime.now().isoformat(timespec="seconds"),
        }
        run.config_file.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return run

    def record(self) -> dict:
        return json.loads(self.config_file.read_text(encoding="utf-8"))

    # Metrics

    def write_metrics(self, row: dict) -> None:
        """Appends one row as one line, flushed and synced, so a kill at any moment leaves whole rows. The first row
        writes the header."""
        new = not self.metrics_file.exists() or self.metrics_file.stat().st_size == 0
        line = io.StringIO()
        writer = csv.DictWriter(line, fieldnames=list(row), lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerow(row)
        with self.metrics_file.open("a", encoding="utf-8", newline="") as file:
            file.write(line.getvalue())
            file.flush()
            os.fsync(file.fileno())

    def trim_metrics(self, update: int) -> None:
        """Keeps the rows up to update (the checkpoint's), dropping rows for steps that will be collected again and a
        row cut short by a kill."""
        if not self.metrics_file.exists():
            return
        text = self.metrics_file.read_text(encoding="utf-8")
        lines = text.split("\n")
        if not lines or not lines[0]:
            return
        header = lines[0].split(",")
        kept = [lines[0]]
        for line in lines[1:]:
            fields = next(csv.reader([line]), [])
            if len(fields) != len(header):
                continue  # cut short, or the empty string after the last newline
            if int(fields[header.index("update")]) <= update:
                kept.append(line)
        temporary = self.metrics_file.with_suffix(".tmp")
        temporary.write_text("\n".join(kept) + "\n", encoding="utf-8")
        os.replace(temporary, self.metrics_file)

    # Checkpoints

    def save(self, state: dict) -> None:
        """Writes the checkpoint to a temporary file, then replaces the last one."""
        temporary = self.checkpoint_file.with_suffix(".tmp")
        torch.save(state, temporary)
        os.replace(temporary, self.checkpoint_file)

    def load(self, vocabulary: Vocabulary) -> dict:
        """The latest checkpoint, checked against the current code, with a grown vocabulary migrated."""
        state = torch.load(self.checkpoint_file, weights_only=False)
        current = identities(vocabulary)
        mismatches = [f"{name}: checkpoint {state['identities'][name]}, current {value}"
                      for name, value in current.items() if state["identities"][name] != value]
        keys = state["vocabulary_keys"]
        grown = len(keys) < len(vocabulary.keys) and vocabulary.keys[:len(keys)] == keys
        if grown:
            mismatches = [m for m in mismatches if not m.startswith("vocabulary:")]
        if mismatches:
            raise CheckpointMismatch("the checkpoint does not match the current code: " + "; ".join(mismatches))
        if grown:
            _grow_embedding(state, len(keys), len(vocabulary.keys))
        return state


def _grow_embedding(state: dict, old: int, new: int) -> None:
    """Adds an embedding row for each value the vocabulary gained, initialised like the rest (normal, as nn.Embedding
    does), and zero optimiser moments for them. The embedding is the model's first parameter (Policy registers it
    first), so its optimiser state is entry 0."""
    weight = state["model"]["embedding.weight"]
    rows = torch.randn(new - old, weight.shape[1], dtype=weight.dtype)
    state["model"]["embedding.weight"] = torch.cat([weight, rows])
    moments = state["optimizer"]["state"].get(0, {})
    for name, value in moments.items():
        if torch.is_tensor(value) and value.shape == weight.shape:
            moments[name] = torch.cat([value, value.new_zeros(new - old, value.shape[1])])
