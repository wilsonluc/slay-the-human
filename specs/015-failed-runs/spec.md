# 015: Failed runs

Status: draft

## Problem

Training runs fail at a few per thousand, and most failures have causes in our own code or in AutoSlay's, not chance. Counted over the three training runs since 2026-10-14 (spec 013's result run, spec 014's six-game and four-game runs):

| Failure | Count | Cause |
|---|---|---|
| The game closed the connection | 139 | About half are the game's own crashes (a Spine object freed on the .NET finalizer thread, which its developers know of), logged by Windows; most of the rest are native crashes its crash reporter catches first. 17 are not crashes: AutoSlay failed the run and quit, and the trainer did not read its error line ("Run failed with seed"), so the failure is labelled a crash and, since spec 014, does not count against the failure budget. |
| Timed out | 32 | Two hangs in the mod. After the Battleworn Dummy event's fight at its second and third settings, the event returns to its last page with no screen open, which the mod's wait does not expect (12 of 20 in the four-game run). The Crystal Sphere offers switching tools on every choice, a switch spends nothing, and a policy that keeps switching reaches the choice limit with divinations left, after which the minigame never finishes (8 of 20). |
| A rest site button disposed | 6 | With the Miniature Tent, a second option can be chosen at a rest site. After Smith as a later option the mod's wait passes at once (the proceed button is already enabled), and it offers the old buttons again; clicking one fails the run. 6 of the 9 visits that chose a second option. |
| Floor 49 | 2 | AutoSlay stops playing at total floor 49 and abandons the run, and the abandon itself fails in this build. When the act 3 boss is on floor 50, a run that reaches the rest site before it is ended there: these are the agent's best runs. |
| An exhaust pile past 300 | 2 | A fight neither side can win (slimes adding Slimed, a deck with no attack left) grows the exhaust pile past the observation's limit, and the run fails. |

Failures that cluster on certain states would teach the agent to seek or avoid them for the wrong reason (the floor 49 one ends its best runs), and each costs a game relaunch. A crash leaves no message: the game's error output is discarded.

## Goal

Every failure kind above that has its cause in the mod, the trainer or AutoSlay no longer happens, real run failures count against the failure budget again, and a game crash leaves its error output behind.

## Non-goals

- The game's own crashes (the Spine finalizer and the native crashes): they stay failed runs outside the failure budget (spec 014).
- Restarting games on a schedule: crashes do not grow with a game's age.
- A turn limit per fight: the existing step limit per run ends a fight that cannot end.
- The agent's choices themselves (card skipping, resting rather than upgrading, card removal): a later spec.

## Acceptance criteria

- [ ] A run that AutoSlay fails (its "Run failed with seed" line) ends as a failed run named by that line, not as "the game closed the connection", and counts against the failure budget. A test on a game log shows it.
- [ ] The game's error output and exit code are kept for every game process, next to its log, and a failed run caused by a game exit names the exit code.
- [ ] After the Battleworn Dummy event's fight, at every setting, the event carries on to its end and the run goes on. Checked in the game on a seed that reaches it, for each setting.
- [ ] The Crystal Sphere never reaches its choice limit: switching tools is offered only when the last choice was not a switch. Checked in the game, and no Crystal Sphere timeout in the training run.
- [ ] At a rest site with the Miniature Tent, choosing Smith as a later option goes on to the rest site's next choice, with no disposed button. Checked in the game.
- [ ] A run that reaches total floor 49 goes on to its act 3 boss. Checked in the game on a seed whose act 3 boss is on floor 50.
- [ ] A draw, discard or exhaust pile larger than the observation holds no longer fails the run: the observation keeps its most recent cards, and the pile's size stays exact. A test shows it.
- [ ] A training run from scratch with spec 014's result settings (four games, seed 2032, the 2,000,000-step schedule, stopped after 500,000 steps) has no failure of the kinds fixed above, and its failed runs are counted by kind in the result.

## Open questions

None.
