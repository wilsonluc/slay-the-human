# 001: Decompile the game

Status: done

## Problem

The mod patches methods in `sts2.dll` and reads game state from its classes, so writing it needs the game's source. Mega Crit owns that source: this public repo cannot hold it, and every contributor has to make it from their own copy of the game.

Game updates rename and change the methods the mod hooks, so the source has to match the build the repo targets. Without one shared way to decompile, each person uses their own tool version and build, and nobody can tell which build their source came from.

## Goal

One command decompiles the installed `sts2.dll` into a gitignored folder of C# source, labelled with the Steam build ID it came from, and refuses a build other than the one in `GAME_VERSION.md` unless told otherwise.

## Non-goals

- Extracting the game's `.pck` (art, audio, scenes, localization). The agent reads everything through `sts2.dll`.
- Linux and macOS. The command targets Windows, where the game and the training run.
- Committing decompiled source or game binaries.
- Updating `GAME_VERSION.md` or diffing two builds' source. Those stay manual.

## Acceptance criteria

- [x] With build 23811903 installed in any Steam library, one command, run from the repo root with no arguments, writes the decompiled C# of `sts2.dll` to `decompiled/` and exits 0.
- [x] `decompiled/` holds a file recording the Steam build ID it was made from, and `git status` shows nothing new after a run.
- [x] When the installed build differs from `GAME_VERSION.md`, the command exits non-zero, names both build IDs, and leaves an existing `decompiled/` untouched. With an explicit override flag it decompiles anyway and records the installed build.
- [x] When the game cannot be found, the command exits non-zero and says how to point it at the Steam folder.
- [x] The decompiler's exact version is pinned in the repo. Two runs on the same build produce identical `decompiled/` folders.
- [x] The command works whatever package sources the user's global NuGet config lists.
- [x] When Windows long paths are off, the command exits non-zero before decompiling and says how to turn them on, so no files are silently lost.
- [x] `NGame.IsReleaseGame()`, `NGame.StartNewSingleplayerRun(...)` and `RunManager.DebugOnlyGetState()` are present in the output for build 23811903.
- [x] `README.md` and `CLAUDE.md` say how to run the command and where its output goes.

## Open questions

