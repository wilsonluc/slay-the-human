# 011: Exploration and credit for bosses

Status: approved

## Problem

The phase 0 training run (`runs/20261012-122156`, spec 010) passed its target at 250,000 steps, then stopped improving:

| | 250k generation | 500k generation |
|---|---|---|
| Best-action mean floor | 15.26 | 14.26 |
| Runs past the act 1 boss | 3.5% | 0.5% |
| Runs that died on floor 17 (the act 1 boss) | 113 of 200 | 97 of 200 |

The agent learned to reach the act 1 boss, not to beat it. It reaches the boss with the starting deck: over the last 30 training runs it opened the card reward 22 times, against several combats a run, and most runs end with 10 to 12 cards (10 at the start). On the rewards screen it takes the gold and proceeds, leaving the card. Four things hold it there:

- **It stopped trying other choices.** Policy entropy fell early and fell furthest on the rare decisions. Between update 11 and update 301: card reward 1.38 to 0.10, map 0.64 to 0.08, rest 0.69 to 0.002, event 0.85 to 0.13. The entropy bonus is averaged over steps, and combat is most of the steps, so the bonus barely reaches the decisions that build the deck. Once those decisions are near certain, the agent no longer tries the alternatives, and cannot learn what they are worth.
- **A boss pays like any other floor.** Killing a boss pays one kill and one floor, each 1/48: about 0.04, against 1 for a win. Nothing marks the act 1 boss as the wall it is.
- **Credit does not reach far enough back.** A card taken on floor 3 pays off at the boss on floor 17, hundreds of decisions later. GAE's lambda of 0.95 weights the next 20 or so decisions; past that, credit rests on the value estimate alone.
- **The updates are tiny.** Approximate KL stays near 0.001 and the clip fraction under 1%, so each update moves the policy very little, and a habit takes a long time to unlearn.

## Goal

A training run that keeps trying every kind of decision, pays for beating a boss, carries credit back from the boss to the choices that built the deck, and updates at a pace PPO is designed for; and beats the phase 0 run past the act 1 boss.

## Non-goals

- Model size or architecture.
- A combat-only environment, a simulator, or a curriculum.
- Forcing any choice, such as always taking a card: skipping a card is a real strategy, and the agent must learn when to.
- Phase 1.0's win rate target (`ROADMAP.md`): it is still set from the first agent that wins reliably.
- The results dashboard (now spec 012).

## Acceptance criteria

Exploration:

- [ ] The entropy bonus gives each decision kind (combat, map, card reward, reward, rest, shop, event, card select, treasure, and the rest) equal weight, whatever its share of the steps. A test shows a rare decision kind's entropy pulls on the loss as much as combat's.
- [ ] At the end of the training run below, every decision kind that appears at least once per run on average has entropy of at least 0.2 in `metrics.csv`.

Reward:

- [ ] Each boss killed pays a bonus of its own, one act's share of a win (1/3), on top of the floor and kill it already pays. It is progress: paid once, when it happens, never taken back. Its weight and reasons are documented with the other terms.
- [ ] The tests on worked example runs (spec 009) still pass, and a new one shows a loss just after the act 1 boss returns clearly more than a loss at it.
- [ ] The reward's hash changes.

Learning settings:

- [ ] GAE lambda is 0.99 by default.
- [ ] The default learning rate (or epochs) is raised so that, over the training run below, the mean approximate KL per update is between 0.005 and 0.03 and the mean clip fraction under 0.3.

Measurement:

- [ ] `metrics.csv` reports the share of card rewards taken (a card picked, out of card rewards offered), so deck-building behaviour shows without reading traces.

Training:

- [ ] A training run with these changes, otherwise configured like the phase 0 run (4 games, generations every 250,000 steps), runs to 1,000,000 steps. A generation's best-action share of runs past the act 1 boss is at least 15%, against 3.5% for phase 0's best.
- [ ] If it falls short, the run is reported with its metrics before any change to these settings.

## Open questions

None.
