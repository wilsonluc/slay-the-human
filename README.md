# slay-the-human

A reinforcement learning agent for **Slay the Spire 2**. It plays the game headless and trains with PPO, with a strong focus on self-improvement.

## Goals

- Play the real game headless through a mod bridge. The mod reads game state and executes the agent's actions.
- Speed the game up as far as possible for faster training.
- Build PPO from the ground up.
- Make the agent improve through self-play over time.

## Setup

You need `git`, the GitHub CLI `gh`, and [Claude Code](https://claude.com/claude-code).

1. Log in to GitHub: `gh auth login`.
2. Clone and enable the repo's git hooks. The pre-push hook blocks direct pushes to `main`.
   ```
   gh repo clone wilsonluc/slay-the-human
   cd slay-the-human
   git config core.hooksPath .githooks
   ```
3. Start Claude Code in the repo (`claude`) and trust the folder when asked. `.claude/settings.json` registers the [pr-tools](https://github.com/wilsonluc/pr-tools) marketplace and enables two plugins:
   - `pr-reviewer@pr-tools` reviews each PR against its built-in standards, `STANDARDS.md` and `CLAUDE.md`, and looks for bugs.
   - `pr-addresser@pr-tools` works through review conversations: it checks each finding, fixes the confirmed ones, and replies to the rest.

   Accept the prompt to install them. If no prompt appears, install them by hand:
   ```
   /plugin marketplace add wilsonluc/pr-tools
   /plugin install pr-reviewer@pr-tools
   /plugin install pr-addresser@pr-tools
   ```
4. Check with `/plugin`: both plugins should show as enabled.

Personal Claude Code settings go in `.claude/settings.local.json`, which is gitignored.

## Layout

- `STANDARDS.md` — project-specific coding standards, on top of the generic [standards built into pr-reviewer](https://github.com/wilsonluc/pr-tools/blob/main/plugins/pr-reviewer/standards.md).
- `.claude/settings.json` — shared Claude Code settings: the pr-tools plugins.
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
