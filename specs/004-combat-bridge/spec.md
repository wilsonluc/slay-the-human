# 004: Combat bridge

Status: draft

## Problem

The agent has to see the game and choose its moves, but it is Python and the game is C# inside the game process. Nothing connects them yet.

AutoSlay, the stand-in player from spec 003, also plays dishonestly in combat: it gives itself 999 Plating and 999 Regen every combat and plays cards through a path that spends no energy. Its runs say nothing about how good a policy is.

## Goal

During an unattended run, every combat decision goes to a Python program: the mod sends it the combat state and the legal actions, and carries out the action it picks the way a player would. A Python client that picks at random plays full runs this way. Outside combat, AutoSlay still decides.

## Non-goals

- Decisions outside combat (map, events, rewards, shop, rest sites, card selection, relics). That is spec 005, along with the combats events start, which AutoSlay still ends by killing the enemies.
- Card choices made inside combat by card selection screens (such as "choose a card to discard"); they stay with AutoSlay's selector until spec 005.
- The training environment, observation encoding and action masks for PPO (spec 006).
- A smart agent. The client picks at random.
- Several games or agents at once.

## Acceptance criteria

- [ ] One command runs a full unattended run with the random Python client choosing every combat action, and prints the run summary from spec 003 plus the number of combat decisions and the decisions per second.
- [ ] At each combat decision, the client receives the state: the player's HP, max HP, block, energy and powers; each card in hand with its ID, cost, type, target type and whether it can be played; the sizes of the draw, discard and exhaust piles; the potions with their target types; each enemy's ID, HP, max HP, block, powers and intent with its damage; and the act, floor and turn.
- [ ] The legal actions are listed with the state: each playable card with each valid target, each usable potion with each valid target, and ending the turn. Nothing illegal is listed.
- [ ] A card the client plays costs its energy, and no power the player could not get in normal play is applied.
- [ ] An action not in the list, a client that disconnects, or a client that does not answer in time ends the run as an error naming the reason. No substitute action is ever taken.
- [ ] The client and the mod check they speak the same protocol version when they connect; a mismatch ends the run with an error naming both versions.
- [ ] The same game seed with the same client seed gives the same run: the same rooms, the same combat actions, the same outcome.
- [ ] The protocol is written down in one place, which both sides follow.
- [ ] Launching the game normally from Steam opens no connection and changes nothing.
- [ ] `README.md` says how to run it.

## Open questions

