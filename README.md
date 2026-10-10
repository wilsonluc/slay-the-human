# slay-the-human

A reinforcement learning agent for **Slay the Spire 2**. It plays the game headless and trains with PPO, with a strong focus on self-improvement.

## Goals

- Play the real game headless through a mod bridge. The mod reads game state and executes the agent's actions.
- Speed the game up as far as possible for faster training.
- Build PPO from the ground up.
- Make the agent improve through self-play over time.

## Setup

You need Windows, `git` (with Git Bash), the GitHub CLI `gh`, the [.NET 9 SDK](https://dotnet.microsoft.com/download/dotnet/9.0), [Claude Code](https://claude.com/claude-code), and Slay the Spire 2 installed through Steam.

1. Log in to GitHub: `gh auth login`.
2. Clone and enable the repo's git hooks. The pre-push hook blocks direct pushes to `main`.
   ```
   gh repo clone wilsonluc/slay-the-human
   cd slay-the-human
   git config core.hooksPath .githooks
   ```
3. Install the [pr-tools](https://github.com/wilsonluc/pr-tools) plugins in Claude Code. They install at user scope, so they apply in every repo:
   ```
   /plugin marketplace add wilsonluc/pr-tools
   /plugin install pr-reviewer@pr-tools
   /plugin install pr-addresser@pr-tools
   ```
   - `pr-reviewer` reviews each PR against its built-in standards, `STANDARDS.md` and `CLAUDE.md`, and looks for bugs.
   - `pr-addresser` works through review conversations: it checks each finding, fixes the confirmed ones, and replies to the rest.
4. Check with `/plugin`: both plugins should show as enabled.
5. Decompile the game: `sh tools/decompile.sh`. It checks the installed build against `GAME_VERSION.md` and writes the game's C# source to `decompiled/`. That code is Mega Crit's: it is gitignored and never committed.
6. Build and install the mod, with the game closed: `sh tools/mod.sh`. It builds `mod/` against the game's own assemblies and installs it into the game's `mods/SlayTheHuman/` folder.
7. The first time, start the game and answer **Yes** to its mods warning. The game saves the answer and quits. From the next start, it loads the mod, and `%APPDATA%\SlayTheSpire2\logs\godot.log` shows lines starting `[SlayTheHuman]`.

## Unattended runs

With Steam running and the game closed, `sh tools/run.sh` plays one full run with nobody at the keyboard. It starts the random Python agent (`agent/random_agent.py`, Python 3.13 with the packages in `pyproject.toml`; install them with `pip install -e .`), then launches the game through Steam with no window and at 20x game speed. The agent makes every decision in the run (combat, map, rewards, card rewards, rest sites, card selections, events, shops, treasure, bundles and the Crystal Sphere) over the bridge described in `docs/protocol.md`, and the mod carries out its choices the way a player would. The game's built-in AutoSlay bot only drives the screens around them: menus, dialogue and transitions. It prints one line:

```
seed=TEST1 character=IRONCLAD outcome=loss floor=4 seconds=30 agent_seed=1 decisions=50 per_second=7.3 log=runs/20261010-165634.log
```

- `--character=<id>` picks the character (`IRONCLAD`, the default, `SILENT`, `DEFECT`, `NECROBINDER` or `REGENT`).
- `--seed=<seed>` and `--agent-seed=<n>` replay a run: with the same character, the same pair visits the same rooms and makes the same decisions. Without them, each run gets new random seeds.
- `--time-scale=<n>` sets the game speed (default 20; past about 10 the gain is small).
- The run's game log, the agent's output and a trace of every decision and choice (`.trace.jsonl`) are kept in `runs/` (gitignored).
- The run ends as an error, and the command exits 1 with the reason, if the agent picks an action that is not listed (or a card selection outside its limits), does not answer within 30 seconds, disconnects, or speaks another protocol version; if the run stops making progress for 120 seconds (`STALL_SECONDS`); or if the game exits before the run ends. Nothing ever picks an action in the agent's place.
- Runs use the game's separate modded profile and save nothing, so your own saves, stats and achievements are untouched.
- A normal launch from Steam is unaffected: run mode and the bridge are on only when the game is started by this command.

Run the agent's tests with `python -m unittest discover -s agent/tests -t .`, and the tools' with `sh tools/test.sh`. CI (`.github/workflows/tests.yml`) runs both on every pull request and push to `main`. Building the mod and every check in the real game need the game's files, so they stay manual.

## Layout

- `STANDARDS.md` — project-specific coding standards, on top of the generic [standards built into pr-reviewer](https://github.com/wilsonluc/pr-tools/blob/main/plugins/pr-reviewer/standards.md).
- `CONTEXT.md` — glossary of game and training terms.
- `GAME_VERSION.md` — the game build, Godot, and .NET versions this repo targets.
- `.githooks/` — git hooks; enable with `git config core.hooksPath .githooks`.
- `mod/` — the C# mod the game loads: its project, its manifest (`SlayTheHuman.json`), its Harmony patches and its side of the bridge.
- `agent/` — the Python side of the bridge (`bridge.py`), the random agent, and their tests.
- `docs/protocol.md` — the messages between the mod and the agent.
- `tools/` — `decompile.sh` decompiles the installed game into `decompiled/`; `mod.sh` builds and installs the mod; `run.sh` plays an unattended run; `game.sh` finds the game for all three; `test.sh` checks how they refuse bad setups.
- `decompiled/` (gitignored, local only) — the game's C# source for the targeted build, made by `tools/decompile.sh`.
- `docs/architecture.md` — how the pieces fit, and the Python layout the specs grow into.
- `ROADMAP.md` — the phases: what the agent should reach, in order, and the rules for moving between them.
- `specs/` — feature specs. Every feature starts as a spec; see `specs/README.md` for the process.
- `.scrape/` (gitignored, local only) — reference material taken from [sts2-rl-agent](https://github.com/zhiyue/sts2-rl-agent): the C# bridge mod, a Python simulator, and docs. See `.scrape/NOTES.md`.

## Credits

This project builds on [zhiyue/sts2-rl-agent](https://github.com/zhiyue/sts2-rl-agent). That project's bridge mod, decompilation work, game-systems documentation, and Python simulator are the starting reference here. The code in this repo is written from scratch.

## License

MIT, see [LICENSE](LICENSE). The license covers this repo's own code only.

Slay the Spire 2 is the property of Mega Crit Games. This repo contains no game files, assets, or decompiled game code. You need your own copy of the game to use it. This project is for research and educational purposes.
