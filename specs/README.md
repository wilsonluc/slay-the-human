# Specs

Every feature starts here as a spec. Code follows an approved spec. When code and spec disagree, update the spec first.

## Process

Each feature gets its own folder, `specs/NNN-slug/` (for example `specs/001-run-bootstrap/`). Number folders in order.

1. **Spec** — write `spec.md`: what the feature is and why it's needed. Leave out how it gets built. *Done when* every acceptance criterion is a pass/fail check a reviewer can run, and the open questions section is empty.
2. **Approve** — the user reads `spec.md` and says it's approved. Set `Status: approved`. *Done when* the user has said so. The agent never self-approves.
3. **Plan** — write `plan.md`: how it gets built, meaning the files touched, interfaces, risks, and how each acceptance criterion gets verified. *Done when* every acceptance criterion maps to a verification step.
4. **Tasks** — write `tasks.md`: an ordered checklist of small steps. Each step can be verified on its own. *Done when* finishing every task would satisfy every acceptance criterion.
5. **Build** — work through `tasks.md`, ticking boxes as you go. If a task contradicts the spec, stop and revise `spec.md` with the user. *Done when* every box is ticked and every acceptance criterion has been checked and passes.
6. **Close** — set `Status: done` in `spec.md`.

Small fixes that change no behavior (typos, renames) skip this process.

## Templates

### spec.md

```markdown
# NNN: Title

Status: draft | approved | done

## Problem
Why this matters. What breaks or stays impossible without it.

## Goal
What exists when this is done, in one or two sentences.

## Non-goals
What this deliberately leaves out.

## Acceptance criteria
- [ ] Pass/fail check a reviewer can run.

## Open questions
- Question, and who answers it.
```

### plan.md

```markdown
# NNN: Plan

## Approach
How it works, briefly.

## Changes
- `path/to/file` — what changes.

## Verification
- Acceptance criterion → how it is checked (command, test, log line).

## Risks
- Risk → mitigation.
```

### tasks.md

```markdown
# NNN: Tasks

- [ ] 1. Smallest verifiable step.
```
