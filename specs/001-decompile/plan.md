# 001: Plan

## Approach

A POSIX `sh` script, `tools/decompile.sh`, run from the repo root in Git Bash (the same shell as the git hooks):

1. Check Windows long paths are on (`LongPathsEnabled` under `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem`). Stop if not.
2. Find Steam: `STEAM_DIR` if set, else `SteamPath` under `HKCU\Software\Valve\Steam`.
3. Find the game: read every library path in `steamapps/libraryfolders.vdf` and take the one holding `steamapps/appmanifest_2868840.acf`. Read `buildid` and `installdir` from that manifest. The DLL is `common/<installdir>/data_sts2_windows_x86_64/sts2.dll`.
4. Compare `buildid` with the build ID in `GAME_VERSION.md`. Stop on a mismatch unless `--any-build` is given.
5. Run `dotnet tool restore`, then `dotnet tool run ilspycmd -p -o decompiled.new sts2.dll`. Write the build ID to `decompiled.new/BUILD`.
6. Only after a successful run, replace `decompiled/` with `decompiled.new/`, so a failed run leaves the previous output whole.

The decompiler is pinned in a local .NET tool manifest to ilspycmd `9.1.0.7988`, the last release built for .NET 8 (10.x and later need the .NET 10 SDK). `rollForward: true` lets it run on the .NET 9 runtime the repo needs anyway. A root `nuget.config` clears all package sources and adds only nuget.org, so a user's global feeds cannot break the restore.

## Changes

- `tools/decompile.sh`: the script.
- `tools/decompile.test.sh`: checks the failure paths with a fake `reg` and a fake Steam folder; needs no game.
- `.config/dotnet-tools.json`: pins ilspycmd.
- `nuget.config`: nuget.org only.
- `.gitignore`: ignore `decompiled/` and `decompiled.new/`.
- `.gitattributes`: check out `*.sh` with LF line endings, since `sh` breaks on CRLF.
- `README.md`: a setup step to run the script, and `decompiled/` and `tools/` in the layout.
- `CLAUDE.md`: read `decompiled/` (made by the script) before touching game hooks or state reading.
- `GAME_VERSION.md`: mark the build ID as checked by the script; drop the line about the older decompiled reference.

## Verification

- Writes `decompiled/` and exits 0 → run `sh tools/decompile.sh` with build 23811903 installed.
- Records the build, `git status` clean → `cat decompiled/BUILD` prints `23811903`; `git status --short` prints nothing new.
- Mismatch fails, leaves `decompiled/` whole; `--any-build` overrides → `tools/decompile.test.sh` with a fake manifest at another build; then the same with `--any-build` gets past the check.
- Game not found → `tools/decompile.test.sh` with `STEAM_DIR` pointing at an empty folder.
- Pinned, reproducible → `.config/dotnet-tools.json` names the exact version; two runs, then `diff -r` of the outputs prints nothing.
- Global NuGet config ignored → with a global NuGet package source that cannot be reached, the run still succeeds.
- Long paths off → `tools/decompile.test.sh` with a fake `reg` reporting `0x0`.
- Hook methods present → `grep` finds `static bool IsReleaseGame()` and `StartNewSingleplayerRun(` in `decompiled/MegaCrit.Sts2.Core.Nodes/NGame.cs` and `DebugOnlyGetState()` in `decompiled/MegaCrit.Sts2.Core.Runs/RunManager.cs`.
- Docs → `README.md` and `CLAUDE.md` name `tools/decompile.sh` and `decompiled/`.

## Risks

- A game update changes the DLL's folder name or the app layout → the script stops with the missing path, never decompiles a wrong file.
- ilspycmd output changes between versions → pinned to an exact version; a version bump is its own PR.
- The root `nuget.config` also applies to the mod's build later → its packages (Harmony, Godot.NET.Sdk) are on nuget.org.
