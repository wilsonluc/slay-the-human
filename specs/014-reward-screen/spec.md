# 014: Reward screen

Status: draft

## Problem

**The agent skips card rewards without seeing them.** On the rewards screen after a fight the agent takes rewards one at a time and then proceeds. It can proceed with the card reward unopened, which gives the same outcome as opening it and choosing Skip, without seeing the cards. Early in training this choice becomes near certain either way, and which way it goes decides the run. Counted in the training traces (early and late thirds of each run's traces):

| Training run | Card reward opened | Proceeded with it unopened | Once opened: picked, skipped |
|---|---|---|---|
| Spec 013's first run (six games, collapsed), early | 1,012 | 340 | 857, 155 |
| Spec 013's first run, late | 25 | 1,093 | 22, 3 |
| Spec 013's result run (four games), early | 3,193 | 649 | 3,088, 107 |
| Spec 013's result run, late | 4,587 | 23 | 2,689, 1,900 |

The card choice itself works: once the agent sees the cards, it picks or skips them, and late in the good run it skips 41% of the time. The collapse is in the decision before it, which skips every card unseen. Spec 011 left the rewards screen out of its exploration check because its choices "have one right order", and all three six-game runs fell into skipping that way (spec 013). The same screen also lets the agent leave gold behind: late in spec 013's result run it did so 986 times.

**Runs fail on the rewards screen after an event's fight.** In spec 013's two longer training runs, 61 of 128 failed runs failed with "the event was still asking after 50 choices" (53 of 101 in the result run). A fight that an event starts (a monster room reached through an unknown room) ends in a rewards screen, and there the agent's choices stop having effect: it takes the same gold, or proceeds, again and again until the event handler gives up.

## Goal

On the rewards screen the agent cannot leave a card reward unopened or gold untaken. It decides about cards on the card reward screen, where it sees them, and can still skip them there. Runs no longer fail on the rewards screen after an event's fight. If, with this, six games learn as well as four, training goes back to six games.

## Non-goals

- Forcing a card pick: Skip stays on the card reward screen.
- Potions and relics: taking them stays the agent's choice (a full potion belt, a relic with a downside).
- Game crashes ("the game closed the connection") and other failure kinds.
- The results dashboard (now spec 015).

## Acceptance criteria

Rewards screen:

- [ ] While a card reward is unopened or gold is untaken, the rewards screen does not offer proceeding. A test on recorded decisions shows it.
- [ ] The card reward screen still offers Skip, and a skipped card reward is still not offered again.
- [ ] The rewards screen after an event's fight responds to the agent's choices. The cause is found and fixed in the mod, and the plan records it.

Training:

- [ ] A training run with six games and seed 2040, configured like spec 013's comparison (the 2,000,000-step schedule, stopped after 300,000 steps), opens the card reward on at least 95% of the rewards screens that offer one, and has no run fail with "the event was still asking after 50 choices".
- [ ] If it does: a training run with six games, seed 2032 and a step budget of 2,000,000 runs to its budget, and its best generation is within 1.0 mean floor and 5 points past the act 1 boss of `spec-013.pt` (19.87, 30.7%) or better. Then the default goes back to six games. Otherwise the default stays at four, and the runs are reported.
- [ ] No run in either training run fails with "the event was still asking after 50 choices".

## Open questions

None.
