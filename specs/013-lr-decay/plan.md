# 013: Plan

## Approach

`learning_rate(config, steps)` in `agent/ppo/train.py` returns `lr * max(0, 1 - steps / total_steps)`. Before each update the trainer sets every optimizer parameter group's rate from the steps taken so far, so the update that starts at step 0 uses the set rate, and the rate reaches zero at the step budget. It depends only on the steps and the recorded config, so a resumed run gets the same rate it would have had without stopping; the rate saved in the optimizer's state is overwritten before it is used. `metrics.csv`'s `learning_rate` column already reports the rate the update used.

The step budget is now the length a run trains for: the default stays at 10,000,000 (ROADMAP.md's stop-and-look point), and the verification run sets `--total-steps 2000000`.

## Changes

- `agent/ppo/train.py`: `learning_rate`; the trainer sets the rate before each update.
- `agent/ppo/config.py`: the comments on `lr` and `total_steps`.
- `agent/tests/test_train.py`: the schedule's values, and each update's reported rate.
- `agent/tests/test_checkpoint.py`: the resume test stops its first part with an interrupt under the same step budget, so it checks the resumed rates too.
- `docs/architecture.md`: the schedule and why.

## Verification

- The rate falls linearly to zero → `LearningRateTest` (start, halfway, at and past the budget) and `test_each_update_uses_and_reports_the_rate_for_the_steps_taken`.
- A resumed run continues the schedule → `test_resuming_gives_the_same_updates_as_training_on`, whose rows include `learning_rate`.
- `metrics.csv` reports the rate → the same test on rows.
- Comment and docs → the diff.
- Training criteria → `python -m agent.ppo.train --total-steps 2000000 --device cuda` with the other defaults; KL from `metrics.csv` (run mean, and the highest 50-update rolling mean), generations from `generations.csv`, compared with spec 011's best (23.0% past the act 1 boss).

## Risks

- The rate falls early in a long budget too, slowing learning before it plateaus → the run is judged against spec 011's best; if it falls short, it is reported before any change.
- The run takes 9 to 10 hours, and a game could pass its memory limit late in a run (spec 012 noted slow growth) → the environment relaunches that game; failures count against the failure budget as before.
