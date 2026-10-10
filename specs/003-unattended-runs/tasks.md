# 003: Tasks

- [ ] 1. Add run mode, the seed prefix, AutoSlay start and the run log lines to the mod; a normal launch logs none of them.
- [ ] 2. Let `tools/game.sh` take per-script options; existing checks still pass.
- [ ] 3. Write `tools/run.sh` with the Steam checks, launch, log watch and summary; ignore `runs/`.
- [ ] 4. Add the `run.sh` checks to `tools/test.sh`; it passes.
- [ ] 5. Run with and without `--seed`; check the seeds and the summary.
- [ ] 6. Run the same seed twice; compare room and end lines.
- [ ] 7. Measure time scales on one seed; set the default; check it at most halves the normal-speed time.
- [ ] 8. Check the stall and early-exit paths, and a normal launch.
- [ ] 9. Update `README.md`.
- [ ] 10. Check every acceptance criterion and tick it in `spec.md`.
