# 008: Plan

## Approach

`python -m agent.ppo.train` creates a training run folder, launches the games, and loops: collect a rollout from every game, run one PPO update, write a metrics row, and save a checkpoint every few updates. It stops at the step budget, on the failure budget, on an interrupt or on an error, saving a checkpoint each time. `--resume runs/<training run>` picks up from the latest checkpoint.

Torch is pinned in `pyproject.toml` (the CPU build; training runs on the CPU by default, and `--device cuda` uses a GPU with a CUDA build installed by hand). The model is small next to the games' cost, so the CPU is enough to start.

### Model (`agent/ppo/model.py`)

One embedding table over the whole vocabulary (padding index 0), width `embed` (default 32).

Each set in the observation (`docs/architecture.md`) has its own entity network: the entity's ID embeddings concatenated with its numbers, then two linear layers with ReLU, to width `hidden` (default 128). Sets inside entities are pooled first: each enemy's powers and intents are encoded and pooled into the enemy's input. Sets with one number per entry (powers) take it as a column; Crystal Sphere cells are entities with their hidden flag and grid position.

Pooling: for every set, the masked mean and masked max of its entities (zeros for an empty set). These, with the global IDs' embeddings and global numbers, go through two layers to the state vector, width `state` (default 256). The value head is one more layer to a scalar.

Action logits, segment by segment in `encoding.ACTIONS` order, each from a small per-segment scorer `w · relu(A e + B s)` over an entity vector `e` and the state `s`:

| Segment | Entity |
|---|---|
| `play` card i, target t | hand card i joined with enemy t, or a learned "no target" vector |
| `potion` slot i, target t | potion i joined with enemy t or "no target" |
| `travel`, `reward`, `card`, `option`, `shop`, `cell` | that set's entity i (`card` is the choices; `shop` adds the shop card's vector to the item's) |
| `bundle` b | mean of the choice cards in bundle b |
| `end_turn`, `tool`, `take`, `confirm`, `proceed` | the state alone, one linear layer |

The entity networks are shared within a set and pooling ignores order, so reordering a set's entities reorders its actions' logits and nothing else.

`masked(logits, mask)` replaces illegal logits with -1e8 before the softmax; the categorical's entropy then counts legal actions only, and masked positions get zero gradient. The same function is used when sampling and in the update.

### Buffer (`agent/ppo/buffer.py`)

Preallocated numpy arrays of shape `[steps, games, ...]` for every observation key (IDs as int32), the mask (bool), action, log-probability, value, reward, `terminated`, `truncated`, the bootstrap value and the decision kind. About 100 KB a step, so the default 256 steps × 4 games is about 100 MB.

GAE, per game column, from the last step back:

```
next_value = value[t+1]            (last_value after the final step)
if terminated[t]:  next_value = 0
elif truncated[t]: next_value = bootstrap[t]   (value of the observation the truncated step returned)
delta = reward[t] + gamma * next_value - value[t]
advantage[t] = delta + gamma * lam * (0 if terminated[t] or truncated[t] else advantage[t+1])
```

Returns are advantages plus values. Minibatches come from one seeded numpy generator, flattening steps and games.

### Collection (`agent/ppo/rollout.py`)

Each game collects its column in its own thread, with its own torch sampling generator: get the observation and mask, run the policy (no gradient, batch of one), sample, step the environment, store. Games never wait for each other, so a slow combat on one does not hold up the rest, and a game's choices depend only on its own seeds. The policy's weights do not change during collection. Torch runs single-threaded inside each game's thread so the threads don't fight over cores.

At an episode's end, a truncated step's bootstrap value is computed from the observation it returned, and the next `reset()` starts the next run. A `reset()` that fails (the game did not start the run) is retried three times, then raised. Collection returns every run that ended: outcome, floor, steps and `info["run"]`. After the last step, each game's last value is computed for GAE.

### Update (`agent/ppo/train.py`)

For each epoch, for each minibatch: recompute logits with the stored masks, the ratio to the stored log-probability, the clipped surrogate, the value loss `0.5 * (value - return)^2`, and the entropy bonus. Advantages are normalised per minibatch. Adam with gradient-norm clipping. Metrics come from the first epoch: approximate KL `mean((ratio - 1) - log ratio)`, clip fraction, entropy overall and per decision kind, value and policy loss, and explained variance over the rollout.

