# 015: Plan

## Approach

Each failure kind gets the smallest fix at its cause, found by reading the failed runs' game logs and traces and the game's decompiled code (investigation of 2026-10-18).

- **Mislabelled run failures.** AutoSlay logs "Run failed with seed=<seed>: <message>" and quits with exit code 1. The environment looked for "run error" or "RunFailed" in the game log; "RunFailed" only matched a stack trace line, and only when one was printed. It now matches "Run failed with seed" and names the failure "AutoSlay failed the run: <message>", without the seed so reasons group. A closed connection waits up to 5 seconds for the game to exit before reading its log, so the last line is there.
- **Error output and exit code.** `games.launch` sends the game's error output to `<log stem>.errors.txt` beside its log instead of discarding it. A failure from a closed connection appends "the game exited with code 0x…" (0xE0434352 is an unhandled .NET exception).
- **Battleworn Dummy.** Its encounter gives no rewards, so after the fight the game resumes the event. At its second and third settings the event upgrades cards or gives a relic, opening no screen, and comes back as a new event room on its last page. `AgentEvent`'s wait after the room closes accepted only a combat, a screen, the map or the run's end; it now also accepts a new live event room, and carries on with it.
- **Crystal Sphere.** `AgentCrystalSphere` offered switching tools on every choice. A switch is now offered only when the last choice was a reveal (or at the start), so every two choices spend at least one divination and the loop finishes well within its 200 choices.
- **Rest site with Miniature Tent.** `AgentRestSite` waited for the proceed button, which stays enabled after a first option, so a later option (Smith, whose card choice runs before the game removes it from the options) passed the wait at once and its stale button was offered again. It now waits for the chosen option to leave the room's options.
- **Floor 49.** `AutoSlayer.PlayRunAsync` loops while the total floor is below 49, then abandons the run through an Options button this build lacks. A transpiler on its state machine replaces the 49 with `int.MaxValue`, checking it finds exactly one; a win and a loss already end the loop.
- **Piles.** The draw, discard and exhaust piles pass `encoding` only their first `PILE` cards; the global sizes still use the whole piles.

## Changes

- `agent/env/environment.py`: `_game_error` matches AutoSlay's line; `_exited` names the exit code; both failure paths use them.
- `agent/env/games.py`: `launch` keeps the error output; `error_file`.
- `agent/env/encoding.py`: piles cut to `PILE`.
- `mod/AgentEvent.cs`, `mod/AgentCrystalSphere.cs`, `mod/AgentRestSite.cs`: the waits and the tool switch above.
- `mod/RunLoop.cs`: `NoFloorLimit`.
- `agent/tests/fake_game.py`: modes `autoslay` and `crash`.
- `agent/tests/test_environment.py`, `agent/tests/test_encoding.py`: tests.
- `docs/protocol.md` (the tool switch), `README.md` (the error file).

## Verification

- AutoSlay's failure → test: the fake game logs AutoSlay's line and quits; the outcome is "AutoSlay failed the run: …", without "closed the connection" or the seed.
- Error output and exit code → test: the fake game writes an exception to its error output and exits with 0xE0434352; the file holds it and the outcome names the code.
- Battleworn Dummy, Miniature Tent, floor 49, Crystal Sphere → in the game: failed runs from the four-game training run replayed with the fixed mod (a scratchpad script plays the trace's actions, then `spec-014.pt`'s best action), each going past the floor it failed on.
- Piles → test: an exhaust pile of 400 cards encodes 300 and the exact size.
- Training → `runs/<time>/train.log`, counted by failure reason.

## Risks

- A new event room also appears in cases that worked before → the wait only takes it when no combat is starting and no screen is open, the cases it already handled.
- The transpiler finds a different 49 after a game update → it refuses unless there is exactly one.
- Waiting for an option to leave the options never ends if the game keeps it (a cancelled Smith) → the same 60 second timeout as before.
