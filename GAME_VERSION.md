# Game version

The game build this repo targets. Game updates can rename or change the methods the mod hooks into. When the game updates, re-check the hooks and update this file in the same PR.

| Item | Version | Source |
|------|---------|--------|
| Slay the Spire 2 (Steam build ID) | 23811903 | `buildid` in Steam's `appmanifest_2868840.acf`. `tools/decompile.sh` checks the installed game against it. |
| Godot (MegaDot) | 4.5.1 | sts2-rl-agent `STS2BridgeMod.csproj`. The game rejects a mod `.pck` built with a newer Godot. |
| .NET | 9 (`net9.0`) | sts2-rl-agent `STS2BridgeMod.csproj` |

When the game updates, decompile the new build with `sh tools/decompile.sh --any-build`, re-check the hooks against it, then update the build ID here.

To keep a long training run from breaking mid-way, set Steam to update the game only when it is launched.
