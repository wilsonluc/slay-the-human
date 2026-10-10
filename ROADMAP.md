# Roadmap

Where the project is going, in phases. A phase is a result the agent reaches, checked by an evaluation. Specs (`specs/`) are what we build to get there; each phase lists the specs it needs. Change this file only by pull request.

## Phases

| Phase | Goal | Done when | Needs |
|---|---|---|---|
| 0 | The agent can learn | Every decision in a run goes to the agent, and one training run works end to end | Specs 001-006 (done: every decision goes to the agent); the training environment; PPO; evaluation and checkpoints; a results dashboard comparing generations (React and MUI X, hosted on GitHub Pages) |
| 1.0 | Ironclad, ascension 0 | Evaluation win rate ≥ target | Phase 0 |
| 1.1 - 1.10 | Ironclad, ascension 1 to 10 | Evaluation win rate ≥ target, per level | Ascension support |
| 2 | Decided at the end of phase 1 | Recorded below as a decision | |

The game has ascension levels 0 to 10, and they are cumulative: ascension *n* keeps every modifier of the levels below it (`AscensionManager.HasLevel` is `level >= n`). The playable characters are Ironclad, Silent, Defect, Necrobinder and Regent.

Phase 2's choice is made, and written here, when phase 1 ends: keep refining Ironclad, or start another character (Silent first), from scratch or from Ironclad's weights.

## Rules

- **No going back down.** Once a character's training reaches ascension *n*, it trains only at *n* or higher. Each level is the one below it plus one more modifier, so it is strictly harder, and its runs make better training data. Lower levels may still be evaluated, never trained on again.
- **Each level starts from the last.** Phase 1.*n* starts from the checkpoint that finished phase 1.(*n*-1).
- **Targets come from measurements.** Each phase's target win rate is set after measuring a baseline: first a random agent, then the first PPO agent at ascension 0. Until then the targets read "to be set".
- **Evaluation is separate from training.** Win rates are measured on a fixed set of evaluation seeds that training never uses, with the agent choosing its best action rather than sampling.
- **A finished phase is reproducible.** Its record names the checkpoint, git commit, training config, game build (`GAME_VERSION.md`), evaluation seed set, and the evaluation result. A result that cannot be traced to its record does not count (`STANDARDS.md`).

## Targets

| Phase | Target win rate | Set from |
|---|---|---|
| 1.0 - 1.10 | to be set | baseline measurements |

## Record

Finished phases and decisions, newest first.

| Date | Phase | Result | Record |
|---|---|---|---|
