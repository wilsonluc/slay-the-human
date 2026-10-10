# 006: Events, shops and relics

Status: done

## Problem

After spec 005, AutoSlay still makes every choice in events, shops and treasure rooms, and on the bundle and Crystal Sphere screens. Those choices matter: each run opens with an ancient event that grants its starting blessing, and shops are the main way to remove cards. AutoSlay picks events' options at random, buys at random until its gold runs out, never removes a card at a shop, and always takes a treasure's relic. It also fails outright on the FakeMerchant event, which ends the run.

AutoSlay also expects every run to end in a win. When the player dies, it waits out a timeout for a rewards screen that never comes and fails the run (#11), which wastes time on every losing run and hides real failures.

## Goal

The agent makes every choice in a run. Every decision that AutoSlay still makes after spec 005 goes to the agent, with the run state and the legal options, and a lost run ends promptly and cleanly.

## Non-goals

- Ascension levels (a later spec, before roadmap phase 1.1).
- Discarding a potion, or using one outside combat.
- A smart agent. The random client picks among the options.
- The relic choice screen. Nothing in this game build opens it (boss relics come through the rewards screen, which the agent handles since spec 005). If a game update starts using it, the check that AutoSlay makes no choice catches it.

## Acceptance criteria

- [x] Events: at every event choice, including each run's opening ancient event and events with their own screens such as FakeMerchant, the agent gets the event and its options (which are locked, and which the game marks as deadly) and chooses among the available ones.
- [x] Shops: the agent sees what the shop offers with prices (cards, relics, potions, card removal), buys any item it can afford one at a time, and chooses when to leave.
- [x] Treasure rooms: the agent chooses what to take from the chest among what the game allows, and when to leave.
- [x] Bundle choice screens: the agent chooses one of the offered bundles.
- [x] Crystal Sphere: the agent chooses which cells to reveal.
- [x] Over a full run of the random agent, AutoSlay makes no choice at all; every room and screen of the run is handled by the agent's decisions.
- [x] A lost run ends within seconds of the player's death, with no AutoSlay error, and the command reports the loss.
- [x] The same game seed, agent seed and character give the same run.
- [x] The protocol document covers the new decisions, and its version goes up.
- [x] `ROADMAP.md` marks phase 0's "every decision" need as done.

## Open questions

