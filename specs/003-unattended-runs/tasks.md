# 003: Tasks

- [x] 1. Add run mode, the seed prefix, AutoSlay start and the run log lines to the mod; a normal launch logs none of them.
- [x] 2. Let `tools/game.sh` take per-script options; existing checks still pass.
- [x] 3. Write `tools/run.sh` with the Steam checks, launch, log watch and summary; ignore `runs/`.
- [x] 4. Add the `run.sh` checks to `tools/test.sh`; it passes.
- [x] 5. Run with and without `--seed`; check the seeds and the summary.
- [x] 6. Run the same seed twice; compare room and end lines.
- [x] 7. Measure time scales on one seed; set the default; check it at most halves the normal-speed time.
- [x] 8. Check the stall and early-exit paths, and a normal launch.
- [x] 9. Update `README.md`.
- [x] 10. Check every acceptance criterion and tick it in `spec.md`.
