# 007: Training environment

Status: draft

## Problem

Since spec 006 the agent makes every decision in a run, but in a shape a learner cannot use. A PPO learner needs a step interface: reset, then step with an action, getting back an observation, which actions are legal, a reward, and whether the episode is over. It needs every observation in one fixed shape and every action at a fixed index. Today each decision is a JSON message whose shape depends on its kind, and its actions are a list that changes length every time.

It also needs many episodes, fast, and the game has to wait for it. Today each run launches the game through Steam and the game quits at the end, so every run pays the game's start-up. The mod connects only at a run's first decision, so the agent cannot start a run or choose its seed. And the game gives up on a decision after a fixed time, which a learner pausing to update its policy would hit every time.

## Goal

A Python environment a learner can drive one step at a time, laid out as `docs/architecture.md` describes: each decision of a run comes as a fixed-shape observation with a mask of the legal actions in one fixed action space, each step returns a reward, one game process plays runs back to back, and the game waits for the learner as long as it takes.

## Non-goals

- Learning. PPO is the next spec.
- Evaluation, checkpoints and the results dashboard.
- Several games at once.
- Ascension above 0 (`ROADMAP.md`: ascension support), and changing character between runs; the environment is created with one character.
- Discarding potions. The game allows it, the agent does not yet; a potion reward stays masked while the slots are full.

## Acceptance criteria

Interface:

- [ ] The environment has the Gymnasium shape (`docs/architecture.md`): `reset(seed)` starts a new run, with the given game seed (letters and digits) or a new random one that is recorded, and returns the first decision's observation and an info dict; `step(action)` returns the next observation, the reward, `terminated`, `truncated` and an info dict with the run's seed, floor and outcome; `action_masks()` returns the legal actions.
- [ ] The environment starts each run itself, with its seed and character, over the bridge. `docs/protocol.md` documents the change under a new protocol version.

Observation and actions:

- [ ] Every decision kind is encoded into the same fixed-shape observation: a dict with one padded array per set (`docs/architecture.md`), each with a presence mask, and numbers scaled to a small fixed range. Each set's size is written in one place, the environment logs the largest size it has seen of each, and a decision that does not fit fails loudly.
- [ ] Every legal action of every kind has its own index in one fixed action space, and the mask marks exactly the legal actions.
- [ ] A card selection that takes several cards is made as single picks, each its own step: picks go in ascending index order, the observation marks the cards already picked, confirm is legal once the minimum is picked, and the selection submits itself at the maximum.
- [ ] Every ID and named value the observation encodes (cards, relics, potions, monsters, powers, events, enchantments, afflictions, intents, map point types, rest options and the rest) has its own index in a vocabulary taken from the targeted game build. The vocabulary is a committed file that only grows: new values are appended and removed ones keep their index. It has a content hash, the mod reports the game build at the start of the connection, and the environment refuses a build its vocabulary was not made from. A value outside the vocabulary fails loudly.
- [ ] An action the mask does not allow is refused with an error naming it, and the episode ends as an error (`STANDARDS.md`); nothing picks an action in its place.

Reward:

- [ ] The reward is defined in one place and documented there: `+1` for a win, `-1` for a loss, plus shaping terms. Each shaping term is the change in a score of the state from one step to the next (potential-based, so it never changes which policy is best), and the scores fall to zero when the run ends. The scores are: floor reached as a fraction of a full run; HP as a fraction of max HP; within a combat, the fraction of the enemies' HP removed; and elites and bosses killed. Each term has its own weight, set in one place.
- [ ] Every step's reward is kept in the run's trace, split by term, and the environment reports each term's total per run, so a term the agent exploits shows up.

Runs and failures:

- [ ] One game process plays at least 10 runs in a row, each started by `reset()`, without relaunching.
- [ ] The game waits for each action with no time limit: a run is not failed because the learner was slow to answer.
- [ ] Only a win or a loss is `terminated`. A run that fails (the game stops, or sends no decision within a set time after an action) ends its episode as `truncated`, with the reason, decision kind and floor logged as an error; that step returns the last decision's observation, and the info's outcome names the failure. The next `reset()` starts the game again if it has to.
- [ ] A run that reaches a set number of steps ends as `truncated`, with the outcome naming the step limit.
- [ ] The same seed and the same actions give the same observations, masks and rewards: in a fresh game process or after other runs, with the machine otherwise idle or busy, and whatever the profile has unlocked.

Measurement and tests:

- [ ] A command plays a given number of runs with random actions through the environment and prints steps per second, runs per hour and the floor reached. The numbers go into `ROADMAP.md`'s phase 0 decision point.
- [ ] The environment's tests run in CI against a fake game that speaks `docs/protocol.md`, and the encoding round-trips recorded decisions of every kind.

## Open questions

