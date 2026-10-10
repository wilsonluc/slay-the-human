# 007: Training environment

Status: draft

## Problem

Since spec 006 the agent makes every decision in a run, but in a shape a learner cannot use. A PPO learner needs a step interface: reset, then step with an action, getting back an observation, which actions are legal, a reward, and whether the episode is over. It needs every observation in one fixed shape and every action at a fixed index. Today each decision is a JSON message whose shape depends on its kind, and its actions are a list that changes length every time.

It also needs many episodes, fast, and the game has to wait for it. One game makes about 7 decisions a second, held back by its own frame time, so a faster game alone cannot give PPO the tens of millions of steps it needs; several game processes at once can, and a measurement showed they run side by side, with identical results, when launched directly rather than through Steam. Today each run launches the game through Steam and the game quits at the end, so every run pays the game's start-up, about 20 seconds. The mod and the game flow also wait fixed real times (after clicks, rooms and rewards) that do nothing for the run. The mod connects only at a run's first decision, so the agent cannot start a run or choose its seed. And the game gives up on a decision after a fixed time, which a learner pausing to update its policy would hit every time.

## Goal

A Python environment a learner can drive one step at a time, laid out as `docs/architecture.md` describes: each decision of a run comes as a fixed-shape observation with a mask of the legal actions in one fixed action space, each step returns a reward, several game processes run at once, each playing runs back to back, and the game waits for the learner as long as it takes.

## Non-goals

- Learning. PPO is the next spec.
- Evaluation, checkpoints and the results dashboard.
- Ascension above 0 (`ROADMAP.md`: ascension support), and changing character between runs; the environment is created with one character.
- Discarding potions. The game allows it, the agent does not yet; a potion reward stays masked while the slots are full.

## Acceptance criteria

Interface:

- [ ] The environment has the Gymnasium shape (`docs/architecture.md`): `reset(seed)` starts a new run, with the given game seed (letters and digits) or a new random one that is recorded, and returns the first decision's observation and an info dict; `step(action)` returns the next observation, the reward, `terminated`, `truncated` and an info dict with the run's seed, floor and outcome; `action_masks()` returns the legal actions.
- [ ] The environment starts each run itself, with its seed and character, over the bridge. `docs/protocol.md` documents the change under a new protocol version.

Observation and actions:

- [ ] Every decision kind is encoded into the same fixed-shape observation: a dict with one padded array per set (`docs/architecture.md`), each with a presence mask, and numbers scaled to a small fixed range. Each set's size is written in one place, the environment logs the largest size it has seen of each, and a decision that does not fit fails loudly.
- [ ] The observation carries everything a player can look up, so the policy needs no memory. The mod sends it under the new protocol version:
  - Every card, wherever it appears (deck, hand, piles, rewards, selections, bundles, shop), is the same card object: its ID, upgrade, current base numbers (damage, block, main magic number, so cards that grow are seen as grown), keywords, enchantment and affliction with their amounts, and in hand its cost and its numbers after modifiers.
  - In combat, the contents of the draw, discard and exhaust piles as unordered sets of cards.
  - Every decision carries the map with the current position, and the act's boss (and second boss, when there is one); a decision made in combat carries the room's encounter and the combat state, including a card selection made mid-combat.
- [ ] Every legal action of every kind has its own index in one fixed action space, and the mask marks exactly the legal actions.
- [ ] A card selection that takes several cards is made as single picks, each its own step: picks go in ascending index order, the observation marks the cards already picked, confirm is legal once the minimum is picked, and the selection submits itself at the maximum.
- [ ] Every ID and named value the observation encodes (cards, relics, potions, monsters, encounters, powers, events, enchantments, afflictions, intents, map point types, rest options and the rest) has its own index, keyed by category so the same name in two categories gets two indices, in a vocabulary taken from the targeted game build. The vocabulary is a committed file that only grows: new values are appended and removed ones keep their index. It has a content hash, the mod reports the game build at the start of the connection, and the environment refuses a build its vocabulary was not made from. A value outside the vocabulary fails loudly.
- [ ] An action the mask does not allow is refused with an error naming it, and the episode ends as an error (`STANDARDS.md`); nothing picks an action in its place.

Reward:

- [ ] The reward is defined in one place and documented there: `+1` for a win, `-1` for a loss, plus shaping terms. Each shaping term is potential-based, `w * (gamma * score(next state) - score(state))` with `gamma` the learner's discount, so it never changes which policy is best; the scores fall to zero when the run is terminated (a win or a loss), not when it is truncated. The scores are: floor reached as a fraction of a full run; HP as a fraction of max HP; combat progress over the run, which is the combats won plus the current combat's fraction of enemy HP removed (each summoned enemy's HP added when it appears), divided by the most combats a run can have, so finishing a fight never lowers it; and elites and bosses killed. Each term has its own weight, set in one place, chosen so the term's weighted score stays within ±1; the return then needs no scaling.
- [ ] Every step's outcome reward and each term's score are kept in the run's trace, so the learner computes shaping with its own discount and changing the discount never rewrites stored rewards. Per run, the environment reports each term's discounted contribution, its highest score and its score just before the run ended, so a term the agent exploits shows up.

Runs and failures:

- [ ] Several game processes run at once, each its own environment. The number is a setting, not tied to one machine. The environment launches each game directly (not through Steam), staggering start-ups so none times out while the others load.
- [ ] The environment launches the game from a copy of the game folder kept outside Steam's library, one copy per game build, so a Steam update never changes the game under a training run. `GAME_VERSION.md` records the build and a hash of the copy, and the environment refuses a copy whose hash does not match.
- [ ] Run mode fixes the run's unlocks to everything unlocked and writes no profile file, so a seed's content depends neither on the profile nor on earlier runs in the process, and training never touches the player's own save.
- [ ] Each game process plays at least 10 runs in a row, each started by `reset()`, without relaunching.
- [ ] Between decisions, the mod and the game flow wait on the game's state, not on fixed times; the only fixed time left is the hang detection below.
- [ ] The game waits for each action with no time limit: a run is not failed because the learner was slow to answer.
- [ ] Only a win or a loss is `terminated`. A run that fails (the game stops, or sends no decision within a set time after an action) ends its episode as `truncated`, with the reason, decision kind and floor logged as an error; that step returns the last decision's observation, and the info's outcome names the failure. The next `reset()` starts the game again if it has to.
- [ ] A run that reaches a set number of steps ends as `truncated`, with the outcome naming the step limit.
- [ ] The same seed and the same actions give the same observations, masks and rewards: in a fresh game process or after other runs, alone or alongside other game processes, with the machine otherwise idle or busy, and whatever the profile has unlocked.

Measurement and tests:

- [ ] A command plays a given number of runs with random actions across a given number of game processes and prints steps per second (per game and in total), runs per hour and the floor reached, so the number of games can be chosen on any machine.
- [ ] The environment's tests run in CI against a fake game that speaks `docs/protocol.md`, and the encoding round-trips recorded decisions of every kind.

## Open questions

