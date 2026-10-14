# 013: Learning rate that decays

Status: approved

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
- Changing the starting learning rate or any other setting, except the default number of games (see below).
- The results dashboard (now spec 014).

## Acceptance criteria

Schedule:

- [ ] The learning rate falls linearly with the training steps taken, from the set learning rate at step 0 to zero at the step budget (`total_steps`). A test checks the rate at the start, halfway and at the budget.
- [ ] A resumed training run continues the same schedule: a test shows the rate after resuming is the rate the run would have had without stopping.
- [ ] `metrics.csv` reports each update's learning rate (it already has the column).
- [ ] The setting's comment and `docs/architecture.md` describe the schedule and why.

Number of games (added after the first training run, below):

- [x] The default number of games is four, with the reason in its comment, `README.md` and `docs/architecture.md`.

Training:

- [ ] A training run with the default settings and a step budget of 2,000,000 runs to its budget.
- [ ] Over that run, the mean approximate KL per update is between 0.005 and 0.03, and no 50 updates in a row average above 0.03.
- [ ] Its last generation's mean floor is within 1.0 of its best generation's, and its share of runs past the act 1 boss within 5 points of the best's.
- [ ] Its best generation's share of runs past the act 1 boss is at least spec 011's best (23.0%).
- [ ] If it falls short of any of these, the run is reported with its metrics before any change to the settings.

## First training run, and the number of games

The first training run (`runs/20261014-132759`, six games, seed 2032) was stopped at 768,000 steps. Its generations fell from 15.37 mean floor and 4.5% past the act 1 boss (250k) to 12.34 and 0.5% (500k, 750k): it stopped taking card rewards (72% taken over the first 75,000 steps, 8% over the last), the collapse of phase 0. It began while the learning rate was still above three quarters of its start, and spec 012's 250,000-step run (six games, constant rate) had drifted the same way, so the decay did not cause it.

Two 300,000-step runs with seed 2040 then compared four games with six:

| | Four games | Six games |
|---|---|---|
| Generation at 250k: mean floor, past the act 1 boss | 16.26, 7.0% | 13.61, 1.0% |
| Card rewards taken, first 75k to last 75k | 80% to 69% | 55% to 16% |
| Steps per second | 48 | 60 |

All three six-game runs drifted into skipping card rewards; neither four-game run did (spec 011's and this one). With six games each update's rollout is 1,536 steps instead of 1,024. The default goes back to four games, and the training run below uses it.

## Open questions

None.
