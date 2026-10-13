# 012: Uncapped frame rate

Status: draft

## Problem

Training runs at about 28 steps a second with four games, so 1,000,000 steps take about 10 hours, and phase 1 likely needs tens of millions. Each game makes about 7 steps a second.

A game in run mode is held to its player's frame rate setting. At startup the game sets the engine's frame cap from its settings, 60 frames a second by default, with no window as well as with one. A game that is not in focus drops further, to 30, when its "limit frame rate in background" setting is on (the default). The mod waits on the game one frame at a time, and a decision takes about 8 frames, so the cap, not the processor, sets the pace: four games use under half of an 8-core machine.

## Goal

Games in run mode run as many frames a second as the machine allows, whatever the player's settings, and play exactly the same runs as before. Training is measurably faster, and the measured speeds replace the ones in `ROADMAP.md`.

## Non-goals

- The results dashboard (now spec 013).

- Changing the player's saved settings. A normal launch of the game (without run mode) keeps the player's frame rate.
- A combat-only environment or a simulator of the game.
- Changes to the trainer, its settings or the reward.
- A learning rate that decays over the run (left to its own spec).

## Acceptance criteria

- [ ] In run mode, the game's frame cap is off, from startup and through every run, whatever its frame rate setting, and the background limit never applies. The game log shows the frame cap the mod set.
- [ ] A normal launch keeps the frame rate from the player's settings.
- [ ] Runs are unchanged: spec 011's best checkpoint (`spec-011.pt`), evaluated on the 200 evaluation seeds with the best action, gives the same result per seed as before this change (mean floor 17.78; 23.0% past the act 1 boss), apart from runs that fail (game crashes) in either evaluation.
- [ ] Speed is measured with random actions at 1, 4 and 8 games, and with training at the default game count, and `ROADMAP.md`'s speed paragraph is updated with the new figures and the date.
- [ ] Training with four games makes at least 1.5 times as many steps a second as before (28). If it falls short, the measurements and what then limits the speed are reported before any other change.
- [ ] The default number of games is the fastest measured count, if that is not four.

## Open questions

None.
