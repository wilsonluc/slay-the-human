# 007: Tasks

- [x] 1. `agent/` as a package with tests in `agent/tests/`, `pyproject.toml` (Python version, numpy pinned), CI installing it; README's "standard library only" replaced. Tests pass locally and in CI.
- [x] 2. Game copy: `tools/copy-game.sh`, `games.py` (hash, refusal, direct launch with the app ID, Steam check), `mod.sh` installs into the copy, `GAME_VERSION.md` rows, `/games/` gitignored. `test_games` passes; a copy launched by `games.py` reaches the main menu.
- [x] 3. Protocol 4 connection: `hello` with game version, `ready`/`start`, `run_end` per run, one connection; `RunLoop.cs` (no quit after a run that ended normally, per-run resets, room handler once); `bridge.py`; the random agent playing R runs on one game; `tools/run.sh` and its checks removed. `test_bridge` passes; 10 runs in one process.
- [x] 4. Unlocks and profile: lobby and player unlock prefixes, the fixed in-memory profile, no progress writes, the run-start check. `unlocks=all` in every run; profile folder hash unchanged after 10 runs; one seed played first and after three others gives identical traces.
- [ ] 5. No time limits: no answer timeout, `Wait.Until` logs instead of throwing, AutoSlay's deadlines and watchdog off. A run with 6-minute pauses before 5 actions completes.
- [ ] 6. Waits on state: AutoSlay's delays become one frame (startup counts logged), every `Wait.For` becomes a wait on its outcomes. No delay or `Wait.For` left in `mod/`; 20 full runs without failure; decisions per second before and after recorded.
- [ ] 7. Protocol 4 state: card object everywhere, sorted piles, map and boss on every decision, combat on any decision in combat with encounter and combat IDs, run counters; `CombatSnapshot` split; `docs/protocol.md`. Real traces show the fields, including a mid-combat selection.
- [ ] 8. Vocabulary: `Vocabulary.cs` keys in `hello`, `vocabulary.py` with `--update`, committed `vocabulary.json`. `test_vocabulary` passes; a second `--update` adds nothing.
- [ ] 9. Recordings: one real decision of every kind (including a mid-combat selection, a multi-card selection, a bundle and the Crystal Sphere) in `agent/tests/recordings/`. A test asserts every kind is present.
- [ ] 10. `encoding.py`: sets, sizes, scaling, map route summaries, action segments, mask, single picks, overflow. `test_encoding` round-trips every recording.
- [x] 11. `reward.py` with its documentation. `test_reward` passes on hand-worked values.
- [ ] 12. `fake_game.py` and `environment.py`: reset/step/masks, hang detection, failures, step cap, illegal actions, traces and summary rows, set-size logging. `test_environment` passes in CI.
- [ ] 13. Several games and the speed command: staggered `make_environments`; `random_agent.py` on the environment with `--games`, `--trace-every`, `--think-seconds`, `--replay`. A sweep of random runs with no overflow or unknown value; sizes set from it with margin; `--games 1` and `--games 8` figures recorded.
- [ ] 14. Determinism: fresh vs after other runs, alone vs parallel, idle vs busy, two profiles, and a summary row's replay all give identical traces.
- [ ] 15. Failures on the real game: kill a game mid-run (truncated, logged with reason, kind and floor; relaunched at the next reset); 10 runs per process without a relaunch.
- [ ] 16. Frame cap: uncapped in run mode, kept only if the speed command shows a gain and task 14's checks still pass.
- [ ] 17. `README.md`, `docs/architecture.md`, `CONTEXT.md`, `ROADMAP.md`, `GAME_VERSION.md` updated; every acceptance criterion checked and ticked.
