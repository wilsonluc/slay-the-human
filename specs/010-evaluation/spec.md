# 010: Evaluation and generations

Status: approved

## Problem

Training reports how its own runs went, on seeds it draws as it goes, with the policy sampling its actions. That cannot compare two checkpoints fairly: they played different dungeons, and sampling adds noise. Phase 0 (`ROADMAP.md`) is judged "on the evaluation seeds", against the random agent, by a margin set from the first measurements; none of that exists yet. Nor do generations: the dashboard (spec 011) is meant to compare evaluated checkpoints, and training keeps only its latest checkpoint, so a good one is overwritten by the next.

## Goal

A fixed set of evaluation seeds that training never plays; `python -m agent.evaluate` plays a checkpoint (or the random agent) on all of them, with its best action and again by sampling, and records the result; training evaluates its checkpoint every so often, turning it into a generation and keeping the best and the latest few; and phase 0's target is set from the random agent's baseline.

## Non-goals

- The dashboard. Spec 011.
- Replaying the level below to catch forgetting (`docs/architecture.md`). It needs ascension, so it comes with the ascension spec.
- Win-rate targets for phase 1. They are set from the first agent that wins reliably (`ROADMAP.md`).

## Acceptance criteria

Evaluation seeds:

- [ ] A fixed list of evaluation seeds is committed, with its size and how it was made recorded beside it. Training never plays one: the environment refuses an evaluation seed outside an evaluation, and a training run's game seeds are drawn so they cannot be one.

Evaluating:

- [ ] `python -m agent.evaluate <checkpoint>` plays every evaluation seed twice on several games at once: once with the policy's best action (the masked argmax), which is the official result, and once by sampling, with sampling seeds fixed per evaluation seed. `python -m agent.evaluate random` plays the random agent on the same seeds, with fixed seeds.
- [ ] It writes a result: for each seed and mode, the outcome, floor, act reached, steps and failure reason; and for each mode, the mean floor, win rate, the share of runs past each act's boss, and failed runs. The result names the checkpoint, its training run, the evaluation seed set's hash, the game build, the git commit, and the vocabulary, schema, protocol and reward hashes.
- [ ] The same checkpoint and seeds give the same best-action results, run after run, alone or with other games running.
- [ ] Every evaluation run keeps its full trace (spec 007).
- [ ] A run that fails during an evaluation is reported as failed, never counted as a loss or a win; an evaluation whose failed runs pass a set share is marked invalid.

Generations:

- [ ] Training evaluates its checkpoint every set number of steps, with the best action only (sampling is for `agent.evaluate`), and saves that checkpoint as a generation in its training run folder, with its result. The time evaluating is reported apart from training's steps per second.
- [ ] Training keeps the best generation (by best-action mean floor while no run wins, by win rate once one does) and the latest few; older ones are deleted.
- [ ] Each generation's result goes in `runs/<training run>/generations.csv`, one row per generation, which the dashboard will read.

Baseline and target:

- [ ] The random agent's evaluation on the seed set is recorded in the repo as phase 0's baseline.
- [ ] Phase 0's target is written in `ROADMAP.md`: a generation whose best-action mean floor is at least twice the random agent's, within 1,000,000 training steps. A training run under this spec, with generations, is evaluated against it (spec 009's checkpoint predates the potion-slot change and no longer loads), and the result is recorded in the roadmap's record when it passes.

Tests:

- [ ] Tests in CI, without the game: the seed set's hash; the refusal of an evaluation seed in training; best action is the masked argmax; the result file's fields; keeping the best and latest generations; the invalid mark on too many failures. `agent.evaluate` runs end to end on the fake game.

## Open questions

None.
