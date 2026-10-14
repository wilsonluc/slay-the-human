# Roadmap

Where the project is going, in phases. A phase is a result the agent reaches, checked by an evaluation. Specs (`specs/`) are what we build to get there; each phase lists the specs it needs. Change this file only by pull request.

## Phases

| Phase | Goal | Done when | Needs |
|---|---|---|---|
| 0 | The agent can learn | Every decision in a run goes to the agent, and a training run's agent beats the random agent's mean floor on the evaluation seeds by a set margin within a set number of steps | Specs 001-010 (done: every decision goes to the agent; the training environment; PPO; a reward that pays for progress; evaluation and generations); a results dashboard comparing generations (014) |
| 1.0 | Ironclad, ascension 0 | Evaluation win rate ≥ target | Phase 0; exploration on every decision kind and credit for bosses (011); uncapped frame rate (012); a learning rate that decays over the run (013) |
| 1.1 - 1.10 | Ironclad, ascension 1 to 10 | Evaluation win rate ≥ target, per level | Ascension support |
| 2 | Decided at the end of phase 1 | Recorded below as a decision | |

The game has ascension levels 0 to 10, and they are cumulative: ascension *n* keeps every modifier of the levels below it (`AscensionManager.HasLevel` is `level >= n`). The playable characters are Ironclad, Silent, Defect, Necrobinder and Regent.

**Speed.** Learning a full run from scratch likely takes tens of millions of steps. One game is bound by its frame time, so the training environment (spec 007) runs several games at once. Spec 012 (measured 2026-10-13 and 14, on an 8-core desktop) made frames cheap: in run mode a game keeps every resource it loads, forces no garbage collection on asset loads, and has no frame cap. With random actions, one game went from 7.6 to 13.6 steps a second and four games from 23 to 49; six games make 61 and eight 62, as the games then compete for the cores. Training with the defaults (six games, the update on a GPU) makes 61 steps a second over its first 250,000 steps, against 26 for spec 011's four games: about 5.3 million steps a day, with a game holding at most 2.8 GB. The next lever is batching the policy's inference across games, which takes about a quarter of each game's time; if training is still too slow, then a combat-only environment, before any simulator of the game.

**Ascension 10 ends later.** At ascension 10 the act 3 boss is followed by a second one on floor 49; ascension support must play to it, not stop at floor 48.

Phase 2's choice is made, and written here, when phase 1 ends: keep refining Ironclad, or start another character (Silent first), from scratch or from Ironclad's weights.

## Rules

- **No going back down.** Once a character's training reaches ascension *n*, it trains only at *n* or higher. Each level is the one below it plus one more modifier, so it is strictly harder, and its runs make better training data. Lower levels may still be evaluated, never trained on again.
- **Each level starts from the last.** Phase 1.*n* starts from the checkpoint that finished phase 1.(*n*-1).
- **Targets come from measurements.** The random agent never wins, so phase 0 is judged on mean floor against it, with the margin and step count set from the first measurements. Phase 1.0's target win rate is set from the first agent that wins reliably, and each later level's from the result of the level below. Until then the targets read "to be set".
- **Stop and look before training longer.** If a training run's mean floor has not beaten the random agent's by the set margin by 10 million steps, training stops and the environment, reward and model are examined before any longer run.
- **Evaluation is separate from training.** Win rates are measured on a fixed set of evaluation seeds that training never uses, with the agent choosing its best action rather than sampling.
- **A phase runs on one game build.** Training and evaluation launch from a copy of the game that Steam does not update. Moving to a new build is a deliberate step: a new copy, the mod checked against it, and the vocabulary migrated.
- **A finished phase is reproducible.** Its record names the checkpoint, git commit, training config, game build (`GAME_VERSION.md`), evaluation seed set, and the evaluation result. A result that cannot be traced to its record does not count (`STANDARDS.md`).

## Targets

| Phase | Target | Set from |
|---|---|---|
| 0 | a generation's best-action mean floor at least twice the random agent's (2 x 5.18 = 10.36), within 1,000,000 training steps | the random agent on the evaluation seeds (`docs/baselines/random.json`) |
| 1.0 - 1.10 | win rate, to be set | baseline measurements |

## Record

Finished phases and decisions, newest first.

| Date | Phase | Result | Record |
|---|---|---|---|
| 2026-10-12 | 0 | Passed. Generation at update 245 (250,880 steps): best-action mean floor 15.26 on the 200 evaluation seeds, against a target of 10.36 (the random agent's 5.18, doubled); 2 of 200 runs failed (game crashes), 0 wins, 3.5% past the act 1 boss. | Training run `runs/20261012-122156` (seed 2030, 4 games, default config; checkpoint kept as `phase-0.pt`, result `generations/update-245.json`), commit `bd625ec`, game build 23811903, evaluation seeds hash `c54712d653a9`. |
