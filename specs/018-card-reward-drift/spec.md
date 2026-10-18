# 018: The drift into skipping cards

Status: draft

## Problem

Training drifts into skipping card rewards, and the skipping costs the agent. In spec 014's four-game run, the share of card rewards taken fell from 84% to 51%. Spec 017 measured `spec-014.pt` with a card forced at every card reward on the 200 evaluation seeds, paired by seed:

| Play | Mean floor | Forced card | Paired gain |
|---|---|---|---|
| Best action | 21.06 | 22.63 | +1.53 ± 0.49 |
| Sampled, as in training | 20.14 | 21.49 | +1.41 ± 0.56 |

Taking a card is better in training's own sampled play too, and training's own signal says so. Over the last third of that run's saved training runs, the GAE advantage (as training computes it, with `spec-014.pt`'s values) averages +0.006 for picking a card and −0.013 for Skip, a gap of +0.019 ± 0.005. When it does take a card, the policy takes its likeliest one 85% of the time, so sampling is not picking bad cards. The signal points to taking; the policy moves to skipping anyway.

The update is where it goes wrong. Spec 011 gave every decision kind an equal share of the entropy bonus, but the policy loss is still averaged over steps. Card rewards are about 6% of steps, combat most of the rest. A card reward's own pull on the policy is small, while combat's updates move the layers it shares with them: the state network, the scorer that rates cards (shared with card selections, where the agent removes its best cards, spec 017) and the scorer that rates options (shared with the rest site's options and events, where it heals 99% of the time).

## Goal

Every decision kind's own signal pulls on the update at least an equal share, and a training run keeps taking the card rewards that pay, beating `spec-014.pt`.

## Non-goals

- Separate networks or scorers per decision kind: the next step if this falls short.
- Forcing a choice in training, such as removing Skip: skipping is a real strategy (spec 011).
- Smith and the removal's card choice as targets of their own: they are measured here, and a later spec takes them on with this run's result.
- The reward.

## Acceptance criteria

Update:

- [ ] The policy loss gives each decision kind in the minibatch at least an equal share of the kinds' pull, whatever its share of the steps, and combat's pull stays at least half what it is now. A test shows a rare kind's policy loss pulls at least as much as an equal share, and combat's at least half its share of the steps.
- [ ] `metrics.csv` reports the approximate KL per decision kind, as it reports entropy, so a rare kind's updates growing too large shows.

Training:

- [ ] A training run from scratch with spec 014's result settings (four games, seed 2032, the 2,000,000-step schedule) runs to its step budget.
- [ ] Over its last 100 updates, the share of card rewards taken is at least 70% (spec 014's run: 56%).
- [ ] Its best generation's mean floor (best action, 200 evaluation seeds) beats `spec-014.pt`'s 21.06 on the same build (spec 017's evaluation).
- [ ] Its best generation, evaluated with `force_card`, gains less than twice the paired standard error over its best action: forcing cards no longer finds floors the policy leaves.
- [ ] The result reports the Smith and card removal shares over the run, and each kind's approximate KL.
- [ ] If the run falls short, it is reported with its metrics before any change to these settings.

## Open questions

None.
