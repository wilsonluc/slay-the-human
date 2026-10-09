# Game version

The game build this repo targets. Game updates can rename or change the methods the mod hooks into. When the game updates, re-check the hooks and update this file in the same PR.

| Item | Version | Source |
|------|---------|--------|
| Slay the Spire 2 (Steam build ID) | 23811903 | Steam → game Properties → Updates. Not yet verified against the installed files. |
| Godot (MegaDot) | 4.5.1 | sts2-rl-agent `STS2BridgeMod.csproj`. The game rejects a mod `.pck` built with a newer Godot. |
| .NET | 9 (`net9.0`) | sts2-rl-agent `STS2BridgeMod.csproj` |

The decompiled reference in `.scrape/decompiled/` is from a build of about May 2026, which may be older than the build above. Re-decompile before relying on it.

To keep a long training run from breaking mid-way, set Steam to update the game only when it is launched.
