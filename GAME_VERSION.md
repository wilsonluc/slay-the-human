# Game version

The game build this repo targets. Game updates can rename or change the methods the mod hooks into. When the game updates, re-check the hooks and update this file in the same PR.

| Item | Version | Source |
|------|---------|--------|
| Slay the Spire 2 (Steam build ID) | 23811903 | `buildid` in Steam's `appmanifest_2868840.acf`. `tools/decompile.sh` and `tools/mod.sh` check the installed game against it. |
| Slay the Spire 2 (game version) | v0.107.1 | `version` in the game's `release_info.json` |
| Godot (MegaDot) | 4.5.1 | Assembly version of the game's `GodotSharp.dll` (4.5.1.0) |
| .NET | 9.0.7 (`net9.0`) | `Microsoft.NETCore.App` in the game's `sts2.runtimeconfig.json`. The game ships this runtime, and the mod runs on it. |

When the game updates, decompile the new build with `sh tools/decompile.sh --any-build`, re-check the hooks against it, then update the versions here.

To keep a long training run from breaking mid-way, set Steam to update the game only when it is launched.
