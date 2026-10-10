# 002: Plan

## Approach

**Finding the game.** The Steam and game lookup and the build check move out of `tools/decompile.sh` into `tools/game.sh`, which both scripts source. It sets the game folder, its data folder (`data_sts2_windows_x86_64`) and the installed build, and stops on a build mismatch unless `--any-build` is given.

**The mod.** A plain `Microsoft.NET.Sdk` class library in `mod/`, targeting `net9.0` (the game ships .NET 9.0.7). No Godot SDK, since there is no `.pck`. It references `sts2.dll`, `GodotSharp.dll` and `0Harmony.dll` from the game's data folder, passed in as the MSBuild property `GameDataDir`, with `Private=false` so none is copied to the output. The build fails with a clear error when `GameDataDir` is missing.

- Mod ID and assembly name: `SlayTheHuman`. The game loads `mods/SlayTheHuman/SlayTheHuman.json` and `SlayTheHuman.dll`.
- The manifest sets `has_dll: true` and `has_pck: false`. The game reads only snake_case keys, and without `has_dll` it skips the DLL with a warning, not an error.
- Entry point: a class marked with the game's `[ModInitializer("Init")]`, so the game calls `Init` instead of its own `Harmony.PatchAll`. `Init` applies each `[HarmonyPatch]` class one at a time. If one throws, it removes every patch the mod applied, logs an error naming the failing class, and rethrows, so the game marks the mod as failed. Otherwise it logs how many patch classes it applied.
- One patch: a postfix on `NMainMenu._Ready` that logs a line when the main menu is ready.
- Every line the mod logs goes through the game's `Log` and starts with `[SlayTheHuman]`, so it lands in the game's `godot.log`.

**Installing.** `tools/mod.sh [--any-build]` finds the game, checks the build, runs `dotnet build mod -c Release -p:GameDataDir=<data folder>`, then replaces `<game>/mods/SlayTheHuman/` with a folder holding only the manifest and the DLL.

**The mods warning.** The game loads mods only after the player has accepted its mods warning once. The README tells the user to launch the game after the first install and accept it.

## Changes

- `tools/game.sh`: shared lookup of Steam, the game and its build, and the build check.
- `tools/decompile.sh`: sources `tools/game.sh`.
- `tools/mod.sh`: builds and installs the mod.
- `tools/decompile.test.sh` becomes `tools/test.sh`: the existing checks, plus `tools/mod.sh` installing nothing on a build mismatch, and the manifest declaring `has_dll: true` and `has_pck: false`.
- `mod/SlayTheHuman.csproj`, `mod/SlayTheHuman.json`, `mod/ModEntry.cs`, `mod/MainMenuReady.cs`: the mod.
- `README.md`: how to build and install the mod and accept the mods warning; `mod/` in the layout.
- `GAME_VERSION.md`: Godot from `GodotSharp.dll` (assembly version 4.5.1.0), .NET from `sts2.runtimeconfig.json` (9.0.7), and the game's own version from `release_info.json` (v0.107.1).

## Verification

- Builds and installs, exits 0 → `sh tools/mod.sh` with build 23811903 installed.
- No game files in the repo → the build output holds only `SlayTheHuman.dll` (and its `.pdb`); `git status --short` prints nothing new.
- Mismatch installs nothing → `tools/test.sh` with a fake Steam install at another build: exit 1, both build IDs named, no `mods/` folder created.
- Mod folder holds only the manifest and the DLL → `ls <game>/mods/SlayTheHuman`.
- Mod loads with no errors → launch the game, accept the mods warning; `godot.log` shows `Finished mod initialization for 'Slay the Human' (SlayTheHuman)` and no `[ERROR]` line naming the mod.
- Patch runs → `godot.log` shows `[SlayTheHuman] main menu ready`.
- Failing patch stops the mod → temporarily add a patch on a method `NMainMenu` does not have, install, launch: `godot.log` shows the `[SlayTheHuman]` error naming that patch class and no `main menu ready` line. Remove the patch afterwards.
- Docs → `README.md` covers build, install and the warning; `GAME_VERSION.md` rows name the game files they come from.

## Risks

- The game loads mods before the menu and only once → a change needs a game restart; `tools/mod.sh` says so.
- A game update renames `NMainMenu._Ready` → the patch fails, the mod stops with an error naming the patch, per `STANDARDS.md`.
- Installing while the game runs → Windows locks the loaded DLL and the copy fails loudly; close the game first.
