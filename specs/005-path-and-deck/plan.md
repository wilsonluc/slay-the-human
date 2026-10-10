# 005: Plan

## Approach

Each AutoSlay handler that holds one of this spec's choices is replaced by a Harmony prefix that runs our own version and skips the original, as spec 004 did for combat. All prefixes apply only in run mode with an agent. AutoSlay's room loop, screen dispatch and the handlers this spec leaves alone keep running.

**One decision shape.** A `Decision` holds a kind, a kind-specific state, the legal actions and how to carry out each. It adds the run state, asks the agent through the bridge, and carries out the answer. When only one action is legal it carries it out without asking, so the agent only sees real choices (this also applies to combat, where a turn with only "end turn" left is no longer sent).

**Run state**, in every decision as `state.run`: character, HP, max HP, gold, ascension, act, floor, the deck (`Player.Deck.Cards`: ID, upgraded), relics (`Player.Relics`: ID, counter when shown), potions (`Player.PotionSlots`).

**The choices:**

| Kind | Replaces | Options | Carried out by |
|---|---|---|---|
| `combat` | `CombatRoomHandler.HandleAsync` and `EventRoomHandler.HandleEventCombat` | as in spec 004 | as in spec 004 |
| `map` | `MapScreenHandler.HandleAsync` | the map points the game's own map screen marks travelable (`NMapPoint.State == Travelable`, enabled), so free travel from relics counts | clicking that map point, then waiting for `RunManager.RoomEntered` |
| `reward` | `RewardsScreenHandler.HandleAsync` | each enabled reward button (gold, potion, relic, card reward, special card, card removal, and the members of a "choose one" set), except a potion with no free slot; and proceeding | clicking the button, then waiting until it is claimed, re-enabled, or another screen opens (then returning to AutoSlay's screen loop, as the original does); proceeding clicks the proceed button |
| `card_reward` | `NCardRewardSelectionScreen.OptionSelected()`, and `CardRewardScreenHandler.HandleAsync` becomes a wait until the screen closes | the offered cards and the screen's other options (`Skip`, `REROLL`, `SACRIFICE`, ...) | returning the chosen index to the game, which adds the card or runs the option |
| `rest` | `RestSiteRoomHandler.HandleAsync` | the enabled rest site options; and proceeding once the game allows it | clicking the option's button; proceeding clicks the proceed button and waits for the map (the button stays enabled, so AutoSlay's own check clicks it once more, harmlessly) |
| `card_select` | `AutoSlayCardSelector.GetSelectedCards` | the cards offered, `min`, `max`, and a `purpose` | returning the chosen cards to the game |

The rewards, rest site and map choices are carried out by clicking the same screen nodes AutoSlay clicks, so the screens stay consistent; the agent's index maps back to a node through the list built for that decision.

**Card selection purpose.** The game does not pass the purpose to the selector, so a prefix on each `CardSelectCmd` entry point records it in an `AsyncLocal`, which the selector reads. Values: `choose` (`FromChooseACardScreen`), `reward_grid` (`FromSimpleGridForRewards`), `grid` (`FromSimpleGrid`), `combat_pile` (`FromCombatPile`), `upgrade` (`FromDeckForUpgrade`), `transform` (`FromDeckForTransformation`), `enchant` (`FromDeckForEnchantment`), `remove` (`FromDeckForRemoval`), `deck` (`FromDeckGeneric`), `hand` (`FromHand`), `discard` (`FromHandForDiscard`), `hand_upgrade` (`FromHandForUpgrade`). `FromDeckForRemoval` and `FromHandForDiscard` call `FromDeckGeneric` and `FromHand`; they hand their purpose to the inner call, which keeps it. A selection that came through none of them is `other`. The answer to a `card_select` is a list of distinct indices whose length is within `min` and `max`.

**Character.** `--slay-the-human-character=<ID>` (default `IRONCLAD`). A prefix on `NCharacterSelectButton.Select()` selects that character's button instead of the one AutoSlay drew. A character the game does not have ends the run as an error before AutoSlay starts (logged as `[SlayTheHuman] run error`, which `tools/run.sh` reports first); a locked one ends it when selected.

**Protocol version 2.** `decision` gains `kind`; `state` becomes `{"run": ..., <kind>: ...}`; `action` answers with `index`, or `indices` for `card_select`. `docs/protocol.md` defines every kind; both sides move to version 2.

**Agent.** `bridge.py` passes the whole decision to `choose`, which returns an index or a list of indices. The random agent picks uniformly among the actions, or for `card_select` a uniform count within `min`..`max` and then that many distinct cards.

**Command.** `tools/run.sh --character=<id>` passes the character; the summary adds it.

## Changes

- `docs/protocol.md`: version 2.
- `mod/Decision.cs`: the decision shape and the run state (replacing the action list in `CombatSnapshot`).
- `mod/CombatSnapshot.cs`, `mod/AgentCombat.cs`: build a `combat` decision; also replace `EventRoomHandler.HandleEventCombat`.
- `mod/AgentMap.cs`, `mod/AgentRewards.cs`, `mod/AgentCardReward.cs`, `mod/AgentRestSite.cs`, `mod/AgentCardSelect.cs`, `mod/ChooseCharacter.cs`: the new choices.
- `mod/Bridge.cs`: version 2, `kind`, and `indices` answers.
- `agent/bridge.py`, `agent/random_agent.py`, `agent/test_bridge.py`: version 2, `indices`, tests.
- `tools/run.sh`: `--character`.
- `README.md`: the option and the new decisions.

## Verification

- Run state in every decision → over a full run's trace, every decision has `state.run` with every field.
- Map → the trace's `map` decisions list the act's points with types, edges and position, and the chosen point is the next `room` line's floor; one run with free travel is checked if a seed offers Winged Boots (otherwise noted).
- Rewards → a run's `reward` decisions list each reward on the screen; a potion is listed only with a free slot; proceeding before taking everything leaves the rest.
- Card rewards → `card_reward` decisions list the cards and `Skip`; picking a card adds it to the next decision's deck; `Skip` adds nothing.
- Rest sites → `rest` decisions list the enabled options; choosing Smith leads to a `card_select` with purpose `upgrade`.
- Card selection → `card_select` decisions with their purposes; an answer of fewer than `max` cards is accepted when `min` allows.
- Event combats → the log shows no Strength, Plating or Regen from AutoSlay and no AutoSlay kill; the trace has `combat` decisions inside an event.
- Character → `--character=SILENT` gives a Silent run; the default is Ironclad; a bad ID fails.
- AutoSlay makes none of these choices → the run log has none of AutoSlay's map, reward, card reward, rest site or card selector action lines.
- Same seeds and character, same run → two runs, identical traces.
- Protocol → `docs/protocol.md` version 2, checked by `tools/test.sh`; agent tests for `indices`.
- Docs → `README.md`.

## Risks

- AutoSlay wraps each handler in a 30-second timeout and its waits in a 30-second watchdog → fine for a fast agent; a slow agent later needs these raised.
- Clicking screen nodes depends on node paths and types that a game update can move → each replaced handler fails loudly when a node is missing, and each gets its own check in the real game.
- The card reward screen keeps cards unclickable for its first 350 ms → we return the index through `OptionSelected`, not clicks.
- `AsyncLocal` purpose could leak into a later selection that skips the entry points → every entry point sets it, and the selector clears it after reading.
