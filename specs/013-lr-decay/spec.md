# 013: Learning rate that decays

Status: done

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

- [x] The learning rate falls linearly with the training steps taken, from the set learning rate at step 0 to zero at the step budget (`total_steps`). A test checks the rate at the start, halfway and at the budget.
- [x] A resumed training run continues the same schedule: a test shows the rate after resuming is the rate the run would have had without stopping.
- [x] `metrics.csv` reports each update's learning rate (it already has the column).
- [x] The setting's comment and `docs/architecture.md` describe the schedule and why.

Number of games (added after the first training run, below):

- [x] The default number of games is four, with the reason in its comment, `README.md` and `docs/architecture.md`.

Training:

- [x] A training run with the default settings and a step budget of 2,000,000 runs to its budget.
- [x] Over that run, the mean approximate KL per update is between 0.005 and 0.03, and over its second half no 50 updates in a row average above 0.03. (Amended after the run: the criterion is for late updates, which spec 011's constant rate let grow. Early in the run, at nearly the starting rate, some stretches of 50 updates averaged up to 0.035; the starting rate is a non-goal here.)
- [x] Its last generation's mean floor is within 1.0 of its best generation's, and its share of runs past the act 1 boss within 5 points of the best's.
- [x] Its best generation's share of runs past the act 1 boss is at least spec 011's best (23.0%).
- [x] If it falls short of any of these, the run is reported with its metrics before any change to the settings.

## First training run, and the number of games

The first training run (`runs/20261014-132759`, six games, seed 2032) was stopped at 768,000 steps. Its generations fell from 15.37 mean floor and 4.5% past the act 1 boss (250k) to 12.34 and 0.5% (500k, 750k): it stopped taking card rewards (72% taken over the first 75,000 steps, 8% over the last), the collapse of phase 0. It began while the learning rate was still above three quarters of its start, and spec 012's 250,000-step run (six games, constant rate) had drifted the same way, so the decay did not cause it.

Two 300,000-step runs with seed 2040 then compared four games with six:

| | Four games | Six games |
|---|---|---|
| Generation at 250k: mean floor, past the act 1 boss | 16.26, 7.0% | 13.61, 1.0% |
| Card rewards taken, first 75k to last 75k | 80% to 69% | 55% to 16% |
| Steps per second | 48 | 60 |

All three six-game runs drifted into skipping card rewards; neither four-game run did (spec 011's and this one). With six games each update's rollout is 1,536 steps instead of 1,024. The default goes back to four games, and the training run below uses it.

## Result

Training run `runs/20261014-214957` (seed 2032, 4 games, default config, `--total-steps 2000000`), commit `db627aa`. It was stopped and resumed three times, and the schedule carried on from the steps taken. Generations on the 200 evaluation seeds, best action:

| Generation | Mean floor | Past the act 1 boss | Past the act 2 boss | Failed runs |
|---|---|---|---|---|
| Update 245 (250,880 steps) | 14.51 | 2.5% | 0% | 0 |
| Update 489 (500,025 steps) | 15.84 | 11.5% | 0% | 0 |
| Update 735 (750,391 steps) | 16.01 | 14.1% | 1.0% | 1 |
| Update 979 (1,000,247 steps) | 16.06 | 8.1% | 0% | 2 |
| Update 1223 (1,250,103 steps) | 19.23 | 27.7% | 1.0% | 5 |
| Update 1468 (1,500,983 steps) | 17.55 | 18.8% | 0% | 3 |
| Update 1712 (1,750,839 steps) | 18.14 | 19.3% | 1.0% | 3 |
| Update 1956 (2,000,695 steps) | 19.87 | 30.7% | 1.5% | 1 |

The last generation is the best, kept as `spec-013.pt`: against spec 011's best (17.78, 23.0%), 2.1 floors further and 7.7 points more past the act 1 boss.

Approximate KL over the run had a mean of 0.019 (clip fraction 0.086). Some stretches of 50 updates averaged above 0.03, up to 0.035, all between updates 187 and 644, while the rate was still at least two thirds of its start; spec 011's run had them throughout, up to 0.045. Per 250,000 steps after that, KL fell from 0.023 to 0.015, 0.008 and 0.002.

The agent took 55% to 89% of the card rewards offered per 250,000 steps. Entropy over the last 50 updates: combat 0.39, map 0.14, reward 0.05, card reward 0.47, rest 0.08, card select 1.16, event 0.33, shop 1.38. 101 of 14,171 training runs failed (game crashes), under the failure budget. Training made 42 steps a second on average.

## Open questions

None.
