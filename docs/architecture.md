# Architecture

How the pieces fit, and where each spec puts its code. Each spec creates only the files it needs; this is the shape they grow into. Change it by pull request, like the specs.

## The system

```
Slay the Spire 2 (headless, via Steam)
  └─ mod/ (C#, Harmony)        replaces AutoSlay's choices; reads game state; carries out actions
       └─ TCP, docs/protocol.md
            └─ agent/ (Python)  makes every decision: the random agent now, the PPO policy later
```

`tools/run.sh` plays one run with the random agent. From spec 007, the training environment drives the game itself, and the learner drives the environment.

## Python layout

One package, `agent/`, run as modules (`python -m agent.<module>`).

```
agent/
  bridge.py          the protocol client                                         004
  random_agent.py    random baseline; also the baseline row in evaluation         004
  env/                                                                            007
    environment.py   reset/step in the Gymnasium shape; one game process, runs back to back
    encoding.py      observation as a dict of padded arrays with presence masks; action index <-> game action; mask
    vocabulary.py    every ID of the targeted build -> index, with a content hash
    reward.py        the reward, defined once
    vector.py        later: several games at once (see below)
  ppo/                                                                            008
    model.py         ID embeddings, per-entity network, masked pooling, pointer-style logits, masked categorical
    buffer.py        preallocated storage including action masks; GAE with truncation bootstrap; minibatches
    rollout.py       drives the environments and fills the buffer; takes a list of environments
    train.py         the PPO update (re-applies stored masks) and its metrics
    config.py        hyperparameters as a dataclass, from the command line
  evaluate.py        fixed evaluation seeds kept apart from training; best action                 009
  checkpoint.py      owns runs/<run>/: config.json, metrics.csv, checkpoints (last N and best)    009
  tests/             one file per module, runnable in CI, plus a fake environment
dashboard/           React and MUI X on GitHub Pages; reads exported runs/*/metrics.csv and config.json    010
runs/                gitignored: game logs, traces, run records, checkpoints, evaluation results
pyproject.toml       Python version and pinned dependencies (numpy from 007, torch from 008)
```

## Design decisions

The layout follows ikostrikov/pytorch-a2c-ppo-acktr-gail (`storage.py`, `model.py`, `algo/ppo.py`, `envs.py`, `evaluation.py`): modular but shallow, with the PPO maths kept as readable as vwxyzjn/cleanrl's single-file `ppo.py`. One algorithm and a long-lived project suit modules; class hierarchies, callbacks and registries (Stable-Baselines3, Tianshou) are left out.

- **Environment in the Gymnasium shape.** `reset(seed) -> (obs, info)` and `step(action) -> (obs, reward, terminated, truncated, info)`, plus `action_masks()` (the sb3-contrib convention). Only a win or a loss is `terminated`. A game crash, hang or disconnect is `truncated`, so the learner bootstraps from the value estimate instead of treating it as a loss; it is still logged as an error (`STANDARDS.md`). Full Gymnasium spaces come later, only to cross-check against sb3-contrib's `MaskablePPO` if learning stalls.
- **Masking applied twice.** Illegal actions' logits are replaced before the softmax (`torch.where(mask, logits, -1e8)`, as sb3-contrib's `MaskableCategorical`), and entropy is computed over legal actions only. The mask is stored in the buffer and applied again when the update recomputes log-probabilities; masking only while sampling makes the ratio and KL wrong (Huang and Ontañón, "A Closer Look at Invalid Action Masking in Policy Gradient Algorithms", 2020). No action outside the mask is ever sent to the game.
- **Rollout buffer separate from collection.** As SB3's `RolloutBuffer` and ikostrikov's `RolloutStorage`: the buffer is pure (arrays, GAE, minibatches) and tested on its own; `rollout.py` only talks to environments.
- **Structured observations.** Each set (hand, enemies, relics, potions, shop items, rewards, map) is a padded array of fixed size with a presence mask, in a dict, not one flat vector. The model embeds each ID (from `vocabulary.py`), joins it with the entity's numbers, runs a shared per-entity network and pools with the masks into a global vector. Action logits are pointer-style: "play card i on enemy j" scores card i's and enemy j's embeddings with the global vector, so a card's logit follows the card wherever it sits in the hand. The deck is a bag of embeddings, not an ordered list. An entity transformer (as in AlphaStar) comes only if pooling plateaus.
- **One fixed action space.** A flat set of segments (cards by target, potions by target, end turn, map points, rewards, options, shop items, cards to select) with a mask. A multi-card selection is a sequence of single picks plus a confirm.
- **Several games at once, later.** Each game is already its own process and the Python side only waits on sockets, so parallel games need no worker processes: send every environment its action, then read every reply. Because decisions take very different times, a later step returns the first environments that are ready (PufferLib's `Multiprocessing(batch_size)`, Tianshou's `wait_num`). `rollout.py` takes a list of environments from the start, with one for now.
- **A record for every run.** On start, `runs/<run>/config.json` records the hyperparameters, the seed, the git commit (and whether the tree was dirty), the game build and the vocabulary's hash, as sample-factory records its `git_hash`. A checkpoint holds the model, the optimiser state, the step and the vocabulary hash, and refuses to load against a different vocabulary.
- **Metrics in a file.** `runs/<run>/metrics.csv` is the source of truth, which the dashboard reads: approximate KL, clip fraction, entropy, value and policy loss, explained variance, learning rate, steps per second, and the game's own: win rate, floor and act reached, decisions per run, legal actions per decision, failed runs.
- **Evaluation apart from training.** A fixed seed list that training never uses, with the policy's best (masked argmax) action, as SB3's `evaluate_policy(deterministic=True)`. The random agent runs the same seeds as the baseline.
- **Tests without the game.** As SB3's tests: GAE against hand-worked values (with truncation), masked actions getting zero probability and zero gradient, encoding round trips on recorded decisions, checkpoint save and load, and a tiny fake environment with masked actions that PPO must learn, which exercises the whole training stack in CI.

## Deliberately left out

Until a measurement asks for it: an entity transformer, observation or reward normalisation, Gymnasium space declarations, W&B or YAML configuration, asynchronous learners (sample-factory), and any second algorithm.
