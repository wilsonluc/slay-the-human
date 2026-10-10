# 008: PPO trainer

Status: draft

## Problem

Since spec 007 the game can be played one step at a time by a learner, but nothing learns. Phase 0 (`ROADMAP.md`) needs a training run whose agent beats the random agent, and that takes a PPO learner built for this environment: observations are sets of entities (cards, enemies, relics) of changing size, most actions are illegal at any decision, and a run is thousands of steps with its win at the very end.

Training will also run for days, on tens of millions of steps, across several games. Over that time games fail, the machine restarts and settings get tuned, so a training run that cannot be stopped and resumed, or whose results cannot be traced to what produced them, wastes those days. And a learner that keeps going while runs fail in clusters learns to seek the failures out.

## Goal

`python -m agent.ppo.train` trains a PPO policy on several games at once, laid out as `docs/architecture.md` describes (`agent/ppo/`, `agent/checkpoint.py`): it records each training run, saves checkpoints it can resume from, writes its metrics to a file, and stops loudly when runs fail too often.

## Non-goals

- Evaluation on fixed evaluation seeds with the best action, generations, keeping the best checkpoint or the last few, and the baseline measurement. Spec 009.
- The results dashboard. Spec 010.
- Ascension above 0, and other characters than Ironclad.
- A combat-only environment, a simulator of the game, a recurrent (memory) policy, an entity transformer, running observation or reward normalisation, hyperparameter search, and any second algorithm (`docs/architecture.md`: deliberately left out).
- Reaching phase 0's target. This spec gives the learner; phase 0 is judged by an evaluation once spec 009 exists.

## Acceptance criteria

Model:

- [ ] The policy and the value estimate are computed from the structured observation as `docs/architecture.md` describes: each ID embedded from the vocabulary and joined with the entity's numbers, a network shared by the entities of a set, pooling with the presence masks, and pointer-style action logits that score an action from the entities it names (a card, a target, a map point) and the pooled state.
- [ ] Reordering the entities of a set (cards in the hand, enemies, rewards) reorders their actions' probabilities the same way and changes nothing else.
- [ ] Illegal actions get zero probability and zero gradient, and entropy counts legal actions only. The action mask is stored with each step and applied again when the update recomputes probabilities.

Learning:

- [ ] Advantages are computed with GAE: a terminated episode adds no value after its last step; a truncated one (failure or step limit) and the end of a rollout add the value estimate of the last observation instead.
- [ ] One PPO update uses the clipped objective, a value loss and an entropy bonus. Every hyperparameter (discount, GAE lambda, clip range, learning rate, rollout length, epochs, minibatch size, loss weights, gradient clipping, number of games) lives in one config, can be set from the command line, and is recorded. The defaults are documented with the reason for each; the discount starts at about 0.999 (`docs/architecture.md`).
- [ ] Several games are stepped together, as many as the config says: each gets its action, then each reply is read. The game waits for the policy, including while it updates, with no time limit (spec 007).
- [ ] No action outside the mask is ever sent to the game.

Record and metrics:

- [ ] Each training run has its own folder, `runs/<training run>/`. On start it writes `config.json` with every hyperparameter, the seed, the git commit and whether the tree was dirty, the game build, the vocabulary hash, the observation and action schema hash (computed by the encoding from its own constants), the protocol version and the reward definition's hash.
- [ ] Every source of randomness (policy initialisation, sampling, minibatch order, game seeds) comes from the recorded seed, in a fixed order.
- [ ] After each update a row is added to `runs/<training run>/metrics.csv` with the learner's numbers (approximate KL, clip fraction, entropy overall and per decision kind, value loss, policy loss, explained variance, learning rate, steps per second, and the share of time spent updating against collecting) and the game's (win rate, floor and act reached, steps per run, legal actions per decision, failed runs, and each reward term's discounted contribution per run), over the runs that ended since the last row. A training run killed at any moment leaves a readable file.

Checkpoints and resuming:

- [ ] A checkpoint is saved every set number of updates and when training stops for any reason, including an interrupt and the failure budget below. It holds the model, the optimiser state, the step count, every random number generator's state, and the hashes from `config.json`. The latest checkpoint is kept; older ones are replaced.
- [ ] `--resume runs/<training run>` continues that training run from its latest checkpoint: same config, step count and metrics file carried on. A training run killed at any moment resumes, losing at most the steps since its last checkpoint.
- [ ] A checkpoint whose hashes do not match the current code (vocabulary, schema, protocol, reward) refuses to load, naming each mismatch. The one migration is a vocabulary that has only grown since the checkpoint: it loads, with an embedding row added for each new value.

Stopping:

- [ ] Training stops at a set number of steps (default 10 million, `ROADMAP.md`'s "stop and look" point), saving a checkpoint.
- [ ] Training stops loudly, saving a checkpoint, when the failed runs among the most recent runs pass a set budget, naming the budget, the count and the most common failure reasons. A single failed run is logged (spec 007) and training carries on.

Tests and measurement:

- [ ] Tests in CI, without the game: GAE against hand-worked values, with terminated, truncated and rollout-end cases; masked actions getting zero probability and zero gradient; the reordering criterion above; a checkpoint saved, loaded and resumed giving the same next update as an uninterrupted run; mismatched hashes refused and a grown vocabulary migrated.
- [ ] In CI, PPO learns a small fake environment with masked actions and a reward that only comes at the end of a long episode, reaching a set return within a set number of steps, in under five minutes.
- [ ] A training run on the real game with four or more games reaches one million steps. Along the way it is killed once and resumed. It does not hit the failure budget, and its mean floor over its last 500 runs is above the random agent's, measured on the same environment and game count.
- [ ] Over that training run, steps per second are at least 80% of the random agent's with the same number of games: collecting and updating cost little next to the games.

## Open questions

None.
