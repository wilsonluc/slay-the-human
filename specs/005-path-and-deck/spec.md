# 005: The path and the deck

Status: draft

## Problem

Since spec 004 the agent plays every combat, but AutoSlay still makes the choices that shape a run: which way to go on the map, which rewards to take, which card to add, what to do at a rest site, and which cards to upgrade, remove or transform. Many of these are not choices at all for AutoSlay. It always takes the first map path, takes rewards in screen order, never skips a card reward, and picks the most cards a selection allows. An agent that only fights can never learn to build a deck or plan a route.

AutoSlay also still cheats in combats that events start: it gives the player 100 Strength, Plating and Regen and kills every enemy without playing a card. And it picks the character at random, while training needs to choose it.

## Goal

The agent makes every map, reward, card reward, rest site and card selection choice, with the run's state and the legal options, as well as every combat decision, including combats that events start. The command chooses the character.

## Non-goals

- Events, shops, treasure rooms, and the relic, bundle and Crystal Sphere choice screens. AutoSlay still decides those; they are spec 006. That includes each run's opening ancient event, where AutoSlay still picks the starting blessing at random, and the relic choice after a boss.
- Discarding a potion, or using one outside combat.
- Ascension levels.
- A smart agent. The random client from spec 004 picks among the options.

## Acceptance criteria

- [ ] Every decision the agent gets carries the run's state: HP, max HP, gold, the deck (each card's ID and whether it is upgraded), relics, potions, act and floor.
- [ ] Map: at each choice of the next room, the agent gets the act's map as the player sees it (every node with its room type, the paths between them, the current position) and chooses among the rooms the game lets the player move to next, including moves a relic allows.
- [ ] Rewards: after a combat, the agent chooses which rewards to take, one at a time, and when to move on. A reward that cannot be taken (a potion with no free slot) is not listed.
- [ ] Card rewards: the agent chooses one of the offered cards or one of the other options on that screen, such as skipping.
- [ ] Rest sites: the agent chooses among the options the rest site offers.
- [ ] Card selection: every time the game asks the player to select cards (to upgrade, transform, remove, enchant, discard, choose, and the like), the agent gets the cards offered, why they are offered, and how few and how many it may pick, and picks any allowed number of them.
- [ ] Combats that events start are played by the agent like any other combat; no power the player could not get is applied and no enemy is killed except by play.
- [ ] The command takes the character to play; without it, the run uses Ironclad.
- [ ] Over a full run of the random agent, AutoSlay makes none of the choices listed above.
- [ ] The same game seed, agent seed and character give the same run.
- [ ] The protocol document covers the new decisions, and its version goes up.
- [ ] `README.md` covers the new option.

## Open questions

