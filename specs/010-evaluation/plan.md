# 010: Plan

## Approach

### Evaluation seeds

`agent/env/evaluation_seeds.json` holds 200 seeds, drawn once by `random.Random("slay-the-human evaluation seeds")` from the environment's seed alphabet, with that rule written in the file. `agent/env/seeds.py` loads them and computes their hash (SHA-256 of the seeds in order). 200 seeds put the standard error of a mean floor near 0.4 floors; win rates need more, which is the phase 1 spec's to decide.

`Environment.reset(seed)` refuses an evaluation seed unless `options["evaluation"]` is set, and a randomly drawn training seed that lands in the set is drawn again.

### `agent/evaluate.py`

```
python -m agent.evaluate <checkpoint.pt | random> [--games 4] [--modes best,sampled] [--seeds N]
```

Each game thread takes seeds from a shared queue and plays each with `options={"evaluation": True}`. Results do not depend on which game plays a seed: the best action is the masked argmax of a fixed policy, and sampling (and the random agent) uses a generator seeded from the evaluation seed and the mode. The policy runs on the CPU, one decision at a time, as in collection.

A checkpoint is loaded through `TrainingRun.load` (identity checks and vocabulary migration); the model's sizes come from its training run's `config.json`.

The result, `result.json`:
- `runs`: per seed and mode, the outcome, floor, act reached, steps and failure reason;
- `summary`: per mode, runs, failed runs, mean floor (over runs that did not fail), win rate, the share of runs past each act's boss (reached the next act; act 3's boss is a win), and `valid` (failed runs at most 10%);
- the checkpoint, its training run and update, the seed set's hash and size, the game build, the git commit, and the vocabulary, schema, protocol and reward hashes.

`agent.evaluate` writes to `runs/eval-<time>/`, beside the games' logs and traces.

### Generations

Two config settings: `evaluate_every` (default 250,000 steps) and `generations_kept` (default 3, the latest; the best is kept besides). After the update that passes each multiple, training evaluates its policy with the best action on the training games: each game's run in progress is ended (the next reset relaunches it), the evaluation plays the seeds, and collection starts fresh runs after. The checkpoint at that update is saved as `runs/<training run>/generations/update-<n>.pt` with `update-<n>.json`, its result, and a row is added to `generations.csv`: update, step, time, the best-action summary, the evaluation's seconds, and the file.

The best generation is the one with the highest win rate, then the highest mean floor: while no run wins, that is the mean floor. Generations that are neither the best nor among the latest `generations_kept` lose their checkpoint file; their row and result stay.

### Baseline and target

`docs/baselines/random.json` is the random agent's result on the seed set for the targeted build. `ROADMAP.md`'s targets table gets phase 0's target: a generation's best-action mean floor at least twice the random agent's, within 1,000,000 training steps. A training run with generations is evaluated against it; when one passes, the record row names the generation, its training run, commit, config, game build, seed set and result.

## Changes

- `agent/env/evaluation_seeds.json`, `agent/env/seeds.py`.
- `agent/env/environment.py`: the refusal and redraw.
- `agent/evaluate.py`.
- `agent/ppo/config.py`, `agent/ppo/train.py`: generations; `agent/ppo/rollout.py`: start fresh runs after an evaluation.
- `agent/tests/test_evaluate.py`; `test_environment.py`: the refusal.
- `docs/baselines/random.json`, `ROADMAP.md`, `README.md`, `docs/architecture.md`, `CONTEXT.md`.

## Verification

| Acceptance criterion | Check |
|---|---|
| Fixed seeds, never trained on | `test_evaluate`: the file's size and hash; `test_environment`: an evaluation seed is refused without the option, and drawn seeds avoid the set |
| `agent.evaluate`, both modes, random | `test_evaluate`: end to end on the fake game, a checkpoint and `random`; best action equals the masked argmax |
| Result fields | `test_evaluate`: every field present, the summary computed from the runs |
| Same results run after run | `test_evaluate` on the fake game; on the real game, a checkpoint evaluated twice with different game counts gives identical best-action rows |
| Traces kept | evaluation runs pass `evaluation`, which keeps full traces (spec 007); checked in the result folder |
| Failed runs, invalid | `test_evaluate`: failed runs are excluded from the mean and counted; past 10% the result is invalid |
| Generations every N steps | `test_train`: a small `evaluate_every` produces generations, rows and files |
| Best and latest kept | `test_train`/`test_evaluate`: files pruned, the best kept |
| `generations.csv` | `test_train` |
| Baseline recorded | `docs/baselines/random.json` from `agent.evaluate random` |
| Target and the run against it | `ROADMAP.md`; a training run with generations to 1,000,000 steps or until one passes |
| Tests in CI | the workflow |

## Risks

- An evaluation every 250,000 steps costs about 30,000 steps of play, near a tenth of training's time → reported apart; the interval is a setting.
- Ending the runs in progress for an evaluation wastes them → a few runs per evaluation, logged as abandoned, not failures.
- A checkpoint from before a schema change cannot be evaluated → by design; generations are evaluated as they are made.
