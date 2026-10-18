# 018: Plan

## Approach

- **Policy loss.** `every_kind` replaces the plain mean of the PPO policy loss's per-step terms: the mean over steps plus `by_kind`'s mean over kinds (spec 011's entropy weighting). In a minibatch with K kinds, a kind with n of N steps weighs n/N + 1/K: at least 1/K, what an equal share of the kinds gives it, and combat keeps all of its n/N. The total weight doubles, which Adam's step size and the gradient clipping absorb; relative to the whole, combat keeps more than half its share (about 0.45 of the pull against about 0.8 now).
- **KL per kind.** The last epoch's per-step approximate KL is averaged per decision kind, as entropy is, into `approx_kl_<kind>` columns.
- **Training run.** From scratch: four games, seed 2032, cuda, `--total-steps 2000000`, run to the budget (about 16 hours at spec 014's pace). Its generations every 250,000 steps are evaluated with the best action; its best generation is evaluated again with `--modes best,force_card` and paired by seed (scratchpad `paired.py`, as in spec 017).

## Changes

- `agent/ppo/train.py`: `every_kind` in the policy loss; `approx_kl_<kind>` metrics.
- `agent/tests/test_train.py`: the policy loss weighting test; the KL column.
- `docs/architecture.md`: the weighting and the metric.

## Verification

- Weighting → `test_the_policy_loss_gives_a_rare_kind_an_equal_share_and_combat_its_steps`: one card reward among 99 combat steps gets a gradient of at least 1/2, and the combat steps together at least 0.99.
- KL per kind → `test_one_update_changes_the_weights_and_writes_finite_metrics` reads `approx_kl_event`.
- Training → `runs/<time>/metrics.csv` (`card_rewards_taken` over the last 100 updates, `smith_taken`, `card_removal_taken`, `approx_kl_<kind>`) and `train.log`'s generations; the force_card evaluation's paired gain and standard error.

## Risks

- Combat learns slower with a smaller share → the generations' mean floor shows it against spec 014's run at the same steps; the run is reported as it is.
- A rare kind's updates grow too large (its KL jumps, its policy flips) → `approx_kl_<kind>` shows it, and PPO's clip still bounds each step.
