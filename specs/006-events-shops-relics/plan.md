# 006: Plan

## Approach

As in spec 005: each AutoSlay handler that still chooses is replaced by a Harmony prefix running our own loop, which builds a `Decision`, asks the agent and clicks the same nodes AutoSlay clicks. All apply only in run mode with an agent.

| Kind | Replaces | State | Actions |
|---|---|---|---|
| `event` | `EventRoomHandler.HandleAsync` | the event's ID, its current page (`EventModel.Description` key), and each option: text key, locked, proceed, deadly (`WillKillPlayer`), relic | `choose` an unlocked option |
| `shop` | `ShopRoomHandler.HandleAsync`, and the FakeMerchant event's shop | each item: type (`card`, `relic`, `potion`, `card_removal`), ID, cost, on sale, stocked | `buy` a stocked item the player can afford (a potion only with a free slot); `leave` |
| `treasure` | `TreasureRoomHandler.HandleAsync` | the chest's relic, or none | `take`; `skip` |
| `bundle` | `ChooseABundleScreenHandler.HandleAsync` | each bundle's cards | `pick` a bundle |
| `crystal_sphere` | `CrystalSphereScreenHandler.HandleAsync` | the grid's cells (hidden or not, never what is under a hidden cell), divinations left, the current tool | `reveal` a hidden cell; `tool` to switch between the big and small divination |

**Events.** Our loop keeps AutoSlay's structure: wait for the event room; click through ancient dialogue (no choice) until options appear; ask; click the chosen option; then wait for the next state (new options, an overlay, the map, combat, or the room closing). Combats an event starts go to the agent's combat loop, as in spec 005. An overlay (a rewards screen, the Crystal Sphere, a bundle screen) hands back to AutoSlay's screen loop, which dispatches to our handlers, as AutoSlay's own event handler does.

**FakeMerchant.** Its custom node is a shop of fake relics. It goes through the same shop decision with its own inventory. Leaving clicks its proceed button directly, since the game disables that button whenever its screen is not the active one, which is why AutoSlay's wait for it times out.

**Shops.** Buying calls the entry's `OnTryPurchaseWrapper`, as the slot's own click does; card removal uses its cancelable overload, as the game's removal slot does, and its card choice reaches the agent through the card selector with purpose `remove`. A relic whose pickup opens a rewards screen is answered in place by the rewards decision.

**Losing a run.** A prefix on AutoSlay's `WaitForRewardsScreenAsync` also returns when `RunManager.IsGameOver`. It then runs AutoSlay's game over handler (no choice: continue, main menu), waits for the main menu and throws a `RunLost` signal, which a postfix on `PlayRunAsync` catches, so AutoSlay ends the run as it ends a win: `RunCompleted`, exit code 0. A death outside combat (a deadly event option) is caught the same way at the next map decision.

**Found while building** (each fixed, each with a replayed run):
- **Questions overlapping.** The game can ask for a card selection while another question is waiting (Lord's Parasol removes a card on entering a shop while the shop decision is out). The bridge now gives questions turns, so one is in flight at a time, as the protocol says.
- **Relics that shop first.** Lord's Parasol buys everything on entering a shop, with the shop's input blocked. The shop decision waits until the shop accepts input and travel is back on, as a player would.
- **Tutorial popups.** The ascension tutorial opens at character select once ascension is unlocked and stays open, unseen, all run. It blocks every later modal (so TRIAL's "double down" could not ask to confirm giving up) and takes the active screen (likely why the FakeMerchant's proceed button stayed disabled for AutoSlay). In run mode tutorials no longer open.
- **Giving up.** An event option that abandons the run opens the game's confirmation; choosing the option was the agent's decision, so it is confirmed and the run ends as a loss.
- **Card selection purposes from small methods.** The JIT inlines the small `CardSelectCmd` entry stubs, which skips patches on them; the purpose is now recorded on each entry point's async state machine, and read from the selection's prompt (`card_selection.TO_REMOVE` and the like) when it has one.
- **Replaying a failed run.** The random agent prints its seed first, so a run that fails can be replayed.

**Protocol version 3** adds the five kinds to `docs/protocol.md`; the agent needs no change beyond the version, since it already answers any kind by index.

**Roadmap.** Phase 0's "every decision outside combat" need is marked done, and the results dashboard (React and MUI X on GitHub Pages, comparing generations) is added as a need after PPO and evaluation.

## Changes

- `docs/protocol.md`, `mod/Bridge.cs`, `agent/bridge.py`, `agent/test_bridge.py`: version 3 and the new kinds.
- `mod/AgentEvent.cs`, `mod/AgentShop.cs`, `mod/AgentTreasure.cs`, `mod/AgentBundle.cs`, `mod/AgentCrystalSphere.cs`, `mod/RunLost.cs`: the new handlers and the loss path.
- `mod/AgentRewards.cs`, `mod/AgentMap.cs`: the rewards decision callable from the shop; the map's game-over check.
- `ROADMAP.md`, `README.md`.

## Verification

- Events → `event` decisions in traces, including a run's opening ancient event; an event that offers a locked option lists it as locked and not as an action.
- FakeMerchant → a seed that reaches it (found by running seeds; noted if none does) ends the event without an AutoSlay error.
- Shops → `shop` decisions with items and costs; a purchase lowers gold by the cost in the next decision; a card removal leads to a `card_select` with purpose `remove` and one fewer card in the deck.
- Treasure → `treasure` decisions; `take` adds the relic; `skip` does not.
- Bundle and Crystal Sphere → seen in traces when a run reaches them (bundles come from the Scroll Boxes relic, the Crystal Sphere from its event; noted if not reached).
- AutoSlay makes no choice → across full runs, the log has none of AutoSlay's choosing action lines (event option, buying, chest relic, bundle, cell).
- Lost run → a losing run's log has no AutoSlay `Run failed`, AutoSlay quits with exit code 0, and the time from `run end` to exit is a few seconds.
- Same seeds → two runs, identical traces.
- Protocol → version 3 in the doc, the mod and the agent (`tools/test.sh`).
- Roadmap → `ROADMAP.md` updated.

## Risks

- Event flows vary (dialogue, combat layouts, custom screens) → the loop fails loudly on any state it does not recognise, and full runs exercise many events; any event that fails is fixed or recorded.
- A purchase can open a screen in the middle of a shop → handled for rewards screens; any other screen fails loudly.
- Normal combats played by the random agent end runs early, so later rooms are rare → coverage runs leave normal combats to AutoSlay temporarily, as in spec 005, and are undone afterwards.
