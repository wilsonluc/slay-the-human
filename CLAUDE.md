# slay-the-human

An RL agent for Slay the Spire 2. A C# mod drives the real game headless, and a PPO trainer built from scratch learns through self-play.

## Workflow

The repo uses spec-driven development. Feature code follows an approved spec in `specs/NNN-slug/`. Before starting any feature, or when changing behavior, read `specs/README.md` for the process and templates.

## Git

Changes reach `main` only through pull requests. Name branches however you like.

1. Branch off `main`.
2. Push the branch and open a draft PR (`gh pr create --draft`). For a feature, link its spec folder in the PR body.
3. When the spec's `tasks.md` is fully ticked, mark the PR ready (`gh pr ready`). The pr-reviewer plugin (from wilsonluc/pr-tools) then reviews it against the standards below and for bugs, and pr-addresser works through the findings.
4. Merge with squash once the `pr-reviewer` status is green and every review conversation is resolved or answered. The remote deletes the branch after merge.

`.githooks/pre-push` blocks pushes to `main`. Turn it on once per clone: `git config core.hooksPath .githooks`.

## Standards

Before writing or reviewing code, read both standards files:

- the generic standards built into pr-reviewer: `gh api repos/wilsonluc/pr-tools/contents/plugins/pr-reviewer/standards.md -H "Accept: application/vnd.github.raw"`
- `STANDARDS.md`, the rules specific to this repo, which win where the two conflict.

pr-reviewer checks every PR against both.

Name things with the terms in `CONTEXT.md`. When a new term comes up, add it there.

## Reference

`.scrape/` holds material from zhiyue/sts2-rl-agent: their bridge mod, decompiled game source, a Python simulator, and docs. It is gitignored and stays local. Read `.scrape/NOTES.md` before touching game hooks, state reading, run startup, or game speed.

The repo is MIT-licensed public code. Write all code in it from scratch. sts2-rl-agent has no license, and the decompiled code belongs to Mega Crit. Use both to learn how the game works, then write our own implementation.

`GAME_VERSION.md` records the game build this repo targets. The decompiled source may be from an older build. Before relying on a method signature, check it against the installed game.
