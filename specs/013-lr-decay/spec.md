# 013: Learning rate that decays

Status: draft

## Problem

Spec 011's training run peaked and then fell back. Its generations on the 200 evaluation seeds (best action):

| Generation | Mean floor | Past the act 1 boss |
|---|---|---|
| Update 733 (750,592 steps) | 17.78 | 23.0% |
| Update 977 (1,000,448 steps) | 15.80 | 10.1% |

The training runs' own mean floor still rose over the same stretch, so the policy did not run out of things to learn. Its updates grew too large instead: approximate KL climbed from a run mean of 0.028 to 0.040 over the last 50 updates. The learning rate is constant, so nothing settles the policy as training goes on, and the last checkpoint of a run can be much worse than its best.

Spec 012 made training 2.3 times as fast (about 5.3 million steps a day), so runs of several million steps are now the norm, and late updates matter more.

## Goal

The learning rate falls over a training run, from its set value at the start to zero at the step budget. A training run's last generation is then about as good as its best, and the policy's updates stay at the size PPO is designed for through the whole run.

## Non-goals

- Stopping training when generations stop improving (a later spec).
- Starting a training run from another run's checkpoint, or extending a finished run's step budget.
- A learning rate that adapts to approximate KL, or any other schedule.
- Changing the starting learning rate or any other setting.
- The results dashboard (now spec 014).

## Acceptance criteria

Schedule:

- [ ] The learning rate falls linearly with the training steps taken, from the set learning rate at step 0 to zero at the step budget (`total_steps`). A test checks the rate at the start, halfway and at the budget.
- [ ] A resumed training run continues the same schedule: a test shows the rate after resuming is the rate the run would have had without stopping.
- [ ] `metrics.csv` reports each update's learning rate (it already has the column).
- [ ] The setting's comment and `docs/architecture.md` describe the schedule and why.

Training:

- [ ] A training run with the default settings and a step budget of 2,000,000 runs to its budget.
- [ ] Over that run, the mean approximate KL per update is between 0.005 and 0.03, and no 50 updates in a row average above 0.03.
- [ ] Its last generation's mean floor is within 1.0 of its best generation's, and its share of runs past the act 1 boss within 5 points of the best's.
- [ ] Its best generation's share of runs past the act 1 boss is at least spec 011's best (23.0%).
- [ ] If it falls short of any of these, the run is reported with its metrics before any change to the settings.

## Open questions

None.
