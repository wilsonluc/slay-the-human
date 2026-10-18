# 017: Plan

## Approach

- **Rates.** The environment already counts card rewards offered and taken per run (spec 011). It now counts two more choices the same way, in `COUNTED_CHOICES`: rest site choices where Smith was offered, and those that chose it (each choice counts, so a Miniature Tent's second choice too); shop visits where the card removal was affordable on entering, and removals bought (a visit runs from the first shop decision until a decision that is neither the shop nor the removal's card selection; gold only falls in a shop, so a removal bought was affordable on entering). The run's info and summary row carry `smith` and `card_removal` beside `card_rewards`, and `metrics.csv` gets `smith_taken` and `card_removal_taken` beside `card_rewards_taken`.
- **Forced choices.** `agent/evaluate.py` gets three modes, `force_smith`, `force_removal` and `force_card`. Each is the best action, except that where its rule finds legal actions, the mask is narrowed to them first, so the policy picks the best among them (the best card to take). What follows (the card to upgrade or remove) is the plain best action. The environment exposes its current decision and legal actions (`decision`, `legal`) for the rule to read. The Smith and removal tests are shared with the counting.
- **Result.** `spec-014.pt` is evaluated in all four modes on the 200 evaluation seeds. A scratchpad script pairs each forced mode's floors with the best action's by seed: the mean difference, its standard error, and whether it is more than twice the standard error.

## Changes

- `agent/env/environment.py`: `COUNTED_CHOICES`, `is_smith`, `is_removal`, `_count_choices` (was `_count_cards`), the `decision` and `legal` properties.
- `agent/ppo/train.py`: a `<choice>_taken` share per counted choice.
- `agent/evaluate.py`: `FORCED` and its rules; `play` narrows the mask.
- `agent/tests/`: counting tests, the metrics columns, the forced rules and a forced mode played on the fake environment.
- `README.md`, `docs/architecture.md`: the modes and the metrics.

## Verification

- Rates → `test_environment`: Smith counted per rest site choice that offers it; the removal once per shop visit where affordable, its card selection within the visit. `test_train`: the three shares in `metrics.csv`.
- Forced choices → `test_evaluate`: each rule's actions on hand-built decisions (Smith only at 70% of max HP or more), and a forced mode playing only the forced actions where offered.
- Result → `runs/eval-<time>/result.json` for `spec-014.pt` with `--modes best,force_smith,force_removal,force_card`; the paired differences in the spec.

## Risks

- The forced policy has never played the decks it is forced into, so a forced mode understates what the choice is worth to a policy trained to use it → the result reads a clear gain as collapse; a loss or no difference is reported as such, not as proof the choice is bad.
- Seed noise hides a small effect → paired by seed, and judged against twice the standard error.
