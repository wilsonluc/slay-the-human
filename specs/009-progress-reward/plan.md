# 009: Plan

## Approach

`agent/env/reward.py` splits its terms in two. Progress terms (floor, kills) pay `w * max(after - before, 0)`: a score's rise, once, when it happens. Shaping terms (hp, combat) stay potential-based, `w * (gamma * after - before)`, falling to 0 when the run is terminated. The outcome is `+1` for a win and `0` for a loss. The scores themselves (`Scores`) do not change, so traces and summary rows keep their shape and the terms can still be recomputed from them.

### Weights

| Term | Kind | Weight | Pays |
|---|---|---|---|
| floor | progress | 1.0 | 1/48 per floor reached, 1 for a full run |
| kills | progress | 1.0 | 1/48 per elite or boss killed |
| hp | shaping | 0.25 | as in spec 007 |
| combat | shaping | 0.25 | as in spec 007 |
| win | outcome | 1.0 | on the winning step |

A full run's floors pay as much as a win, so the agent values reaching the end as much as winning there; kills pay as much as a floor, so an elite is worth taking when it does not cost the run. `REWARD_REVISION` goes to 2, and the reward hash covers both weight tables and the outcomes.

### Why the loss pays 0

A loss penalty is discounted like every other reward, so the later a loss comes, in steps, the less it costs. In a phase where every run is lost, that makes putting the loss off the thing to learn, which is what the first training run did. With progress paid as it happens and no penalty, dying only ends the progress that would have followed; stalling earns nothing and pushes later progress further into the discount.

### The discount

The worked-run tests showed the discount (0.999, spec 008) leaves a win 3,000 steps away about 5% of its value, so a loss reached much faster can return more than a slow win. That favours speed rather than losing, and at the same pace a win always returns more; the test compares at the same pace. Tuning the discount is outside this spec.

### Turns per combat

The environment records, per run, the last turn of each combat (keyed by the combats won before it) and reports their mean as `turns_per_combat` in `info["run"]` and the summary row. `train.py` averages it over the runs that ended since the last row into a `turns_per_combat` column in `metrics.csv`.

## Changes

- `agent/env/reward.py`: progress and shaping terms, `terms()` replacing `shaping()`, outcomes, weights, revision and hash.
- `agent/env/environment.py`: `reward.terms`; turns per combat.
- `agent/ppo/train.py`: the `turns_per_combat` column.
- `agent/tests/test_reward.py`: worked runs; `test_environment.py`, `test_checkpoint.py`: the new terms and outcome.
- `docs/architecture.md`, `CONTEXT.md`: the reward's description.

## Verification

| Acceptance criterion | Check |
|---|---|
| Progress paid once, never taken back | `test_reward`: hand-worked step; a score that falls and rises again pays nothing more |
| A loss costs nothing | `test_reward`: `outcome("loss") == 0`; `test_environment`: a loss's outcome reward is 0 |
| A win adds its own reward | `test_reward`: `outcome("win") == 1` |
| HP and combat stay potential-based | `test_reward`: their contribution over a terminated run is minus their starting scores |
| Weights in one place, documented | `reward.py`'s docstring and tables; `test_reward`: a full run's floors equal a win |
| Reward hash changes | `test_reward`: each table, the outcomes, the run length and the revision change the hash; `test_checkpoint`: an old checkpoint is refused, naming the reward |
| Deeper loss returns more | `test_reward`: floor 17 against floor 5, also against a floor-5 loss three times as slow |
| Stalling never pays | `test_reward`: the same floors in three times the steps return less, at floors 5, 17 and 40 |
| A win beats any loss | `test_reward`: at the same pace, against losses on floors 1, 17, 47 and 48 |
| Repeating a state pays nothing | `test_reward` |
| Shaping adds up to minus its starting scores | `test_reward` |
| 300,000-step training run | `--games 4 --device cuda`, stopped past 300,000 steps; mean floor and steps per floor over its last 500 runs from `summary.jsonl` |
| Turns per combat in `metrics.csv` | `test_environment`: `info["run"]["turns_per_combat"]`; the column in the training run's `metrics.csv` |

## Risks

- Progress pays only on new floors, so the agent could learn to race up the map and die rather than survive; the floor reward for continuing and the HP shaping should outweigh it → the training run's steps per floor and floor distribution show it.
- A full run of progress is worth a win, so winning adds little over dying on the last floor → acceptable while no run wins; revisit when wins appear.
- The discount makes speed worth more than safety over long horizons → noted, tuning it is a separate decision.
