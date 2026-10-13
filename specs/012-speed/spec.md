# 012: Faster games

Status: approved

## Problem

Training runs at about 26 steps a second with four games, so 1,000,000 steps take about 11 hours, and phase 1 likely needs tens of millions.

Measured in the real game (random actions, one game, unless noted):

- **The game reloads its own code.** The game loads scenes as it needs them and frees them when nothing holds them; a scene's C# scripts go with it. Each reload of a C# script has the engine rebuild the script's class information by reflection, and that was about two thirds of the game's main thread. Keeping every loaded resource alive in run mode took one game from 10.2 to 13.6 steps a second, and four games from 23 to 49.
- **The frame rate is capped.** At startup the game sets the engine's frame cap from its settings, 60 frames a second by default, with no window as well. A decision takes 6 to 8 frames. Uncapped, one game went from 7.6 to 10.2 steps a second. With four games, uncapping alone gained nothing until the reloads were gone.
- **More games help, to a point.** With both changes: four games 49 steps a second, six 61, eight 62.
- **Training keeps most of it.** Both changes, same seed and settings as spec 011's run: 43 steps a second with four games (against 26), and 53 with six. Policy inference then takes 3 of every 18 seconds with four games, 5 with six.
- **Runs are unchanged.** Every change above played the same seeds to exactly the same number of steps.
- **The rest gave nothing measurable:** skipping the game's fast-mode waits outright, faster animations, no audio, a time scale of 60, a larger .NET garbage collector generation, and freeing cards instead of pooling them.

Keeping resources alive costs memory: a training game held about 1.7 GB after 20 minutes, with 1,800 resources kept, against the environment's 4 GB limit.

## Goal

In run mode, games keep every resource they load and run with no frame cap, and training uses the fastest number of games. Training with the default settings is at least 1.8 times as fast as spec 011's run, and plays the same runs.

## Non-goals

- The results dashboard (now spec 013).
- Changing the player's saved settings. A normal launch of the game keeps its frame rate and its resource handling.
- Batching policy inference across games (the next lever if inference becomes the limit).
- A combat-only environment or a simulator of the game.
- A learning rate that decays over the run.

## Acceptance criteria

- [ ] In run mode, no resource the game loads is freed while the game runs, and the game's own asset unloading does nothing. The game log shows how many resources are kept.
- [ ] In run mode the frame cap is off from startup, whatever the frame rate setting. The game log shows the frame cap the mod set.
- [ ] A normal launch keeps the player's frame rate and frees resources as before.
- [ ] Runs are unchanged: spec 011's best checkpoint, evaluated on the 200 evaluation seeds with the best action, gives the same result per seed as before this change, apart from runs that fail (game crashes) in either evaluation.
- [ ] Memory stays bounded: over a training run of at least 250,000 steps, no game passes the environment's memory limit, and the most memory a game holds is reported.
- [ ] The default number of games is the fastest measured in training (six, unless a later measurement says otherwise).
- [ ] A training run with the default settings, otherwise like spec 011's, makes at least 1.8 times spec 011's 26.3 steps a second over its first 250,000 steps.
- [ ] `ROADMAP.md`'s speed paragraph has the new measurements and their date.

## Open questions

None.
