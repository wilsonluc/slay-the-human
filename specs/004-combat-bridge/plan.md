# 004: Plan

## Approach

**Who connects to whom.** The Python agent listens; the game connects. That way the Python side owns the loop, which suits the training environment in spec 006. `tools/run.sh` starts the agent first, reads the port it chose, and passes it to the game as `--slay-the-human-agent-port=<port>`. The mod connects at the run's first combat. The bridge is on only when that argument is present, so a normal launch opens nothing.

**Transport and protocol.** TCP on `127.0.0.1`, one JSON object per line (UTF-8). `docs/protocol.md` defines every message; the protocol version is a constant in the mod and in the agent, and `tools/test.sh` checks both match the doc.

1. On connect, each side sends `{"type": "hello", "protocol": <n>}` and checks the other's. A mismatch ends the run with an error naming both.
2. At each combat decision the mod sends `{"type": "decision", "id": <n>, "state": {...}, "actions": [...]}` and the agent answers `{"type": "action", "id": <n>, "index": <i>}`, an index into `actions`.
3. When the run ends the mod sends `{"type": "run_end", "outcome": "win"|"loss", "floor": <n>}` and closes.

**State** (all read from game models, nothing from the UI):
- player: `hp`, `max_hp`, `block`, `energy`, `max_energy`, `stars`, `powers` (`[{id, amount}]`);
- `hand`: per card `id` (`Id.Entry`), `upgraded`, `cost` (`EnergyCost.GetWithModifiers(All)`; `costs_x`), `star_cost`, `type`, `target`, `playable` (`CanPlay`);
- `draw`, `discard`, `exhaust`: pile sizes;
- `potions`: per slot `id` and `target`, or null for an empty slot;
- `enemies`: every creature in `CombatState.Enemies` (so indices stay stable when one dies), each with `id`, `alive`, `hp`, `max_hp`, `block`, `powers`, and `intents` (`[{type, damage, hits}]`, damage from `AttackIntent.GetSingleDamage`; nothing read through a hidden intent);
- `act`, `floor`, `turn` (`PlayerCombatState.TurnNumber`).

**Legal actions**, built from the same snapshot:
- `{"kind": "play", "card": <hand index>, "target": <enemy index or null>}` for each card and target where `CardModel.CanPlayTargeting(target)` holds: alive enemies for `AnyEnemy`, `null` for every other target type (no ally targets in singleplayer);
- `{"kind": "potion", "slot": <i>, "target": ...}` for each potion that passes the same gate as the game's potion popup (not queued, owner alive, not `Automatic`, `CanRemovePotions`, `PassesCustomUsabilityCheck`, and for combat-only potions the player's side with actions enabled) and each target where `PotionModel.IsValidTarget` holds;
- `{"kind": "end_turn"}`.

**Playing the turn.** A Harmony prefix on AutoSlay's `CombatRoomHandler.HandleAsync` runs our loop and skips the original, so its 999 Plating and Regen and its free `CardCmd.AutoPlay` never happen. The loop:
1. waits, once per frame, until the player can act: combat in progress and not ending, player side, `Phase == Play`, actions enabled, not ready to end the turn, the action synchronizer in its play phase, and the action queue empty with nothing running;
2. sends the decision and waits for the answer;
3. carries it out the way the game's own UI does: `card.TryManualPlay(target)`, `potion.EnqueueManualUse(target)`, or enqueueing `EndPlayerTurnAction(player, turnNumber)` through `ActionQueueSynchronizer.RequestEnqueue`;
4. repeats until combat is over, then waits for it to finish as AutoSlay did.

AutoSlay's other handlers, its card selector, room loop and watchdog are unchanged.

**Errors.** An index outside `actions`, a closed connection, no answer within 30 seconds, or a refused action (`TryManualPlay` returning false) throws from the loop with the reason. AutoSlay then fails the run and quits the game; `tools/run.sh` already reports AutoSlay's failure line. The mod never picks an action itself.

**The agent** (`agent/`, Python 3.13, standard library only):
- `agent/bridge.py`: listens, accepts one connection, does the handshake, yields decisions, sends actions, and returns the run end. It raises on a protocol mismatch, a bad message, or a connection closed before `run_end`.
- `agent/random_agent.py`: picks a uniformly random index with `random.Random(seed)`; `--seed` defaults to a random one. It prints `port=<n>` when listening, and at the end `agent_seed=<n> decisions=<n> per_second=<x>`. With `--trace`, it writes every decision and its choice as JSON lines; `tools/run.sh` keeps that trace in `runs/`.

**The command.** `sh tools/run.sh [--seed=<seed>] [--agent-seed=<n>] [--time-scale=<n>]` starts the agent, launches the game with the agent's port, and appends the agent's final line to the summary. If the agent exits with an error, the command stops the game and exits 1 with the agent's message.

## Changes

- `docs/protocol.md`: the protocol.
- `mod/Bridge.cs`: connection, handshake, decision exchange, timeouts.
- `mod/CombatSnapshot.cs`: state and legal actions.
- `mod/AgentCombat.cs`: the `CombatRoomHandler.HandleAsync` prefix and turn loop.
- `mod/RunMode.cs`: the agent port argument.
- `mod/RunLog.cs`: sends `run_end` to the agent.
- `agent/bridge.py`, `agent/random_agent.py`, `agent/test_bridge.py`: the agent and its tests (`python -m unittest discover agent`).
- `tools/run.sh`: starts the agent and passes its port; the agent seed; the extended summary.
- `tools/test.sh`: the protocol version in the mod, the agent and the doc agree.
- `README.md`: running it, and the agent tests.

## Verification

- Full run with the random agent → `sh tools/run.sh`: exit 0, summary with decisions and decisions per second.
- State contents → the agent's tests check a recorded decision message has every field; one real decision message from a run is checked by hand against the spec's list.
- Only legal actions → over a full run, every action the random agent picks is carried out without a refusal (any refusal fails the run).
- Energy is spent, no buffs → in a run's log, no Plating or Regen applied by AutoSlay, and the energy in the state after a played card is lower by its cost.
- Errors → agent tests with a fake mod: a disconnect, a bad message and no connection each end with the reason. In the game, the mod's checks: agents changed to answer an index out of range, or to answer after 35 seconds, each end the run with that reason, and the command exits 1.
- Version mismatch → agent test with a fake mod sending another version; and one real run with the agent's version changed.
- Same seeds, same run → two runs with `--seed=TEST1 --agent-seed=1`: identical `room` lines, outcome, floor, and the same sequence of action indices.
- One protocol definition → `docs/protocol.md`; `tools/test.sh` checks the version.
- Normal launch → the log shows no bridge connection.
- Docs → `README.md`.

## Risks

- Polling once per frame bounds decisions per second by the frame rate → measure; if too slow, wait on the game's events (`ActionQueueSet.BecameEmpty`, `TurnStarted`) instead.
- AutoSlay's 5-minute combat limit and 30-second watchdog → fine for a random agent; a slow agent later needs our own limits.
- A card selection screen inside combat consumes AutoSlay's shared random source → still deterministic for the same seeds, since the same choices consume it the same way.
- Actions enqueued just before the synchronizer reaches its play phase are deferred, not lost → the "can act" check waits for the play phase.
