# 011: Plan

## Approach

### Exploration

`agent/ppo/train.py`'s `by_kind` averages the per-step entropy within each decision kind of the minibatch, then averages the kinds, and the entropy bonus uses that in place of the plain mean. The kinds are the decision kind's vocabulary index the buffer already keeps for the per-kind entropy metrics. `entropy_coef` stays 0.01.

### Reward

`agent/env/reward.py` gains a progress term, `bosses`: act bosses killed out of 3, weight 1, so each boss pays 1/3 when it dies. It is progress like `floor` and `kills` (paid on the rise, never taken back). `REWARD_REVISION` goes to 3. The worked-run helpers in `test_reward.py` put the act bosses on floors 17, 33 and 48.

### Learning settings

`lam` defaults to 0.99. Approximate KL and the clip fraction are measured on the last epoch of an update rather than the first, so they show how far the whole update moved the policy (the first epoch's first minibatch always reads 0). The learning rate is then set from short runs on the real game: several values, 30,000 steps or so each, keeping the lowest that puts the mean approximate KL in 0.005 to 0.03 with the clip fraction under 0.3. The chosen value and the measurements go in `config.py`'s comment.

### Measurement

The environment counts, per run, the card rewards each visit to a rewards screen offers (the screen repeats after each reward taken; a visit is counted once) and the cards picked from them. The run's info and summary row carry `card_rewards: {offered, taken}`, and `metrics.csv` gets `card_rewards_taken`, picked out of offered over the runs since the last row.

## Changes

- `agent/ppo/train.py`: `by_kind`, KL and clip fraction from the last epoch, `card_rewards_taken`.
- `agent/ppo/config.py`: `lam`, `lr`.
- `agent/env/reward.py`: the `bosses` term.
- `agent/env/environment.py`: card reward counts.
- Tests: `test_train` (`by_kind`), `test_reward` (bosses, worked runs), `test_environment` (counts), `fake_env.py`.
- `ROADMAP.md` (the dashboard is now spec 012), `docs/architecture.md`, `CONTEXT.md`, `README.md` where they describe the reward or settings.

## Verification

| Acceptance criterion | Check |
|---|---|
| Entropy bonus weighs kinds equally | `test_train.EntropyByKindTest` |
| Entropy of each common kind at least 0.2 at the end | the training run's last `metrics.csv` rows |
| Boss bonus, progress, documented | `test_reward` (hand-worked step, ends pay nothing), `reward.py` docstring |
| Worked runs pass; past the boss beats at it | `test_reward.WorkedRunsTest` |
| Reward hash changes | `REWARD_REVISION` 3; `test_definition_hash_follows_the_definition` |
| lam 0.99 | `config.py` |
| KL and clip fraction in range | the training run's `metrics.csv` means |
| Card rewards taken reported | `test_environment` (counting), `metrics.csv` column |
| 15% past the act 1 boss within 1M steps | the training run's `generations.csv` |
| Reported if short | this PR |

## Risks

- Equal weight per kind lowers the bonus on combat steps → combat's entropy is watched too; it is one of the kinds held to 0.2.
- A higher learning rate can destabilise training → the short runs pick it; the full run's KL is checked against the range.
- Several changes at once hide which one helped → accepted: each alone is unlikely to pass the wall, and the per-kind entropy, card reward and KL metrics show what moved.
