# 007: Training environment

Status: draft

## Problem

Since spec 006 the agent makes every decision in a run, but in a shape a learner cannot use. A PPO learner needs a step interface: reset, then step with an action, getting back an observation, which actions are legal, a reward, and whether the episode is over. It needs every observation in one fixed shape and every action at a fixed index. Today each decision is a JSON message whose shape depends on its kind, and its actions are a list that changes length every time.

It also needs many episodes, fast. Today each run launches the game through Steam and the game quits at the end, so every run pays the game's start-up and leaves nothing running for the next.

## Goal

A Python environment a learner can drive one step at a time: each decision of a run comes as a fixed-shape observation with a mask of the legal actions in one fixed action space, each step returns a reward, and one game process plays runs back to back.

## Non-goals

- Learning. PPO is the next spec.
- Evaluation, checkpoints and the results dashboard.
- Several games at once.
- Ascension levels and characters other than the one the environment is created with.

## Acceptance criteria

- [ ] `reset()` starts a new run, with a given seed or a new random one, and returns the first decision's observation and action mask. `step(action)` carries out the action and returns the next observation, the mask, the reward, whether the run is over, and the run's seed, floor and outcome.
- [ ] Every decision kind is encoded into the same fixed-shape observation, and every legal action of every kind has its own index in one fixed action space. The mask marks exactly the legal actions. A card selection that takes several cards is made through the same action space.
- [ ] Every card, relic, potion, monster, power and event the targeted game build has gets its own index, taken from that build. An ID outside that vocabulary fails loudly.
- [ ] An action the mask does not allow is refused with an error naming it; nothing picks an action in its place.
- [ ] The reward is defined in one place and documented, and every step's reward is kept in the run's trace.
- [ ] One game process plays at least 10 runs in a row, each started by `reset()`, without relaunching.
- [ ] A run that fails (the game stops, hangs or disconnects) ends its episode as an error that names the reason and is logged; the next `reset()` starts the game again if it has to.
- [ ] The same seed and the same actions give the same observations, masks and rewards.
- [ ] The environment reports steps per second and runs per hour over a session of random actions.
- [ ] The environment's tests run in CI against a fake game.

## Open questions

