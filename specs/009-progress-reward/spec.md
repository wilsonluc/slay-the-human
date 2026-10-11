# 009: Progress reward

Status: draft

## Problem

The first million-step training run (spec 008) learned the basics quickly, then stalled. Over its first 340,000 steps:

| | First 500 runs | Last 500 runs |
|---|---|---|
| Mean floor | 7.9 | 8.7 |
| Turns per combat | 7.8 | 19.2 |
| Card plays per floor | 9.2 | 16.1 |
| Runs past the act 1 boss | 0 | 0 |

The policy learned to drag fights out, not to go further. The reward (spec 007) causes it. Every shaping term is potential-based and its score falls to zero when a run ends, so over a run that ends in a loss the shaping adds up to almost the same total wherever the run ended: a loss on floor 5 and a loss on floor 17 score nearly the same. While the agent never wins, which is all of the early training, the one thing that differs between runs is the -1 for the loss, and the discount makes a loss that comes later, in steps, cost a little less. So taking more steps before dying is what pays, and progress pays nothing.

The shaping was made potential-based so that no term could be farmed and so that it could never change which policy is best. In a phase where every run is lost, "best" means "lose as late as possible", which is the wrong lesson.

## Goal

A reward under which, while the agent cannot yet win, going further pays and dragging a fight out does not; a win stays the best outcome; no term can be farmed; and each property is pinned by a test on worked example runs.

## Non-goals

- Learning rate, discount, or any other PPO setting. One change at a time, so the next training run shows what the reward alone does.
- Evaluation, generations and the dashboard (now specs 010 and 011).
- A per-step or per-turn penalty: a cost for time would also push the agent to end fights rashly, and the reward below removes the incentive to stall without one.

## Acceptance criteria

The reward:

- [ ] Progress is rewarded when it happens and is never taken back: a reward for each floor reached for the first time in the run, and for each elite and each boss killed. These are not potential-based, so their total over a run grows with how far it got.
- [ ] A loss costs nothing of its own. Dying is bad because it ends the progress that would have followed, so nothing is gained by putting it off.
- [ ] A win adds a reward of its own on top of the progress it took to get there.
- [ ] HP and combat progress stay as potential-based shaping, as in spec 007, to help credit actions within a fight. Their total over a terminated run stays the negative of their starting scores, so they reward nothing by themselves.
- [ ] Each term's weight is set in one place and documented, with the reasons; one full run's worth of progress is on the same scale as a win.
- [ ] The reward's hash changes, so no checkpoint trained on the old reward loads against it.

Tests on worked example runs (no game), discounted with the training discount:

- [ ] A loss on floor 17 returns more than a loss on floor 5, and more than a loss on floor 5 that took three times as many steps.
- [ ] Reaching the same floors in more steps returns less than reaching them in fewer: stalling never pays.
- [ ] A win returns more than any loss.
- [ ] Repeating a state (a floor already reached, a reward screen reopened, an enemy that heals) adds no reward.
- [ ] The HP and combat shaping still add up to minus their starting scores over a terminated run.

Training:

- [ ] A training run with the new reward, otherwise configured like the first (4 games, the same settings), reaches 300,000 steps. Over its last 500 runs at that point, its mean floor is at least 10, against 8.7 for the first run at the same step count, and its steps per floor reached are at most 13, against 18.8.
- [ ] `metrics.csv` reports turns per combat, so stalling shows up without reading traces.

## Open questions

None.
