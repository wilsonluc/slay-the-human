# 012: Plan

## Approach

### Kept resources

`mod/KeepResources.cs`, a run-mode patch class:

- Postfixes on Godot's `ResourceLoader.Load(string, string, CacheMode)` (the non-generic overload, which `Load<T>` goes through) and `ResourceLoader.LoadThreadedGet(string)` add every resource they return to a static set. The set holds a reference, so the resource, and the scripts and sub-resources it references, stay loaded for the life of the game.
- Prefixes on `AssetCache.UnloadAssets` and `AssetCache.UnloadMissedCacheAssets` skip them, since they dispose resources the game no longer needs.
- The game log shows the count each time it passes another 500.

Memory then grows with the number of distinct resources the runs have touched, bounded by the game's own assets.

### No frame cap

`mod/NoFrameCap.cs`, a run-mode postfix on `NGame.InitializeGraphicsPreferences` (which sets `Engine.MaxFps` from the player's settings at startup), sets `Engine.MaxFps` to 0 and logs it. The background limit (`NBackgroundModeHandler`) never applies in run mode: a game with no window gets no focus events. The prototype's game logs show it never logged its limit.

### Rest site buttons

Faster frames widen a race in the rest site handler: a chosen option leaves the room's option list a few frames before its button is replaced, and a stale button clicked in that gap fails the run (5 of 200 evaluation runs with the first build; twice in spec 011's whole run). `mod/AgentRestSite.cs` waits until every live button's option is in the room's list before offering the choice.

### Games and memory

`config.py`'s `games` default goes to 6, with the measurements in its comment. The environment keeps the most memory its game has held (`peak_memory`, across relaunches), and the trainer's per-update timing line shows it per game.

## Changes

- `mod/KeepResources.cs`, `mod/NoFrameCap.cs`: new.
- `mod/AgentRestSite.cs`: buttons checked against the room's options.
- `agent/env/environment.py`: `peak_memory`.
- `agent/ppo/train.py`: memory in the timing line.
- `agent/ppo/config.py`: `games` 6.
- `agent/tests/`: the peak memory on a fake game.
- `ROADMAP.md` (speed paragraph), `docs/architecture.md`, `README.md` (game count examples), `CONTEXT.md` (kept resources).

## Verification

- Kept resources, frame cap → the game log of a run-mode launch shows the kept count and `max fps 0`. A normal launch shows neither line, since the patch classes are run-mode only.
- Runs unchanged → `python -m agent.evaluate runs/20261012-215539/spec-011.pt --modes best`, compared seed by seed with the generation's result `runs/20261012-215539/generations/update-733.json`.
- Memory bounded, speed, default games → a training run with the defaults (seed 2032, cuda) to at least 250,000 steps: the timing lines' peak memory stays under the limit, and `metrics.csv`'s mean steps per second over the run is at least 47.3 (1.8 × 26.3).
- Roadmap → the speed paragraph's figures come from the prototype's and this run's measurements.

## Risks

- A resource the game expects to be reloaded fresh (state kept on a resource object) → the evaluation check catches any change in play.
- Memory grows past the limit over a long run → the 250,000-step run shows the peak; the environment's memory limit stays the backstop.
