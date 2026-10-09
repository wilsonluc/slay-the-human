# Glossary

Each term means exactly this in code, specs, and docs. Use these words. When a new term comes up, define it here.

## Game

- **Run**: one playthrough, from choosing a character to dying or winning.
- **Act**: one section of a run. Each act has its own map and ends with a boss.
- **Room**: one node on the map: monster, elite, boss, event, shop, treasure, or rest site (the game's `RoomType`).
- **Floor**: the count of rooms entered so far in the run (the game's `RunState.TotalFloor`). A floor is a game position, not a unit of training time.
- **Encounter**: the specific group of monsters a combat room uses (the game's `EncounterModel`).
- **Combat**: one fight, from the start until all enemies are dead or the player is.
- **Turn**: the player's phase inside a combat, when cards are played. The player ends it by ending the turn.
- **Round**: one player turn plus the enemy turn after it (the game's `CombatState.RoundNumber`).
- **Intent**: the move an enemy shows it will make on its next turn.

## Agent and training

- **Game state**: everything the mod reads from the game at one moment.
- **Observation**: the fixed-shape encoding of the game state that the policy receives.
- **Decision**: a point where the game waits for a choice, such as play a card, end the turn, pick a map node, or take a reward.
- **Action**: the choice made at a decision.
- **Action mask**: which actions are legal at the current decision.
- **Step**: one decision, the action taken, and the state that results. A step is the unit of training time.
- **Episode**: everything from an environment reset to the end. Depending on the environment, that is one combat or one run.
- **Rollout**: the batch of steps collected under the current policy before one PPO update.
