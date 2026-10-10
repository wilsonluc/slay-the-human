# Glossary

Each term means exactly this in code, specs, and docs. Use these words. When a new term comes up, define it here.

## Game

- **Run**: one playthrough, from choosing a character to dying or winning.
- **Act**: one section of a run. Each act has its own map and ends with a boss.
- **Room**: one node on the map: monster, elite, boss, event, shop, treasure, or rest site (the game's `RoomType`).
- **Floor**: the count of rooms entered so far in the run (the game's `RunState.TotalFloor`). A floor is a game position, not a unit of training time.
- **Ascension**: the run's difficulty level, 0 to 10 (the game's `AscensionLevel`). Levels are cumulative: ascension n has every modifier of the levels below it.
- **Encounter**: the specific group of monsters a combat room uses (the game's `EncounterModel`).
- **Combat**: one fight, from the start until all enemies are dead or the player is.
- **Turn**: the player's phase inside a combat, when cards are played. The player ends it by ending the turn.
- **Round**: one player turn plus the enemy turn after it (the game's `CombatState.RoundNumber`).
- **Intent**: the move an enemy shows it will make on its next turn.

## Agent and training

- **Agent**: the Python program that makes the decisions in a run, on the other side of the bridge (`docs/protocol.md`): first the random agent (`agent/random_agent.py`), then the PPO policy trained from scratch. Never a language model.
- **Policy**: the neural network that maps an observation to a probability for each legal action. The trained agent samples from it, or takes its best action in an evaluation.
- **Game state**: everything the mod reads from the game at one moment.
- **Observation**: the fixed-shape encoding of the game state that the policy receives.
- **Decision**: a point where the game waits for a choice, such as play a card, end the turn, pick a map node, or take a reward.
- **Action**: the choice made at a decision.
- **Action mask**: which actions are legal at the current decision.
- **Step**: one action the policy chooses and the state that results. A selection of several cards takes several steps. A step is the unit of training time.
- **Episode**: everything from an environment reset to the end. Depending on the environment, that is one combat or one run.
- **Terminated**: an episode that ended in the game: a win or a loss.
- **Truncated**: an episode cut short by a failure (the game stopped, hung or disconnected). The learner bootstraps from the value estimate instead of treating it as a loss.
- **Trace**: the record of every decision, action and reward in a run (`.trace.jsonl`).
- **Vocabulary**: every ID and named value of the targeted game build, each with its own index for the observation, identified by a content hash.
- **Training run**: one training session, from start to stop, with its record in `runs/<training run>/`. Not a run of the game.
- **Rollout**: the batch of steps collected under the current policy before one PPO update.
- **Checkpoint**: the saved policy weights at one point in training, with the record of what produced them.
- **Generation**: a checkpoint that was evaluated. The dashboard compares generations on the same evaluation seeds.
- **Evaluation**: measuring a checkpoint's win rate on a fixed set of evaluation seeds that training never uses, with the agent choosing its best action.
- **Baseline**: an evaluation of a reference agent (random, then the first PPO agent) that a phase's target is set from.

## Roadmap

- **Phase**: a result the agent must reach, checked by an evaluation, such as Ironclad at ascension 0. `ROADMAP.md` lists them.
- **Target**: the evaluation win rate that finishes a phase.
