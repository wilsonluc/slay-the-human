# Game version

The game build this repo targets. Game updates can rename or change the methods the mod hooks into. When the game updates, re-check the hooks and update this file in the same PR.

| Item | Version | Source |
|------|---------|--------|
| Slay the Spire 2 (Steam build ID) | 23811903 | `buildid` in Steam's `appmanifest_2868840.acf`. `tools/decompile.sh` and `tools/mod.sh` check the installed game against it. |
| Slay the Spire 2 (game version) | v0.107.1 | `version` in the game's `release_info.json` |
| Game copy (hash) | `ec7120083d45524a79d255b4356c4902027ada2c95969b7dd792f510a6fcba5d` | Printed by `tools/copy-game.sh`: SHA-256 over every file of the copy in `games/<build>/` except `mods/`. The environment refuses a copy whose hash differs. |
| Godot (MegaDot) | 4.5.1 | Assembly version of the game's `GodotSharp.dll` (4.5.1.0) |
| .NET | 9.0.7 (`net9.0`) | `Microsoft.NETCore.App` in the game's `sts2.runtimeconfig.json`. The game ships this runtime, and the mod runs on it. |

When the game updates, decompile the new build with `sh tools/decompile.sh --any-build`, re-check the hooks against it, then update the versions here.

Training and evaluation run a copy of the game per build, which Steam never updates (`sh tools/copy-game.sh`), so a game update cannot change the game under a training run. After an update, copy the new build alongside the old one.
