# slay-the-human

A reinforcement learning agent for **Slay the Spire 2**. It plays the game headless and trains with PPO, with a strong focus on self-improvement.

## Goals

- Play the real game headless through a mod bridge. The mod reads game state and executes the agent's actions.
- Speed the game up as far as possible for faster training.
- Build PPO from the ground up.
- Make the agent improve through self-play over time.

## Setup

You need Windows, `git` (with Git Bash), the GitHub CLI `gh`, the [.NET 9 SDK](https://dotnet.microsoft.com/download/dotnet/9.0), and Slay the Spire 2 installed through Steam.

1. Log in to GitHub: `gh auth login`.
2. Clone and enable the repo's git hooks. The pre-push hook blocks direct pushes to `main`.
   ```
   gh repo clone wilsonluc/slay-the-human
   cd slay-the-human
   git config core.hooksPath .githooks
   ```
3. Decompile the game: `sh tools/decompile.sh`. It checks the installed build against `GAME_VERSION.md` and writes the game's C# source to `decompiled/`. That code is Mega Crit's: it is gitignored and never committed.
4. Build and install the mod, with the game closed: `sh tools/mod.sh`. It builds `mod/` against the game's own assemblies and installs it into the game's `mods/SlayTheHuman/` folder.
5. The first time, start the game and answer **Yes** to its mods warning. The game saves the answer and quits. From the next start, it loads the mod, and `%APPDATA%\SlayTheSpire2\logs\godot.log` shows lines starting `[SlayTheHuman]`.

## Unattended runs and the training environment

Unattended runs use a copy of the game per build, which Steam never updates: make it once with `sh tools/copy-game.sh` and record the hash it prints in `GAME_VERSION.md`, then run `sh tools/mod.sh` again so the copy gets the mod. Install the agent's packages with `pip install -e .` (Python 3.13).

The training environment (`agent/env/`) drives the game a step at a time in the Gymnasium shape: `reset()` starts a run, `step(action)` returns the next observation, the reward, whether the run ended and why, and `action_masks()` the legal actions. Each environment owns one game process that plays runs back to back; several run at once, each launched directly from the game copy (Steam must be running) once the one before reaches its main menu. Every decision comes as a fixed-shape observation (`encoding.py`), every action has its own index in one action space, and the reward is defined in `reward.py`. The game waits for each action as long as it takes; a game that stops or sends nothing for 120 seconds ends its run as truncated and is launched again.

`python -m agent.random_agent` plays runs with random legal actions through the environment, and is the speed command:

```
python -m agent.random_agent --games 4 --runs 120 --seed 41
seed=41
game=game0 seed=WSLL2KN1WJ outcome=loss floor=5 steps=44 per_second=13.1
...
agent_seed=41 games=4 runs=120 steps=6723 steps_per_second=49.0 per_game=12.3 runs_per_hour=3150 mean_floor=5.1 max_floor=12 launch_seconds=52 out=runs\20261013-204342
largest choices=20 deck=20 discard=20 ...
```

- `--games <n>` runs that many games at once, about one per CPU core at most; `--runs <n>` is the total, shared equally between them.
- `--seed <n>` replays a set of runs: the same agent seed gives every game the same game seeds and the same choices. `--replay runs/<time>/summary.jsonl --row <i>` replays one run and checks it ends the same.
- `--character <id>` picks the character (`IRONCLAD`, the default; the observation does not yet carry Defect's orbs or Necrobinder's Osty).
- `--trace-every <n>` keeps a full trace of one run in that many (default 100); failed runs always keep theirs. Every run adds a row to `summary.jsonl`, with its seed and action indices.
- `--think-seconds <s> --think-count <n>` pauses before the first actions, to check the game waits.
- Game logs, traces and summaries go in `runs/` (gitignored).
- An action the mask does not allow raises, and the run ends as an error. Nothing ever picks an action in the agent's place.
- Runs fix every unlock and save nothing, so they neither depend on nor change your profile, saves, stats or achievements.
- A normal launch from Steam is unaffected: run mode and the bridge are on only when the game is started with them.

When the game updates, `python -m agent.env.vocabulary --update` appends the new build's names to `agent/env/vocabulary.json`; existing indices never move.

## Training

`python -m agent.ppo.train` trains a PPO policy on several games at once. Each training run gets its own folder, `runs/<time>/`, holding its record (`config.json`: every setting, the seed, the git commit, the game build and the vocabulary, schema, protocol and reward identities), one row of metrics per update (`metrics.csv`), its latest checkpoint (`checkpoint.pt`), its log (`train.log`, which also shows each game's time per update), and the games' logs, traces and `summary.jsonl`.

```
python -m agent.ppo.train --games 6
python -m agent.ppo.train --resume runs/<time>
```

- Every setting is a flag (`--help` lists them with their defaults; `agent/ppo/config.py` gives the reason for each). `--games` is set per machine, like the speed command's.
- A checkpoint is saved every `--checkpoint-every` updates and whenever training stops: at `--total-steps` (default 10 million, the roadmap's stop-and-look point), on Ctrl+C, on an error, or when more than `--failure-budget` of the last `--failure-window` runs failed. A single failed run is logged and training carries on.
- `--resume` continues from the latest checkpoint with the same settings, losing at most the steps since it. A checkpoint made by code with another vocabulary, observation schema, protocol or reward refuses to load and names the difference; a vocabulary that only grew loads, with new embedding rows.
- Training runs on the CPU by default. `--device cuda` uses a GPU once a CUDA build of torch is installed (see pytorch.org for the command matching your GPU).

## Evaluation

`python -m agent.evaluate <checkpoint.pt>` plays a checkpoint on the 200 evaluation seeds (`agent/env/evaluation_seeds.json`), which training never plays: once with its best action, the official result, and once sampling. `python -m agent.evaluate random` plays the random agent on them; its result is `docs/baselines/random.json`. Each result, in `runs/eval-<time>/result.json`, has every seed's outcome, floor and act, the mean floor, win rate and share of runs past each act's boss, and what was measured (checkpoint, seeds, game build, commit, hashes). `--seeds N` plays the first N seeds, `--modes best` skips sampling.

Training makes a generation every `--evaluate-every` steps (default 250,000): it evaluates its policy with the best action, saves the checkpoint and result in `runs/<time>/generations/`, adds a row to `generations.csv`, and keeps the best generation and the latest `--generations-kept`.

Run the agent's tests with `python -m unittest discover -s agent/tests -t .`, and the tools' with `sh tools/test.sh`. CI (`.github/workflows/tests.yml`) runs both on every pull request and push to `main`. Building the mod and every check in the real game need the game's files, so they stay manual.

## Layout

- `STANDARDS.md` — project-specific coding standards, on top of the generic [standards built into pr-reviewer](https://github.com/wilsonluc/pr-tools/blob/main/plugins/pr-reviewer/standards.md).
- `CONTEXT.md` — glossary of game and training terms.
- `GAME_VERSION.md` — the game build, Godot, and .NET versions this repo targets.
- `.githooks/` — git hooks; enable with `git config core.hooksPath .githooks`.
- `mod/` — the C# mod the game loads: its project, its manifest (`SlayTheHuman.json`), its Harmony patches and its side of the bridge.
- `agent/` — the Python side of the bridge (`bridge.py`), the random agent, and their tests.
- `docs/protocol.md` — the messages between the mod and the agent.
- `tools/` — `decompile.sh` decompiles the installed game into `decompiled/`; `mod.sh` builds and installs the mod; `copy-game.sh` copies the game for unattended runs; `game.sh` finds the game for all three; `test.sh` checks how they refuse bad setups.
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
