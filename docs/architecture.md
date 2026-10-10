# Architecture

How the pieces fit, and where each spec puts its code. Each spec creates only the files it needs; this is the shape they grow into. Change it by pull request, like the specs.

## The system

```
Slay the Spire 2 (headless, via Steam)
  └─ mod/ (C#, Harmony)        replaces AutoSlay's choices; reads game state; carries out actions
       └─ TCP, docs/protocol.md
            └─ agent/ (Python)  makes every decision: the random agent now, the PPO policy later
```

`python -m agent.random_agent` plays runs with the random agent. From spec 007, the training environment drives the games itself, and the learner drives the environment.

## Python layout

One package, `agent/`, run as modules (`python -m agent.<module>`).

```
agent/
  bridge.py          the protocol client                                         004
  random_agent.py    random baseline; also the baseline row in evaluation         004
  env/                                                                            007
    environment.py   reset/step in the Gymnasium shape; one game process, runs back to back
    games.py         launches and supervises several game processes, one environment each
    encoding.py      observation as a dict of padded arrays with presence masks; action index <-> game action; mask
    vocabulary.py    every ID and named value of the targeted build -> index; append-only, with a content hash
    vocabulary.json  the committed vocabulary, made from the game build by the mod
    reward.py        the reward, defined once: outcome plus weighted potential-based shaping terms (fixed weights, using the learner's discount)
  ppo/                                                                            008
    model.py         ID embeddings, per-entity network, masked pooling, pointer-style logits, masked categorical
    buffer.py        preallocated storage including action masks; GAE with truncation bootstrap; minibatches
    rollout.py       drives the environments and fills the buffer; takes a list of environments
    train.py         the PPO update (re-applies stored masks) and its metrics
    config.py        hyperparameters as a dataclass, from the command line
  evaluate.py        fixed evaluation seeds kept apart from training; best action                 009
  checkpoint.py      owns runs/<training run>/: config.json, metrics.csv, checkpoints; save and resume 008, last N and best 009
  tests/             one file per module, runnable in CI, plus a fake game (007) and a fake environment (008)
dashboard/           React and MUI X on GitHub Pages; compares generations (evaluated checkpoints); reads exported runs/*/metrics.csv and config.json    010
runs/                gitignored: game logs, traces, run records, checkpoints, evaluation results
pyproject.toml       Python version and pinned dependencies (numpy from 007, torch from 008)
```

## Design decisions

Modular but shallow: one file per concern, with the PPO maths kept readable in plain functions. One algorithm and a long-lived project suit modules; class hierarchies, callbacks and registries are left out.

