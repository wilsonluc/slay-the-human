# 003: Unattended runs

Status: draft

## Problem

Training needs thousands of runs with nobody at the keyboard. Today a run needs a person to launch the game, click through the menus and play it, at human speed with full rendering. The game also has to be launched through Steam: started directly, Steamworks fails to start and the game stops at an error popup.

The game ships a built-in test bot, AutoSlay, that plays a whole run unattended. It is switched off in release builds. Turned on by the mod, it can stand in for the agent until the agent can play (spec 004), which lets this spec prove the launch, speed, seeding and exit path on real runs.

## Goal

One command plays one full run unattended: it launches the game through Steam with no window and at a raised game speed, the game plays a run with a given seed to the end, and the command reports the outcome and how long it took.

## Non-goals

- The agent making the choices, reading game state, or any bridge to Python. AutoSlay plays, including the defensive buffs it gives itself.
- Several game instances at once.
- Characters other than the one AutoSlay picks, ascension levels and custom modifiers.
- Linux and macOS (see #5).

## Acceptance criteria

- [ ] With Steam running, one command run from the repo root launches the game through Steam, the game plays one full run to its end, and the command exits 0 after the game exits.
- [ ] The command prints the run's seed, its outcome (win or loss), the floor it ended on, and the elapsed time.
- [ ] No game window opens during the run.
- [ ] The run uses the seed given to the command: the game's own log names that seed as the run's seed.
- [ ] Two runs with the same seed visit the same rooms in the same order and end with the same outcome on the same floor.
- [ ] The game speed can be set; a full run at the default speed takes at most half the time of a run at normal speed with no window.
- [ ] When the run makes no progress for a set time, or the game exits without finishing a run, the command stops the game and exits non-zero, saying what happened.
- [ ] When Steam is not running, the command exits non-zero and says so, before launching anything.
- [ ] Launching the game normally from Steam, with the mod installed, leaves AutoSlay off and the game behaves as without these changes.
- [ ] `README.md` says how to run it.

## Open questions