### Config (`agent/ppo/config.py`)

A dataclass; every field is a command-line flag. Defaults, with their reasons kept in the file:

| Setting | Default | Why |
|---|---|---|
| `gamma` | 0.999 | a run is thousands of steps and the win comes at the end (`docs/architecture.md`) |
| `lam` | 0.95 | the usual GAE trade-off |
| `clip` | 0.2 | the usual PPO clip |
| `lr` | 2.5e-4, constant | constant, since training length is open-ended with resuming |
| `steps` | 256 per game | about 1,000 steps per update with 4 games, several random runs or part of a long one |
| `games` | 4 | the speed measurement's best per-game rate; set per machine |
| `epochs`, `minibatch` | 4, 256 | the usual |
| `value_coef`, `entropy_coef` | 0.5, 0.01 | the usual |
| `max_grad_norm` | 0.5 | the usual |
| `embed`, `hidden`, `state` | 32, 128, 256 | small; the observation's structure does the work |
| `total_steps` | 10,000,000 | `ROADMAP.md`'s stop-and-look point |
| `checkpoint_every` | 10 updates | about 10 to 20 minutes of training lost at worst |
| `failure_budget`, `failure_window` | 5 in 100 runs | a few failures are expected; more means a cluster |
| `seed`, `device`, `hang_seconds`, `step_cap`, `trace_every`, `time_scale` | | passed through; the environment's defaults |

### Record and checkpoints (`agent/checkpoint.py`)

The training run folder is `runs/<YYYYMMDD-HHMMSS>/`, also the games' run folder (logs, traces, `summary.jsonl`). On start it writes `config.json`: the config, the seed, `git rev-parse HEAD` and whether `git status --porcelain` is empty, the game build from `GAME_VERSION.md`, the vocabulary hash, `encoding.schema_hash()`, `bridge.PROTOCOL`, `reward.definition_hash()`, and the Python and torch versions.

