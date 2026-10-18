# 014: Deck building

Status: done

## Problem

**The agent skips card rewards without seeing them.** On the rewards screen after a fight the agent takes rewards one at a time and then proceeds. It can proceed with the card reward unopened, which gives the same outcome as opening it and choosing Skip, without seeing the cards. Early in training this choice becomes near certain either way, and which way it goes decides the run. Counted in the training traces (early and late thirds of each run's traces):

| Training run | Card reward opened | Proceeded with it unopened | Once opened: picked, skipped |
|---|---|---|---|
| Spec 013's first run (six games, collapsed), early | 1,012 | 340 | 857, 155 |
| Spec 013's first run, late | 25 | 1,093 | 22, 3 |
| Spec 013's result run (four games), early | 3,193 | 649 | 3,088, 107 |
| Spec 013's result run, late | 4,587 | 23 | 2,689, 1,900 |

The card choice itself works: once the agent sees the cards, it picks or skips them, and late in the good run it skips 41% of the time. The collapse is in the decision before it, which skips every card unseen. Spec 011 left the rewards screen out of its exploration check because its choices "have one right order", and all three six-game runs fell into skipping that way (spec 013). The same screen also lets the agent leave gold behind: late in spec 013's result run it did so 986 times.

**The policy cannot see its deck's size or how many copies it holds.** The model pools the deck's cards into its state with their mean and their maximum (`agent/ppo/model.py`), and both are blind to counts: a deck of Strike and Bash and a deck of two Strikes and two Bashes give the same state, and nothing else in the observation gives the deck's size. Whether to take a card depends on both: a card thins or bloats the deck by its size, and a third copy is worth less than a first. No amount of training recovers what the observation leaves out. The other card sets (hand, draw pile, discard pile, exhaust pile, the cards offered) are pooled the same way: in combat the policy sees what is in the draw and discard piles, but not how many cards each holds. Potions likewise: it sees which potions it holds, but not how many, nor how many slots its belt has, so it cannot tell a full belt (which decides whether a potion reward or a shop potion can be taken).

**Cards outside the hand show no cost, and some lose numbers.** Only cards in the hand carry their energy cost. Deck cards, the cards offered and shop cards carry none, so the policy picks and buys without seeing cost: 57 cards cost less once upgraded, and an enchantment can change cost too. Each card also keeps its damage, block and only one other number; a card with more loses the rest. A special card offered as a reward (a particular card, not a choice of three) is sent whole, but only its ID reaches the observation, so its upgrade and enchantment are lost.

**Runs fail on the rewards screen after an event's fight.** In spec 013's two longer training runs, 61 of 128 failed runs failed with "the event was still asking after 50 choices" (53 of 101 in the result run). A fight that an event starts (a monster room reached through an unknown room) ends in a rewards screen, and there the agent's choices stop having effect: it takes the same gold, or proceeds, again and again until the event handler gives up.

## Goal

On the rewards screen the agent cannot leave a card reward unopened or gold untaken. It decides about cards on the card reward screen, where it sees them, and can still skip them there, knowing its deck's size and how many copies of each card, the offered ones included, it already holds. Runs no longer fail on the rewards screen after an event's fight. If, with this, six games learn as well as four, training goes back to six games.

## Non-goals

- Forcing a card pick: Skip stays on the card reward screen.
- Potions and relics: taking them stays the agent's choice (a full potion belt, a relic with a downside).
- Game crashes ("the game closed the connection") and other failure kinds, beyond the failure budget below.
- What combat and events show beyond the above (power durations, non-attack intent amounts, event option costs, history): spec 015.
- Attention between the cards offered and the deck's cards, for synergies between particular cards: a later spec, if the agent's picks still ignore its deck.
- The results dashboard (now spec 016).

## Acceptance criteria

Rewards screen:

- [x] While a card reward is unopened or gold is untaken, the rewards screen does not offer proceeding. A test on recorded decisions shows it.
- [x] The card reward screen still offers Skip, and a skipped card reward is still not offered again.
- [x] The rewards screen after an event's fight responds to the agent's choices. The cause is found and fixed in the mod, and the plan records it.

The deck:

- [x] The observation gives the size of the deck, and in combat of the hand, draw pile, discard pile and exhaust pile; and for each card in the deck and each card offered (card rewards, card selections, the shop) how many copies of it the deck holds: the same card with the same upgrade. Tests show two decks that differ only in copies give different observations and different states.
- [x] Every card in the observation, not only those in the hand, gives its energy cost (with X cost and no cost marked), and every number the game gives it, not only the first beyond damage and block. Tests show it on recorded cards.
- [x] A special card offered as a reward reaches the observation as a whole card, like a shop's card. A test shows it.
- [x] The observation gives the potions held and the belt's number of slots. A test shows a full belt and one with a free slot give different observations.
- [x] Every card set's pooling also gives its size and the counts of its cards' features, not only their mean and maximum. A test shows a set and the same set doubled pool differently.
- [x] The schema's hash changes, so a checkpoint from before is refused, naming the difference (training starts from scratch).
- [x] The result reports how much the policy's pick probabilities move on recorded card reward decisions when the deck is swapped for the starting deck, for `spec-013.pt` and for this spec's best checkpoint. (A measurement, with no threshold: it shows whether the picks depend on the deck.)

Training:

- [x] A training run with six games and seed 2040, configured like spec 013's comparison (the 2,000,000-step schedule, stopped after 300,000 steps), opens the card reward on at least 95% of the rewards screens that offer one, and has no run fail with "the event was still asking after 50 choices".
- [x] If it does: a training run with six games, seed 2032 and a step budget of 2,000,000 runs to its budget, and its best generation is within 1.0 mean floor and 5 points past the act 1 boss of `spec-013.pt` (19.87, 30.7%) or better. Then the default goes back to six games. Otherwise the default stays at four, and the runs are reported.
- [x] No run in either training run fails with "the event was still asking after 50 choices".

Found in training (amended 2026-10-17, the user's call after the four-game run stopped on the failure budget):

- [x] Mad Science, which the Tinker Time event builds, reaches the observation with only its own type's and rider's numbers, so it fits the numbers a card holds.
- [x] The game's own crashes are still ended as failed runs and logged, but do not count against the failure budget. A test shows crashed runs leave training running.
- [x] A resumed training run starts its failure count afresh, so a run the budget stopped can continue. A test resumes one.

## Result

**Six games.** Training run `runs/20261016-003042` (6 games, seed 2040, the 2,000,000-step schedule), commit `8ca72c7`. At 300,000 steps the agent opened the card reward on 98.4% of the rewards screens that offered one, and no run failed with "the event was still asking after 50 choices". The run was then resumed and went on to its budget, so the 2,000,000-step comparison used seed 2040, not 2032:

| Generation | Mean floor | Past the act 1 boss | Past the act 2 boss |
|---|---|---|---|
| 250,837 steps | 14.05 | 1.5% | 0% |
| 750,405 steps | 15.44 | 9.5% | 0% |
| 1,251,141 steps | 16.69 | 8.0% | 0% |
| 2,000,709 steps | 16.90 | 9.0% | 0% |

Far below `spec-013.pt` (19.87, 30.7%), so the default stays at four games. The skipping moved inside the card reward: the agent opened it and chose Skip, and the share of card rewards taken fell from 61% to 44%.

**Four games.** Training run `runs/20261017-001901` (4 games, seed 2032, default config, `--total-steps 2000000`), commits `8ca72c7` and, from 1,113,280 steps, `6fc1874`. Generations on the 200 evaluation seeds, best action:

| Generation | Mean floor | Past the act 1 boss | Past the act 2 boss | Failed runs |
|---|---|---|---|---|
| Update 245 (250,048 steps) | 18.66 | 24.5% | 0% | 8 |
| Update 490 (500,928 steps) | 18.31 | 26.6% | 1.5% | 1 |
| Update 734 (750,784 steps) | 18.64 | 24.1% | 0.5% | 1 |
| Update 978 (1,000,640 steps) | 19.40 | 28.0% | 2.0% | 0 |
| Update 1222 (1,250,496 steps) | 19.99 | 30.5% | 1.5% | 3 |
| Update 1466 (1,500,352 steps) | 19.18 | 29.6% | 2.5% | 1 |
| Update 1711 (1,750,433 steps) | 19.02 | 30.3% | 1.0% | 5 |
| Update 1955 (2,000,289 steps) | 20.65 | 35.9% | 3.6% | 5 |

The last generation is the best, kept as `spec-014.pt`: against `spec-013.pt`, 0.8 floors further, 5.2 points more past the act 1 boss and 2.1 more past the act 2 boss. Its first generation (18.66, 24.5%) is already near spec 013's at 1,250,000 steps.

**Deck dependence.** Mean total variation distance between the pick probabilities with the real deck and with the run's starting deck, on the card reward decisions in the last third of each run's traces:

| Checkpoint | Decisions | Mean | 0 to 2 cards added | 3 to 7 | 8 or more |
|---|---|---|---|---|---|
| `spec-013.pt` | 4,589 | 0.088 | 0.040 | 0.131 | 0.214 |
| Six games, last | 4,021 | 0.068 | 0.037 | 0.130 | 0.378 |
| `spec-014.pt` | 4,963 | 0.116 | 0.049 | 0.136 | 0.262 |

Every policy picks by its deck, more so as the deck grows; `spec-014.pt` about a third more than `spec-013.pt`.

**Training.** Approximate KL had a mean of 0.015 (clip fraction 0.060); over the second half 0.007, no 50 updates above 0.018. The share of card rewards taken fell per 250,000 steps from 84% to 51%, as in the six-game run but slower: the drift into skipping is not fixed by opening the card reward. Entropy over the last 50 updates: combat 0.33, map 0.11, reward 0.32, card reward 0.51, rest 0.09, card select 1.35, event 0.19, shop 1.14. 87 of 14,232 training runs failed, none with "the event was still asking after 50 choices"; the plan's "Found in training" lists the failures it fixed. Training made 38 steps a second on average.

## Open questions

None.
