# Agent protocol

How the mod and the Python agent talk during an unattended run. This file is the protocol's single definition: the mod (`mod/Bridge.cs` and the `mod/Agent*.cs` decisions) and the agent (`agent/bridge.py`) follow it, and `tools/test.sh` checks both use the version below.

Protocol version: **3**

Change the version whenever a message changes shape, in the same PR as both sides.

## Connection

- The agent listens on TCP `127.0.0.1` and prints the port. `tools/run.sh` passes it to the game as `--slay-the-human-agent-port=<port>`.
- The mod connects once, at the run's first decision, and keeps the connection until the run ends.
- Each message is one JSON object on one line, UTF-8, ending in `\n`.
- Only the mod asks and only the agent answers, one answer per question, in order.

## Messages

### hello (both ways)

Sent by each side right after connecting. If the versions differ, the side that notices closes the connection and fails with both versions in its error.

```json
{"type": "hello", "protocol": 3}
```

### decision (mod to agent)

Sent whenever the run needs a choice the agent makes. A choice with only one legal action is made without asking. `id` counts up from 1 within a run.

```json
{"type": "decision", "id": 7, "kind": "combat", "state": {"run": {...}, "combat": {...}}, "actions": [...]}
```

`kind` is one of `combat`, `map`, `reward`, `card_reward`, `rest`, `card_select`, `event`, `shop`, `treasure`, `bundle`, `crystal_sphere`. `state` always has `run`, plus one object named after the kind.

### action (agent to mod)

The answer to a decision, with the same `id`. For every kind but `card_select`, `index` picks one entry of `actions`. For `card_select`, `indices` picks cards from `state.card_select.cards`: distinct, at least `min` and at most `max` of them.

```json
{"type": "action", "id": 7, "index": 2}
{"type": "action", "id": 8, "indices": [0, 3]}
```

The mod ends the run as an error, and never chooses on its own, when:
- the answer is not a valid choice for that decision, or its `id` does not match;
- the agent does not answer within 30 seconds;
- the connection closes;
- the game refuses the choice.

### run_end (mod to agent)

Sent once when the run ends, after which the mod closes the connection.

```json
{"type": "run_end", "outcome": "win", "floor": 48}
```

`outcome` is `win` or `loss`. A connection that closes without `run_end` means the run failed; the mod's log says why.

## State

### run (every decision)

| Field | Type | Meaning |
|---|---|---|
| `character` | string | character ID, such as `IRONCLAD` |
| `hp`, `max_hp`, `gold` | int | |
| `ascension` | int | 0 to 10 |
| `act` | int | act number, from 1 |
| `floor` | int | rooms entered so far in the run |
| `deck` | array | every card in the deck: `{"id", "upgraded"}` |
| `relics` | array | `{"id", "counter"}`; `counter` is the number shown on the relic, or `null` |
| `potions` | array | one entry per potion slot: `{"id", "target"}`, or `null` when empty |

### combat

| Field | Type | Meaning |
|---|---|---|
| `turn` | int | the player's turn number in this combat, from 1 |
| `player` | object | `hp`, `max_hp`, `block`, `energy`, `max_energy`, `stars` (ints) and `powers` |
| `hand` | array | the cards in hand, in hand order (see below) |
| `draw`, `discard`, `exhaust` | int | pile sizes |
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

Actions:

| Action | Meaning |
|---|---|
| `{"kind": "play", "card": <hand index>, "target": <enemy index or null>}` | play a card; `target` is set only for cards that target one enemy |
| `{"kind": "potion", "slot": <slot index>, "target": <enemy index or null>}` | use a potion; `target` is set only for potions thrown at one enemy |
| `{"kind": "end_turn"}` | end the turn |

### map

The current act's map, as the player sees it.

| Field | Type | Meaning |
|---|---|---|
| `points` | array | every map point: `{"col", "row", "type"}`; `type` is the game's point type (`Monster`, `Elite`, `RestSite`, `Shop`, `Treasure`, `Unknown`, `Boss`, `Ancient`) |
| `edges` | array | paths as `[from, to]` pairs of indices into `points` |
| `current` | int or null | index of the point the player is on, or `null` before the first move |