- **Environment in the Gymnasium shape.** `reset(seed) -> (obs, info)` and `step(action) -> (obs, reward, terminated, truncated, info)`, plus `action_masks()`. Only a win or a loss is `terminated`. A game crash, hang or disconnect is `truncated`: the action that never completed is dropped, and the learner bootstraps from the value of the last observation received instead of treating it as a loss. It is still logged as an error (`STANDARDS.md`), with its decision kind and floor. Failures that cluster on certain states would teach the agent to seek them out, so training stops loudly when the failure rate over recent runs passes a set budget. A per-run step cap is also `truncated`, as a time limit. Full Gymnasium space declarations come later, only if learning stalls and an off-the-shelf masked PPO is needed to tell an environment problem from an algorithm problem.
- **Masking applied twice.** Illegal actions' logits are replaced before the softmax (`torch.where(mask, logits, -1e8)`), and entropy is computed over legal actions only. The mask is stored in the buffer and applied again when the update recomputes log-probabilities; masking only while sampling makes the probability ratio and KL wrong. No action outside the mask is ever sent to the game.
- **The game waits for the learner.** During a PPO update the game sits on its pending decision, for as long as the update takes, so the mod sets no time limit on the agent's answer. Hangs are caught on the Python side instead: no decision within a set time after an action was sent.
- **A long discount.** A run is 2,000 or more steps and a win only comes at the end, so the usual discount of 0.99 (about 100 steps, one combat) sees too little. The starting point is about 0.999 with a GAE lambda of about 0.95, tuned in the PPO plan.
- **Rollout buffer separate from collection.** The buffer is pure (arrays, GAE, minibatches) and tested on its own; `rollout.py` only talks to environments.
- **Structured observations.** Each set (hand, draw, discard and exhaust piles, enemies, relics, potions, shop items, rewards, map) is a padded array of fixed size with a presence mask, in a dict, not one flat vector. The model embeds each ID (from `vocabulary.py`), joins it with the entity's numbers, runs a shared per-entity network and pools with the masks into a global vector. Action logits are pointer-style: "play card i on enemy j" scores card i's and enemy j's embeddings with the global vector, so a card's logit follows the card wherever it sits in the hand. The deck and the piles are bags of embeddings, not ordered lists. The observation carries everything a player can look up (pile contents, each card's enchantment and affliction), so the policy needs no memory. Enemies are the living ones only; the logit follows the entity, so indices need not stay stable. Numbers are scaled by fixed rules in `encoding.py` (HP as a fraction of max HP, log scale for amounts), with no running statistics. Map choice is route planning, which a pooled set of points cannot see, so each candidate next point carries summaries of the routes it opens (the fewest and most elites, rest sites, shops and unknowns before the boss). Each set's size is set in one place, from measured maxima; overflow fails loudly. An entity transformer comes only if pooling plateaus.
- **One fixed action space.** A flat set of segments (cards by target, potions by target, end turn, map points, rewards, card rewards, options, shop items, bundles, grid cells, cards to select, confirm, proceed/leave/skip) with a mask. A multi-card selection is a sequence of single picks in any order (each step picks one remaining card; the environment sorts the picks before sending them), with the picked cards marked in the observation, confirm legal from the minimum, and an automatic submit at the maximum.
- **Several games at once.** One game is bound by its own frame time, so speed comes from running many. Steam starts one copy per app, so each game is launched directly with the app ID in its environment, from a copy of the game folder per build that Steam never updates, with start-ups staggered; copies share the profile safely because run mode writes no profile file, and give identical results alone or side by side. Parallel games need no worker processes: each game is already its own process, so `rollout.py` sends every environment its action, then reads every reply. The number of games is a setting, chosen per machine from the speed command (about one per CPU core).
- **A record for every training run.** On start, `runs/<training run>/config.json` records the hyperparameters, the seed, the git commit (and whether the tree was dirty), the game build and the vocabulary's hash. It also records an observation and action schema hash, computed by `encoding.py` from its own constants (each set's name, size, features and scaling; the action segments' order and sizes), the protocol version, and a hash of the reward definition. A checkpoint holds the model, the optimiser state, the step, the random number generators' states and those hashes, and refuses to load on any mismatch unless an explicit migration exists, so a changed encoding never loads silently. The vocabulary only grows, so a game patch that adds content does not strand checkpoints: one loads when its vocabulary is a prefix of the current one, with new embedding rows added, which is one such migration. Run mode fixes the run's unlocks to everything unlocked and writes no profile file, so a run depends neither on the profile it was played on nor on earlier runs in the same game.
- **Metrics in a file.** `runs/<training run>/metrics.csv` is the source of truth, which the dashboard reads: approximate KL, clip fraction, entropy (also per decision kind, since combat's many actions dominate the total), value and policy loss, explained variance, learning rate, steps per second, and the game's own: win rate, floor and act reached, decisions per run, legal actions per decision, failed runs, and each reward term's discounted contribution per run.
- **Evaluation apart from training.** A fixed seed list that training never uses, with the policy's best (masked argmax) action as the official number. The same seeds are also played by sampling, with fixed sampling seeds; a large gap between the two flags a policy stuck in loops or undertrained. The random agent runs the same seeds as the baseline. With the best action, a policy gives the same result on the same seed every time, so each seed is one sample, and a full run takes minutes; the evaluation spec sets the seed count and how often it runs. From phase 1.1, an evaluation also replays the level below, so a policy that gets worse there (forgets) shows up; training still never goes back down (`ROADMAP.md`).
- **Tests without the game.** GAE against hand-worked values (with truncation), masked actions getting zero probability and zero gradient, encoding round trips on recorded decisions, checkpoint save and load, and a tiny fake environment with masked actions that PPO must learn, which exercises the whole training stack in CI.

## Deliberately left out

Until a measurement asks for it: a schedule fading the reward's shaping weights (if a term's discounted contribution dominates late in training), a recurrent (memory) policy, an entity transformer, running observation or reward normalisation (each reward term's weight keeps its weighted score within ±1 instead), Gymnasium space declarations, W&B or YAML configuration, asynchronous learners, any second algorithm, and population-based training (several policies at once; only if parallel games are plentiful and one training run stalls on its hyperparameters).