- `encoding.schema_hash()`: SHA-256 of the observation spec (each key's shape and dtype, written next to the set sizes as `OBSERVATION`), `ACTIONS`, `KINDS` and `SCHEMA_REVISION`, a number raised whenever a scaling rule or feature changes. A test checks every recording's observation against `OBSERVATION`.
- `reward.definition_hash()`: SHA-256 of `WEIGHTS`, `OUTCOMES`, `FULL_RUN` and `REWARD_REVISION`, raised whenever a score's definition changes.

`metrics.csv` gets one row per update, written as one line, flushed and synced, so a kill leaves whole rows. Columns: update, step, time, the learner's numbers (approximate KL, clip fraction, entropy, entropy per kind, value loss, policy loss, explained variance, learning rate, steps per second, update share), and over the runs ended since the last row the game's (runs, win rate, mean floor, mean act, mean steps per run, mean legal actions per decision, failed runs, each reward term's mean contribution).

`checkpoint.pt`, written to a temporary file then renamed: the model, the optimiser, update and step counts, the torch global RNG state, each game's sampling generator, the minibatch generator, each environment's game-seed generator, the vocabulary keys and the hashes.

On `--resume`: read `config.json`, compare every hash to the current code's and refuse naming each mismatch, except a vocabulary whose saved keys are a prefix of the current ones, which loads with new embedding rows (initialised like the rest). `metrics.csv` is cut back to the checkpoint's update, so rows for steps that will be collected again are dropped. The games launch fresh; each run in progress when training stopped is lost, as with any failure.

### Stopping

- Step budget: after the update that passes `total_steps`.
- Failure budget: a window of the last `failure_window` runs; a run that failed (outcome `failed: ...`, or a reset that never started) counts, the step limit does not. Passing `failure_budget` stops training with an error naming the budget, the count and the most common reasons.
- Interrupt (Ctrl+C) and any exception: a checkpoint of the last completed update, then the error is raised. A rollout cut short is dropped.

### Fake environment (`agent/tests/fake_env.py`)

The environment's interface, with observations of the real shape (`OBSERVATION`) and no game. An episode is 100 steps. On 10 of them, two options are legal at positions drawn at random from the `option` segment, and a cue in `global` says which is good; on the others only `end_turn` is legal. The reward is 0 until the last step, which gives `(good choices - 5) / 5`: random play averages 0, the best gets +1. A setting truncates some episodes partway, to exercise bootstrapping. PPO must reach a mean return of 0.8 within a set number of steps.

### Docs

`README.md`: a "Training" section (start, resume, the settings that matter, the GPU note). `docs/architecture.md`: collection in a thread per game. `CONTEXT.md`: "update" and "failure budget". `ROADMAP.md`: PPO done.

## Changes

- `pyproject.toml`: torch pinned.
- `agent/ppo/__init__.py`, `config.py`, `model.py`, `buffer.py`, `rollout.py`, `train.py`.
- `agent/checkpoint.py`.
- `agent/env/encoding.py`: `OBSERVATION`, `SCHEMA_REVISION`, `schema_hash()`.
- `agent/env/reward.py`: `REWARD_REVISION`, `definition_hash()`.
- `agent/env/environment.py`: the game-seed generator's state readable and restorable for checkpoints.
- `agent/tests/fake_env.py`, `test_model.py`, `test_buffer.py`, `test_checkpoint.py`, `test_train.py`; `test_encoding.py` checks `OBSERVATION`.
- `README.md`, `docs/architecture.md`, `CONTEXT.md`, `ROADMAP.md`.

## Verification

| Acceptance criterion | Check |
|---|---|
| Structured model | `test_model`: output shapes, every segment's logits come from its entities |
| Reordering | `test_model`: permute the hand, enemies and rewards of a recording; logits permute the same way, value and other logits unchanged |
| Masking | `test_model`: masked actions have zero probability and zero gradient; entropy equals the entropy over legal actions alone; `test_train`: the update recomputes with stored masks |
| GAE | `test_buffer`: hand-worked values with terminated, truncated and rollout-end steps |
| PPO update and config | `test_train`: one update changes the weights and gives finite metrics; `--help` lists every setting; `config.json` holds them all |
| Several games | a real training run's log shows every game collecting; `test_train` with three fake environments |
| No action outside the mask | the environment raises on one (spec 007) and training stops; none in the real training run |
| Record | `test_checkpoint`: `config.json` has every field; schema and reward hashes change when a set size, segment or weight changes |
| Seeding | `test_train`: two training runs with the same seed on the fake environment give identical metrics |
| Metrics | `test_train`: one row per update with every column; a file cut mid-row is repaired on resume |
| Checkpoints | `test_checkpoint`: saved on schedule, on the step budget, on an interrupt and on the failure budget |
| Resume | `test_checkpoint`: N updates, save, resume, one more update equals N+1 uninterrupted updates; the real run killed and resumed |
| Hash mismatch, vocabulary growth | `test_checkpoint`: each mismatch refused by name; a checkpoint from a shorter vocabulary loads with new rows |
| Step budget | `test_train` with a small `total_steps` |
| Failure budget | `test_train` with a fake environment that fails often: stops naming the reasons, checkpoint saved |
| CI tests | the workflow runs them all |
| Learns the fake environment | `test_train`: mean return ≥ 0.8 within the set steps, under five minutes in CI |
| Real training run | `--games 4 --total-steps 1000000`, killed once and resumed; no failure-budget stop; mean floor over its last 500 runs against the random agent's over 500 runs with `--games 4` |
| Speed | the training run's mean steps per second (from `metrics.csv`) against the random agent's measurement with 4 games |

## Risks

- Threads per game make inference batch-of-one → the model is small and torch single-threaded per thread; the speed criterion measures it. If it falls short, inference batches across games instead.
- 100 KB a step of observations → measured; IDs as int32; rollout steps are a setting.
- The fake environment could be learned without the long-discount machinery working → its reward only comes at the end, 90 steps after the first choice, so GAE has to carry it.
- Learning may not beat random within a million steps → the stop-and-look rule: environment, reward and model are examined before any longer run, as `ROADMAP.md` says.
- A checkpoint that loads but behaves differently → the resume test compares against an uninterrupted run exactly.
- Torch versions differ between machines → the version is pinned and recorded.