Actions: `{"kind": "travel", "point": <index into points>}` for each point the game lets the player move to next, including moves a relic allows.

### reward

The rewards still on the rewards screen.

| Field | Type | Meaning |
|---|---|---|
| `rewards` | array | `{"type", "id", "amount", "group"}`: `type` is `gold`, `potion`, `relic`, `card`, `special_card`, `card_removal` or `other`; `id` is the potion, relic or card ID when there is one; `amount` is the gold; `group` numbers the members of a "choose one" set, else `null` |

Actions: `{"kind": "take", "reward": <index into rewards>}` for each reward that can be taken now (a potion only with a free slot), and `{"kind": "proceed"}` to leave the rest.

### card_reward

| Field | Type | Meaning |
|---|---|---|
| `cards` | array | the offered cards: `{"id", "upgraded", "type", "rarity"}` |
| `alternatives` | array | the screen's other options by ID, such as `Skip`, `REROLL`, `SACRIFICE` |

Actions: `{"kind": "pick", "card": <index into cards>}` and `{"kind": "alternative", "option": <ID>}`.

### rest

| Field | Type | Meaning |
|---|---|---|
| `options` | array | the rest site's options: `{"id", "enabled"}`; IDs such as `HEAL`, `SMITH`, `LIFT`, `DIG` |

Actions: `{"kind": "rest", "option": <index into options>}` for each enabled option, and `{"kind": "proceed"}` once the game allows leaving.

### card_select

The game asks the player to select cards.

| Field | Type | Meaning |
|---|---|---|
| `purpose` | string | why: `upgrade`, `transform`, `enchant`, `remove`, `discard`, `exhaust`, `hand_upgrade`, `hand`, `deck`, `choose`, `grid`, `reward_grid`, `combat_pile`, or `other` when the game asks some other way |
| `min`, `max` | int | how few and how many cards may be selected |
| `cards` | array | the cards offered: `{"id", "upgraded", "type", "rarity"}` |

`actions` is empty; the answer is `indices` into `cards`.

### event

| Field | Type | Meaning |
|---|---|---|
| `id` | string | event ID, such as `NEOW` |
| `page` | string or null | the localization key of the event's current text, which identifies the page it is on |
| `options` | array | every option on the page: `{"text_key", "locked", "proceed", "deadly", "relic"}`; `deadly` is true when the game marks the option as killing the player now; `relic` is the relic an option grants, when it names one |

Actions: `{"kind": "choose", "option": <index into options>}` for each option that is neither locked nor disabled.

### shop

The shop's inventory, or the FakeMerchant event's.

| Field | Type | Meaning |
|---|---|---|
| `items` | array | `{"type", "id", "cost", "on_sale", "stocked"}`: `type` is `card`, `relic`, `potion` or `card_removal`; `id` is the card, relic or potion ID; `stocked` is false once bought |

Actions: `{"kind": "buy", "item": <index into items>}` for each stocked item the player can afford (a potion only with a free slot), and `{"kind": "leave"}`. Card removal then asks a `card_select` with purpose `remove`.

### treasure

| Field | Type | Meaning |
|---|---|---|
| `relic` | string or null | the chest's relic, or `null` for an empty chest |

Actions: `{"kind": "take"}` when there is a relic, and `{"kind": "skip"}`.

### bundle

| Field | Type | Meaning |
|---|---|---|
| `bundles` | array | each bundle's cards, as arrays of `{"id", "upgraded", "type", "rarity"}` |

Actions: `{"kind": "pick", "bundle": <index into bundles>}`.

### crystal_sphere

| Field | Type | Meaning |
|---|---|---|
| `width`, `height` | int | the grid's size |
| `hidden` | array | the cells still hidden, as `[x, y]`; what lies under them is never sent |
| `divinations` | int | reveals left |
| `tool` | string | the current divination: `Big` (3 by 3) or `Small` (one cell) |

Actions: `{"kind": "reveal", "x": <x>, "y": <y>}` for each hidden cell, and `{"kind": "tool", "tool": <the other tool>}`.
