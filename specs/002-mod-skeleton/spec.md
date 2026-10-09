# 002: Mod skeleton

Status: approved

## Problem

The agent plays through a mod running inside the game: reading state, taking actions and controlling speed all depend on it. Before writing any of that, the repo needs proof that it can build a mod the targeted build loads, and that the mod's Harmony patches apply.

The game has its own mod loader. It reads `mods/<id>/` next to the game's executable: a `<id>.json` manifest, a `<id>.dll`, and an optional `<id>.pck`. It loads mods only after the player has accepted the game's mods warning once. Nothing in the repo uses this yet.

## Goal

One command builds the mod against the installed game and installs it into the game's `mods` folder. Launching the game loads the mod, and a Harmony patch from it runs, both visible in the game's log.

## Non-goals

- Reading game state, taking actions, the bridge to Python, headless mode, game speed and starting runs. Later specs build on this one.
- A `.pck`. The mod is a DLL and its manifest only.
- Steam Workshop publishing.
- Linux and macOS.
- Accepting the game's mods warning automatically. It is a one-time step in the game's menu.

## Acceptance criteria

- [ ] With build 23811903 installed, one command run from the repo root builds the mod and installs it into `<game>/mods/`, and exits 0.
- [ ] The build references the game's assemblies in the install folder. No game file is copied into the repo, and `git status` shows nothing new after a build.
- [ ] When the installed build differs from `GAME_VERSION.md`, the command exits non-zero, names both build IDs, and installs nothing.
- [ ] The installed mod folder holds only the manifest and the DLL.
- [ ] After the mods warning has been accepted once, launching the game logs that the mod finished loading, with no mod errors.
- [ ] A Harmony patch from the mod runs: the game's log shows a line the patch writes when the game reaches the main menu.
- [ ] A patch that fails to apply stops the mod at startup: the game's log shows an error naming the patch, and the mod writes no further lines.
- [ ] `README.md` says how to build and install the mod, and how to accept the mods warning the first time.
- [ ] The Godot and .NET rows in `GAME_VERSION.md` give versions read from the installed game's own files.

## Open questions

