# slay-the-human

An RL agent for Slay the Spire 2. A C# mod drives the real game headless, and a PPO trainer built from scratch learns through self-play.

## Workflow

The repo uses spec-driven development. Feature code follows an approved spec in `specs/NNN-slug/`. Before starting any feature, or when changing behavior, read `specs/README.md` for the process and templates.

## Git

Changes reach `main` only through pull requests. Name branches however you like.

1. Branch off `main`.
2. Push the branch and open a draft PR (`gh pr create --draft`). For a feature, link its spec folder in the PR body.
3. When the spec's `tasks.md` is fully ticked, mark the PR ready (`gh pr ready`).
4. Merge with squash. The remote deletes the branch after merge.

`.githooks/pre-push` blocks pushes to `main`. Turn it on once per clone: `git config core.hooksPath .githooks`.

## Standards

Before writing or reviewing code, read `STANDARDS.md`. It covers DRY and YAGNI.

## Reference

`.scrape/` holds material from zhiyue/sts2-rl-agent: their bridge mod, decompiled game source, a Python simulator, and docs. It is gitignored and stays local. Read `.scrape/NOTES.md` before touching game hooks, state reading, run startup, or game speed.

The decompiled source matches the May 2026 build. Before relying on a method signature, check it against the installed game.
