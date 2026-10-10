# Agent protocol

How the mod and the Python agent talk during an unattended run. This file is the protocol's single definition: the mod (`mod/Bridge.cs`, `mod/CombatSnapshot.cs`) and the agent (`agent/bridge.py`) follow it, and `tools/test.sh` checks both use the version below.

Protocol version: **1**

Change the version whenever a message changes shape, in the same PR as both sides.

## Connection

- The agent listens on TCP `127.0.0.1` and prints the port. `tools/run.sh` passes it to the game as `--slay-the-human-agent-port=<port>`.
- The mod connects once, at the run's first combat, and keeps the connection until the run ends.
- Each message is one JSON object on one line, UTF-8, ending in `\n`.
- Only the mod asks and only the agent answers, one answer per question, in order.

## Messages

### hello (both ways)

Sent by each side right after connecting. If the versions differ, the side that notices closes the connection and fails with both versions in its error.

```json
{"type": "hello", "protocol": 1}
```

### decision (mod to agent)

Sent whenever the player can act in combat. `id` counts up from 1 within a run.

```json
{"type": "decision", "id": 7, "state": {...}, "actions": [...]}
```

`state`:

| Field | Type | Meaning |
|---|---|---|
| `act` | int | act number, from 1 |
| `floor` | int | rooms entered so far in the run |
| `turn` | int | the player's turn number in this combat, from 1 |
| `player` | object | `hp`, `max_hp`, `block`, `energy`, `max_energy`, `stars` (ints) and `powers` |
| `hand` | array | the cards in hand, in hand order (see below) |
| `draw`, `discard`, `exhaust` | int | pile sizes |
| `potions` | array | one entry per potion slot: `{"id", "target"}`, or `null` when empty |
| `enemies` | array | every enemy in the combat, dead ones included, so indices stay stable (see below) |

A power is `{"id": <string>, "amount": <int>}`.

A hand card:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | card ID, such as `STRIKE_IRONCLAD` |
| `upgraded` | bool | |
| `cost` | int | energy cost with all modifiers; negative when the card has no energy cost |
| `costs_x` | bool | an X-cost card, which spends all energy |
| `star_cost` | int | star cost with modifiers; negative when none |
| `type` | string | `Attack`, `Skill`, `Power`, `Status`, `Curse` or `Quest` |
| `target` | string | the game's target type, such as `AnyEnemy`, `Self`, `AllEnemies`, `None` |
| `playable` | bool | the game would let the card be played now |

An enemy:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | monster ID |
| `alive` | bool | |
| `hp`, `max_hp`, `block` | int | |
| `powers` | array | powers |
| `intents` | array | `{"type", "damage", "hits"}`; `type` is the game's intent type (`Attack`, `Defend`, `Buff`, ...). `damage` is per hit as the player would see it, and `hits` the number of hits, both only for attack intents (otherwise `null`). A hidden intent is `{"type": "Hidden", "damage": null, "hits": null}`. |

`actions`, every legal action at this moment and nothing else:

| Action | Meaning |
|---|---|
| `{"kind": "play", "card": <hand index>, "target": <enemy index or null>}` | play a card; `target` is set only for cards that target one enemy |
| `{"kind": "potion", "slot": <slot index>, "target": <enemy index or null>}` | use a potion; `target` is set only for potions thrown at one enemy |
| `{"kind": "end_turn"}` | end the turn; always present |

### action (agent to mod)

The answer to a decision, with the same `id`. `index` picks one entry of that decision's `actions`.

```json
{"type": "action", "id": 7, "index": 2}
```

The mod ends the run as an error, and never acts on its own, when:
- `index` is not a valid index into `actions`, or `id` does not match;
- the agent does not answer within 30 seconds;
- the connection closes;
- the game refuses the action.

### run_end (mod to agent)

Sent once when the run ends, after which the mod closes the connection.

```json
{"type": "run_end", "outcome": "win", "floor": 48}
```

`outcome` is `win` or `loss`. A connection that closes without `run_end` means the run failed; the mod's log says why.
