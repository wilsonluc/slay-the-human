# 017: Choices that pay off later

Status: draft

## Problem

The choices whose payoff comes fights later fade out of training. Over the last third of spec 014's four-game run (543 saved runs):

| Choice | Taken | For comparison |
|---|---|---|
| Smith (upgrade a card) at a rest site | 20 of 1,894 rest site choices (1%) | HEAL 1,867 |
| Card removal at a shop, when affordable on entering | 30 of 656 visits (5%) | the last checkpoint gives it 2% per shop decision; a uniform legal choice would give 10% |
| A card at a card reward | 51% by the end of the run | 84% at its start |

Rest site entropy fell from 0.47 to 0.09 over the run, shop entropy from 1.97 to 1.14.

A potion pays off in the next fight, inside the reward the agent sees soon. An upgrade, a removal or a card pays off a little in many later fights, and that is much harder for PPO to credit. Two readings fit the numbers:

- **Collapse:** the alternatives were not tried enough before the policy moved away from them, so the agent never learned their worth. A per-kind entropy floor, a larger bonus on these kinds, or exploration mixed into training would be the fix.
- **Learned:** they are worth less to this agent than what it does instead (healing keeps runs alive; a small deck with the starting cards gets through act 1). Then no exploration change helps, and the work belongs elsewhere.

Each lever costs a training run to try, and none can be judged without knowing which reading is true. Spec 011's per-kind entropy bonus already gives every decision kind equal weight, and an entropy floor allows a strong preference (a 2-option rest site at 3% Smith still has a fifth of its largest entropy), so a floor alone may change nothing.

## Goal

Training reports how often each of these choices is taken, and an evaluation measures what each is worth to the current best agent, so the next spec picks its lever on evidence.

## Non-goals

- Changing training (entropy, exploration, reward): the next spec, chosen from this one's result.
- Other choices (events, potions, the map).
- A new training run.

## Acceptance criteria

Measurement:

- [ ] `metrics.csv` reports, over each update's finished runs, the share of rest site choices that were Smith (out of the rest site choices where Smith was offered), and the share of shop visits that bought the card removal (out of the visits where it was affordable on entering). With the existing share of card rewards taken, the three choices show without reading traces. A test shows both.

Evaluation with a forced choice:

- [ ] The evaluation can play the best action with one choice forced wherever it is legal: Smith at a rest site when HP is at least 70% of max (where a heal of 30% would be mostly wasted); the card removal at a shop when affordable; taking a card at a card reward. The forced choice's own follow-up (which card to upgrade, remove or take) stays the policy's best action. Each rule is an evaluation mode of its own, recorded in the result like "best" and "sampled". A test shows each rule.

Result:

- [ ] `spec-014.pt` on the 200 evaluation seeds: the best action, and each forced rule. For each, the mean floor, the share past each act's boss, and the failed runs.
- [ ] For each rule, its mean floor difference from the best action paired by seed, with its standard error, and whether it beats the best action by more than twice the standard error: the reading (collapse or learned) for that choice. The result names the lever the next spec should take.

## Open questions

None.
