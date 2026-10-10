"""Finds the game copy for the targeted build and launches games from it.

Training and evaluation never run the Steam install, which Steam updates: they run a copy of the game folder per build,
made by tools/copy-game.sh, in games/<build>/ (STH_GAMES_DIR overrides the folder holding the copies). GAME_VERSION.md
records the build and the copy's hash, and a copy whose hash differs is refused. Steam starts one copy of an app at a
time, so each game is launched directly, with the app ID in its environment; Steam must be running for the game's
Steamworks start-up.

    python -m agent.env.games hash <folder>    prints a folder's hash, as GAME_VERSION.md records it
"""

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

APP_ID = 2868840
EXECUTABLE = "SlayTheSpire2.exe"
ROOT = Path(__file__).resolve().parents[2]
GAME_VERSION = ROOT / "GAME_VERSION.md"


class GameCopyError(Exception):
    """The game copy is missing, or is not the one GAME_VERSION.md records."""


def copy_hash(folder):
    """SHA-256 over every file's relative path and contents, except mods/, which tools/mod.sh installs into."""
    folder = Path(folder)
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        relative = path.relative_to(folder).as_posix()
        if relative.split("/", 1)[0] == "mods":
            continue
        digest.update(relative.encode() + b"\0")
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1 << 20), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _version_row(name, text):
    match = re.search(rf"^\| {re.escape(name)} \| ([^|]+?) \|", text, re.MULTILINE)
    if not match:
        raise GameCopyError(f"no '{name}' row in {GAME_VERSION.name}")
    return match.group(1).strip("` ")


def targeted():
    """The targeted Steam build ID, game version and copy hash, from GAME_VERSION.md."""
    text = GAME_VERSION.read_text(encoding="utf-8")
    return (_version_row("Slay the Spire 2 (Steam build ID)", text), _version_row("Slay the Spire 2 (game version)", text),
            _version_row("Game copy (hash)", text))


def games_dir():
    return Path(os.environ.get("STH_GAMES_DIR") or ROOT / "games")


def game_copy(check_hash=True):
    """The game copy's folder for the targeted build. Refuses a missing copy, or one whose hash differs."""
    build, _, want = targeted()
    folder = games_dir() / build
    if not (folder / EXECUTABLE).is_file():
        raise GameCopyError(f"no game copy for build {build} in {folder}; make it with sh tools/copy-game.sh")
    if check_hash and (got := copy_hash(folder)) != want:
        raise GameCopyError(f"the game copy in {folder} has hash {got}, but GAME_VERSION.md records {want}")
    return folder


def steam_running():
    if sys.platform != "win32":
        return False
    listing = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe", "/NH"], capture_output=True, text=True)
    return "steam.exe" in listing.stdout.lower()


def launch(port, log_file, time_scale=20, command=None, extra_args=()):
    """Launches one game in run mode with no window, connecting to the agent on port and logging to log_file.

    command replaces the game's executable (the tests launch a fake game this way); by default it is the game copy's.
    """
    env = dict(os.environ)
    if command is None:
        if not steam_running():
            raise GameCopyError("Steam is not running; the game needs it to start")
        command = [str(game_copy() / EXECUTABLE)]
        env["SteamAppId"] = env["SteamGameId"] = str(APP_ID)
    args = [*command, "--slay-the-human-run", f"--slay-the-human-agent-port={port}", "--headless",
            "--time-scale", str(time_scale), *extra_args, "--log-file", str(log_file)]
    return subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "hash":
        sys.exit("usage: python -m agent.env.games hash <folder>")
    print(copy_hash(sys.argv[2]))
