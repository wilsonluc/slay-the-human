# 014: Plan

## Approach

### Rewards screen

`Encoder.actions` (`agent/env/encoding.py`) leaves proceeding out of a rewards screen's legal actions while the screen offers to take a card reward or gold. The rule reads the actions the game offers, not the rewards listed, so a card reward the agent skipped (which the mod no longer offers) does not hold the screen. The card reward screen keeps Skip. Potions, relics, special cards and card removal stay optional.

### Stuck rewards screen after an event's fight

Every case found was the Punch Off event, one of the events in the combat layout (Punch Off, The Lantern Key). Its option starts a fight with `shouldResumeAfterCombat: false`, which pushes a combat room without leaving the event room. After the win, the rewards screen's proceed button opens the map and nothing else: the rewards screen stays on the overlay stack and the event room stays alive, with whatever reward was left still takeable. `AgentEvent`'s loop sees a screen open over a live event room and drains it again, each pass counting as one of the event's 50 choices, so the agent was offered the same rewards screen until the loop gave up.

The fix, in `mod/AgentEvent.cs`: the event is over once the current room is a combat room that does not resume its event and no combat is starting or in progress. The handler returns, and AutoSlay's screen loop after the room answers the rewards screen once; it stops when the map opens. Events whose combat resumes them are untouched, and events that fade to a separate combat room already leave through the room-closed branch.

### What the policy sees

The mod sends every card's cost (`cost`, `costs_x`, `star_cost`) wherever the card appears, not only in hand (`mod/GameState.cs`); a canonical card gives its printed star cost. The protocol goes to version 5. The encoding:

- gives every card its cost, X cost, star cost, and whether it has each; and all its numbers besides damage and block, up to 6 in the game's order (the traces' most is 4; more raises, naming them);
- gives every card how many copies of it, by ID and upgrade, the deck holds (`slog`);
- adds the sizes of the deck, hand, draw pile, discard pile and exhaust pile, the potions held and the belt's slots to the global numbers;
- encodes a special card reward's card in a `reward_cards` set aligned with the rewards, which the model adds to the reward's entity, as it does for a shop's cards.

`pool` (`agent/ppo/model.py`) gives each set's sum, divided by the set's capacity, besides its mean and max: the set's size and the counts of its cards' features. The schema revision goes to 2, so the schema hash changes and an older checkpoint is refused.

### Training

As spec 013: `--total-steps 2000000`, seed 2040 with six games stopped after 300,000 steps, then seed 2032 with six games for the full budget. The share of rewards screens offering a card reward on which it was opened is counted from the traces (`scratchpad` analysis, as in the spec's table).

## Changes

- `mod/GameState.cs`: cost for every card. `mod/Bridge.cs`, `agent/bridge.py`, `docs/protocol.md`: protocol 5.
- `mod/`: the stuck rewards screen's fix.
- `agent/env/encoding.py`: card floats, copies, global sizes, `reward_cards`, the proceed rule, schema revision 2.
- `agent/ppo/model.py`: sum pooling, `reward_cards`.
- `agent/tests/recordings/decisions.jsonl`: recorded again under protocol 5.
- `agent/tests/test_encoding.py`, `agent/tests/test_model.py`: tests below.
- `agent/ppo/config.py`, `README.md`, `docs/architecture.md`, `ROADMAP.md`: the number of games, if it changes; the observation's description.

## Verification

- Proceed rule → a test on the recorded rewards screen: proceed is illegal while a card or gold reward can be taken, legal once only a potion, a relic or nothing is left.
- Skip kept → a test on the recorded card reward: Skip is legal.
- Stuck screen → the cause named here, and no "the event was still asking after 50 choices" in either training run's game logs.
- Sizes and copies → tests: two decks differing only in copies give different deck floats, global sizes and model states; combat piles' sizes in the globals.
- Cost and numbers → a test on recorded cards outside the hand: cost floats set; a card with several numbers keeps them all.
- Special card → a test: a rewards screen with a special card fills `reward_cards` in its slot.
- Potions → a test: a full belt and one with a free slot differ in the globals.
- Pooling → a test: a set and the same set doubled pool differently.
- Schema → the checkpoint test refuses a checkpoint with another schema hash (existing), and the hash differs from spec 013's.
- Deck dependence → a script, scratchpad: for recorded card reward decisions from the training traces, the mean total variation distance between pick probabilities with the real deck and with the starting deck, for `spec-013.pt` (in its own code's encoding, at commit 449bacc) and for this spec's best checkpoint.
- Training → `metrics.csv`, `generations.csv` and the traces, as spec 013.

## Risks

- Restarting from scratch loses spec 013's 2,000,000 steps → the 2,000,000-step run is compared with `spec-013.pt` before the default changes.
- Forcing the card reward open adds a decision to most rewards screens → small; the card reward's Skip is one step.
- Measuring `spec-013.pt` needs its own encoding → run from a worktree at 449bacc.
