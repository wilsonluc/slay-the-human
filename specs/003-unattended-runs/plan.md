# 003: Plan

## Approach

**Run mode.** Everything this spec adds to the mod happens only when the game was started with `--slay-the-human-run`. Each new patch class has a Harmony `Prepare()` that returns whether that argument is present, so a normal launch applies none of them.

**Starting the run.** In run mode, when the main menu is ready, the mod starts the game's own `AutoSlayer` (`new AutoSlayer().Start(...)`). No `IsReleaseGame` patch is needed: the game's `--autoslay` path only does the same thing. AutoSlay clicks through the menus, plays the run, and quits the game when the run ends (exit code 0, or 1 when it fails).

**The seed.** AutoSlay's own seed only drives its choices; the run's seed comes from the character screen. In run mode a prefix on `NGame.StartNewSingleplayerRun` replaces the `seed` argument with the run's seed: the one in `--slay-the-human-seed=<seed>`, or else a new one from the game's `SeedHelper.GetRandomSeed()`. The same seed is passed to `AutoSlayer.Start`, so AutoSlay's choices repeat too. The prefix also sets `shouldSave: false`, so runs leave no save files or run history behind.

**What the mod logs.** In run mode, lines starting `[SlayTheHuman]`:
- `run start seed=<seed>` when the run starts;
- `room act=<n> floor=<n> type=<type>` on each `RunManager.RoomEntered`;
- `run end outcome=<win|loss> floor=<n>` from `RunManager.OnEnded(isVictory)`.

Modded games already use a separate save profile (`modded/profileN`), skip metrics upload, and award no achievements, so run mode never touches the player's own profile.

**The command.** `sh tools/run.sh [--seed=<seed>] [--time-scale=<n>] [--any-build]`:
1. Finds the game and checks the build (`tools/game.sh`, whose option parsing gains per-script options).
2. Stops if Steam is not running, or the game already is (Steam would only focus it).
3. Launches through Steam: `steam.exe -applaunch 2868840 --slay-the-human-run [--slay-the-human-seed=<seed>] --headless --time-scale <n> --log-file <runs/...log>`. Godot's `--log-file` sends the whole game log to a file per run in the gitignored `runs/` folder.
4. Watches that log. No new `[SlayTheHuman]` or AutoSlay line for 120 seconds of real time, or the game exiting before `run end`, makes it stop the game and exit 1 with the reason.
5. On `run end`, waits for the game to exit, then prints the seed, outcome, floor and elapsed time, and exits 0.

**Speed.** The default `--time-scale` is the fastest value that still finishes runs, chosen by measuring same-seed runs. If time scale alone cannot halve the time of a normal-speed headless run, the next levers are Godot's frame limits (`--max-fps`, vsync) and any fixed real-time waits the profile shows.

## Changes

- `mod/RunMode.cs`: the `--slay-the-human-run` and `--slay-the-human-seed` arguments, and the run's seed.
- `mod/StartAutoSlay.cs`: starts AutoSlay when the main menu is ready, in run mode.
- `mod/SeedRun.cs`: the `StartNewSingleplayerRun` prefix.
- `mod/RunLog.cs`: the `run start`, `room` and `run end` lines.
- `tools/game.sh`: lets a script add its own options.
- `tools/run.sh`: the command.
- `tools/test.sh`: `run.sh` stops when Steam is not running, and on an unknown option.
- `.gitignore`: `runs/`.
- `README.md`: how to run it.

## Verification

- Full run, exit 0 → `sh tools/run.sh` with Steam running.
- Prints seed, outcome, floor, time → its last lines.
- No window → the run's log shows `Rendering device name: N/A (headless)`; no window appears.
- Random seed by default, given seed used → two runs without `--seed` print different seeds; a run with `--seed=TEST1` prints it; each run's log has the game's own `Seed: <seed>` line matching the printed one.
- Same seed, same run → two runs with `--seed=TEST1`: their `[SlayTheHuman] room` lines and `run end` lines are identical.
- Speed → one same-seed run at `--time-scale=1` and one at the default: the default takes at most half the time.
- Stall and early exit → a run with the stall limit lowered to a few seconds stops the game and exits 1; killing the game mid-run makes the command exit 1, naming the early exit.
- Steam not running → `tools/test.sh` with a fake `tasklist`.
- Normal launch unaffected → launch from Steam: the log has no AutoSlay or `[SlayTheHuman] run` lines, and the main menu waits for input.
- Docs → `README.md` covers the command.

## Risks

- AutoSlay's run depends on timing (its watchdog, frame waits) as well as its seed → the same-seed check finds out; if runs still differ, find the timing-dependent step and revise the spec with the user if it cannot be fixed.
- The act list or other run setup draws from an unseeded random source before `StartNewSingleplayerRun` → the same-seed check finds out.
- `shouldSave: false` breaks part of AutoSlay's flow → drop it and accept run history in the modded profile.
- A Steam update changes `-applaunch` → the command stops when the game never starts, after 90 seconds.
