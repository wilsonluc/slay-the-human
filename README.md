# slay-the-human

A reinforcement learning agent for **Slay the Spire 2**. It plays the game headless and trains with PPO, with a strong focus on self-improvement.

## Goals

- Play the real game headless through a mod bridge. The mod reads game state and executes the agent's actions.
- Speed the game up as far as possible for faster training.
- Build PPO from the ground up.
- Make the agent improve through self-play over time.

## Layout

- `STANDARDS.md` — coding standards (DRY, YAGNI).
- `CONTEXT.md` — glossary of game and training terms.
- `GAME_VERSION.md` — the game build, Godot, and .NET versions this repo targets.
- `.githooks/` — git hooks; enable with `git config core.hooksPath .githooks`.
- `specs/` — feature specs. Every feature starts as a spec; see `specs/README.md` for the process.
- `.scrape/` (gitignored, local only) — reference material taken from [sts2-rl-agent](https://github.com/zhiyue/sts2-rl-agent): the C# bridge mod, decompiled game source, a Python simulator, and docs. See `.scrape/NOTES.md`.

## Credits

This project builds on [zhiyue/sts2-rl-agent](https://github.com/zhiyue/sts2-rl-agent). That project's bridge mod, decompilation work, game-systems documentation, and Python simulator are the starting reference here. The code in this repo is written from scratch.

## License

MIT, see [LICENSE](LICENSE). The license covers this repo's own code only.

Slay the Spire 2 is the property of Mega Crit Games. This repo contains no game files, assets, or decompiled game code. You need your own copy of the game to use it. This project is for research and educational purposes.
