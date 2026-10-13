# 012: Faster games

Status: done

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
- A user interface for the stop request; any local tool can create the file.
- Batching policy inference across games (the next lever if inference becomes the limit).
- A combat-only environment or a simulator of the game.
- A learning rate that decays over the run.

## Acceptance criteria

- [x] In run mode, no resource the game loads is freed while the game runs, and the game's own asset unloading does nothing. The game log shows how many resources are kept.
- [x] In run mode the frame cap is off from startup, whatever the frame rate setting. The game log shows the frame cap the mod set.
- [x] A normal launch keeps the player's frame rate and frees resources as before.
- [x] Runs are unchanged: spec 011's best checkpoint, evaluated on the 200 evaluation seeds with the best action, gives the same result per seed as before this change, apart from runs that fail (game crashes) in either evaluation.
- [x] Memory stays bounded: over a training run of at least 250,000 steps, no game passes the environment's memory limit, and the most memory a game holds is reported.
- [x] The default number of games is the fastest measured in training (six, unless a later measurement says otherwise).
- [x] A training run with the default settings, otherwise like spec 011's, makes at least 1.8 times spec 011's 26.3 steps a second over its first 250,000 steps.
- [x] In run mode, loading a run's, act's or room's assets forces no garbage collection, and a game's time per frame does not grow with its age. The game log shows how many forced collections were removed. (Added during the build: the first 250,000-step run slowed each game by about a quarter as it aged, since each room's forced full collection took longer as the game held more objects, about a second a run and growing.)
- [x] A stop can be requested while training runs, and lets the games' runs finish: from the next update no game starts a new run, training goes on with the steps the runs in progress still play, and once every game is idle it stops with a checkpoint. A test on the fake environment shows the runs in progress finishing and none starting. (Added during the build: faster runs make long training runs routine, and a stop that kills runs mid-way wastes them.)
- [x] `ROADMAP.md`'s speed paragraph has the new measurements and their date.

## Result

Training run `runs/20261014-091022` (seed 2032, the defaults: 6 games, GPU), commit `74359ee`:

| | Spec 011 (4 games), first 250,000 steps | First build of this spec | This spec |
|---|---|---|---|
| Steps a second, mean of updates | 25.9 | 47.2 | 61.2 |
| Steps a second, overall | 25.6 | 46.0 | 60.5 |
| Failed runs | 12 | 18 | 6 |
| Most memory a game held | | 2.1 GB | 2.8 GB |

That is 2.3 times spec 011's 26.3 steps a second. The first build fell short (46 to 47): each game slowed by about a quarter as it aged, which removing the forced garbage collections fixed. With them gone a game's time per update stayed at 13.8 to 14.1 s from launch to 140 updates. The most memory a game held still grew late in the run, by about 0.1 GB every 20 updates; the environment's memory limit relaunches a game that reaches it. The generation at 250,000 steps had a mean floor of 13.82 with no failed runs.

`spec-011.pt`, evaluated with the best action, gave the same outcome, floor and steps as its generation on all 200 evaluation seeds, with no failed runs.

## Open questions

None.
