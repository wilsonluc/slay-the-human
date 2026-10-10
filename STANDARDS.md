# Standards

The generic [standards built into pr-reviewer](https://github.com/wilsonluc/pr-tools/blob/main/plugins/pr-reviewer/standards.md) apply to all code here. This file adds the rules specific to this repo, and wins where the two conflict. Reviews check every change against both.

## Scope is the spec

A feature's scope is the acceptance criteria of its approved spec (see `specs/README.md`). When a future need is likely, write it down as an open question or a future spec.

## Fail loud in training

Training data records only actions the policy actually chose.

- When the game hangs, the agent disconnects, or the agent returns an invalid action, the episode ends as an error and is logged. It never continues on a substitute action such as a random card.
- Report game state the mod cannot read as an error.
- A game hook that fails to apply stops the mod at startup.

## Reproducible runs

An evaluation can be rerun to get the same result: the same checkpoint, evaluation seeds and sampling seeds give the same outcomes. A training run can be traced and repeated: a rerun gives a statistically similar result, not a bit-identical one, because hangs and parallel games depend on the machine.

- Each run records its seed, full config, git commit, game build (`GAME_VERSION.md`), vocabulary, schema and reward hashes, and protocol version next to its outputs.
- Seed every source of randomness (game seed, environment, policy, sampling) from the recorded seed, in a fixed order for each game.
- A result that cannot be traced to its recorded run does not count. Rerun it.
