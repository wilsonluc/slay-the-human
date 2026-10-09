# Standards

Rules that all code in this repo follows. Reviews check every change against every rule here.

## DRY: one source of truth

Every piece of knowledge has one authoritative home: a game constant, a protocol field name, an observation layout, a reward formula. Changing that knowledge is a one-place edit.

- DRY is about knowledge, not text. Two blocks that look alike but would change for different reasons stay separate. Merging them couples unrelated things.
- Extract on the third copy (the rule of three). Two copies are a note to watch. Three copies are a refactor.
- Before writing a helper, constant, or type, search the repo for an existing one and reuse it.
- Cross-language knowledge (for example, a C# mod and a Python trainer sharing a protocol) has one defining side or one shared schema. The other side derives from it or is checked against it by a test.
- Docs follow the same rule. Point to the source of truth (code, config, `--help`) instead of restating it.

## YAGNI: build what the spec asks for

The scope of a change is the acceptance criteria of its approved spec (see `specs/README.md`). Code serves those criteria and nothing else.

- Build for today's caller. Add configuration, parameters, and extension points when a second real use appears.
- An abstraction needs two concrete implementations to exist. One implementation is a plain function or class.
- Delete dead code, unused parameters, and commented-out blocks. Git history keeps them.
- When a future need is likely, write it down as an open question or a future spec. Leave the code at what is needed now.
- Never cut these for YAGNI: input validation at trust boundaries, error handling that prevents data loss or corrupt training data, and the test that proves an acceptance criterion.
