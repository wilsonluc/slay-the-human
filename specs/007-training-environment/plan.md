# 007: Plan

## Approach

The mod plays runs back to back in one game process, each started by the agent (protocol 4), and sends everything a player can look up. A Python environment turns each decision into a fixed-shape observation, a mask and a reward, and a launcher runs several copies of the game at once.

### Protocol 4

One connection per game process. The mod connects when the main menu first appears and keeps the connection until the game quits.

| Message | Direction | Content |
|---|---|---|
| `hello` | mod → agent | `protocol: 4`; `game_version` and `game_commit` from the game's `release_info.json`; `vocabulary`, every key the mod reads from the game (see Vocabulary) |
| `hello` | agent → mod | `protocol: 4` |
| `ready` | mod → agent | the game is at the main menu, waiting for a run |
| `start` | agent → mod | `seed` (letters and digits), `character` |
| `decision`, `action` | as in protocol 3 | ids count from 1 in each run; no time limit on the answer |
| `run_end` | mod → agent | `outcome`, `floor`, `seed` as the game canonicalised it; the connection stays open and the next message is `ready` |

The agent closing the connection at `ready` quits the game with exit code 0. A run that fails inside the game (an error in the mod or in AutoSlay) quits it with exit code 1, and the agent sees the connection close.

State changes:
- `state` holds `run`, `map`, the kind's object, and `combat` whenever a combat is in progress, whatever the kind (for `combat` decisions it is the kind's own object).
- `run` adds `boss` and `second_boss` (the act's boss encounter IDs, `null` when none), and `combats_won`, `elites_killed` and `bosses_killed`, counted by a postfix on the game's progress update after a combat won.
- `map` is protocol 3's map object, now on every decision. The `map` kind's own object is empty, and `travel` actions index `state.map.points`.
- `combat` adds `encounter`. `draw`, `discard` and `exhaust` become arrays of cards, sorted by ID and upgrade, so the draw pile's order (hidden from a player) never reaches the agent. Each enemy adds `combat_id` (the game's creature combat ID), so the reward can follow enemies added or removed mid-fight.
- One card object wherever a card appears: deck, hand, piles, card rewards, special card rewards, selections, bundles and shop cards.

| Card field | Meaning |
|---|---|
| `id`, `type`, `rarity` | as in protocol 3 |
| `upgrade` | upgrade level, replacing `upgraded` (some cards upgrade more than once) |
| `vars` | each dynamic variable's current base value by name, so a card that grew is seen grown |
| `keywords` | the card's keywords, from every source |
| `enchantment`, `affliction` | `{"id", "amount"}` or `null` |
| `cost`, `costs_x`, `star_cost`, `target`, `playable` | hand only, as in protocol 3 |
| `preview` | hand only: each variable after modifiers, as the card in hand shows it (the game's own preview with no target) |

`docs/protocol.md` is rewritten to match; `tools/test.sh` keeps checking that the doc, the mod and the agent use the same version.

### Mod: runs back to back

`mod/RunLoop.cs` replaces `StartAutoSlay.cs`. On the first main menu it connects to the agent, then loops: wait for the main menu with AutoSlay idle, send `ready`, read `start`, check the seed and character (a bad one is a run error), reset per-run state, start a new AutoSlay run with the seed, and wait until AutoSlay is idle again.

A prefix on AutoSlay's `QuitGame` skips the quit when the exit code is 0. Won and lost runs already end at the main menu, so they leave the game running; a failed run still quits.

Per-run state, reset at `start`: the seed and character (`RunMode.Seed` and `RunMode.Character` become settable; the `--slay-the-human-seed` and `--slay-the-human-character` arguments go), `RunLog`'s once-only end flag, the bridge's decision ids, a card selection purpose left from an earlier selection, and the combat counters. `RunLog` attaches its room handler once per process.

**Unlocks and the profile.** So that a seed's content depends neither on the profile nor on earlier runs:
- **Lobby.** A prefix on `StartRunLobby.AddLocalHostPlayer` passes `UnlockState.all`, as Daily mode does; the lobby picks the run's acts from it.
- **Player.** A singleplayer run builds its player from `SaveManager.GenerateUnlockStateFromProgress()`, not from the lobby. A prefix on that method returns `UnlockState.all` in run mode. The run's unlocks are the union of its players', so they are all as well.
- **Profile in memory.** The game also reads the progress save directly during a run (undiscovered acts forced, the first run's first unknown room made an event, a few events reading wins, ancient visits or Wongo points, one relic reading the profile's ID) and updates it in memory after each combat. At each `start`, the mod sets the game's in-memory progress to one fixed profile: the default progress with every act discovered and one recorded loss, so no first-run content.
- **No writes.** A prefix on `ProgressSaveManager.SaveProgress` returns false; every caller goes through it, including the save after each combat won. Run saves and run history are already off (`shouldSave` is false).
- **Check.** In each run's first room, the mod checks that the player holds `UnlockState.all` and the lobby prefix ran, and logs `unlocks=all`; otherwise it is a run error. This catches a patch the JIT inlined away.

### Mod: no time limits, no fixed waits

The game waits for the agent as long as it takes; hangs are caught in Python. In run mode no in-game time limit ends a run:
- The bridge has no answer timeout.
- `Wait.Until` keeps waiting past its timeout and logs `still waiting <n> s for <what>` once, so a hang's game log names what it waited for.
- AutoSlay's timeouts are `static readonly`, so they are patched where used. `mod/RunTiming.cs` has one transpiler on AutoSlay's async state machines: in `WaitHelper.WithTimeout` the deadline delay becomes infinite (room and screen handler timeouts, the 25-minute run timeout); in `WaitHelper.Until` and `ForTask` the timeout's token source never cancels.
- AutoSlay's watchdog, which fails a run after 30 seconds without progress, is turned off by a prefix on its check.
- The same transpiler replaces every other delay in AutoSlay's code with one frame: after rooms, the overlay drain, polling, `UiHelper.Click`, ancient dialogue clicks. Patching state machines rather than methods avoids inlined async stubs. It logs how many methods and calls it changed, and stops the mod at startup if it changed none.
- Every `Wait.For` in the mod (a wait that may legitimately time out) becomes a `Wait.Until` on every outcome it can have: a reward claim waits for the reward button's claimed or skipped signal; after an event option, the wait for the event's response also watches for the give-up confirmation; a closed event room waits for a combat, a screen or the map; an event resumed after combat waits for options, the map, a screen or the room closing. `Wait.For` is deleted.

**Frame cap.** Headless, the game caps frames at the settings' limit (60). Removing the cap in run mode was measured and dropped: with 4 games, 7 of 62 runs failed against none of 120 with the cap, and one game's memory grew past 5 GB.

### Vocabulary

`mod/Vocabulary.cs` lists every key as `CATEGORY.ENTRY`:
- every model type the game registers (not abstract, not test mocks), by the game's own model ID: `CARD.BASH`, and likewise `RELIC`, `POTION`, `MONSTER`, `ENCOUNTER`, `POWER`, `EVENT`, `ENCHANTMENT`, `AFFLICTION`, `CHARACTER`, `ACT`, `ORB` and the rest;
- the game enums the protocol sends: card type, rarity, keyword, target type, intent type, map point type;
- names kept only in localisation tables: event pages and options (each event's table, keys under `<EVENT>.pages.`), rest site options (`OPTION_<ID>` in `rest_site_ui`), card reward alternatives (`OPTION_<ID>` in `card_reward_ui`);
- the protocol's own names: reward types, shop item types, card selection purposes, the hidden intent, Crystal Sphere tools.

The list goes in `hello`. `agent/env/vocabulary.json` holds `game_version` and the keys in index order; index 0 is padding. `python -m agent.env.vocabulary --update` launches one game copy and appends the keys the file lacks, sorted, at the end; removed keys stay. `vocabulary.py` computes the content hash (SHA-256 of the keys), refuses a `hello` whose `game_version` differs from the file's or whose keys are not all in the file, and raises on any value outside the vocabulary.

### Environment

`agent/` becomes a package run as modules; its tests move to `agent/tests/`. `pyproject.toml` pins the Python version and numpy.

**`encoding.py`** turns a decision into a dict of padded arrays, each with a presence mask, and maps between action indices and the game's actions. Every size is a constant here. Initial sizes come from the game's limits where it has one (10 cards in hand, a 7-column map, the 11 by 11 Crystal Sphere); the rest start as guesses and are replaced by the largest sizes seen over a sweep of random runs, with margin.

| Set | Each entity |
|---|---|
| `hand` (10) | card, plus cost, X cost, star cost, playable, target type and numbers after modifiers |
| `deck`, `draw`, `discard`, `exhaust` | card |
| `enemies` (living only) | monster ID, HP as a fraction of max HP, max HP, block; powers (ID, amount); intents (type, damage, hits) |
| `player_powers` | power ID, amount |
| `relics` | relic ID, counter |
| `potions` | potion ID, target type, per slot |
| `map` | point type, row, column, current, travelable, and for a travelable point, route summaries to the boss: the fewest and most elites, rest sites, shops and unknown rooms on any path from it |
| `rewards` | type, ID, gold, group |
| `choices` | card, plus picked and bundle index: card reward cards, cards offered in a selection, bundle cards |
| `options` | an event option (text key, locked, proceed, deadly, relic), a rest site option (ID, enabled) or a card reward alternative (ID) |
| `shop` | item type, ID or card, cost, on sale, stocked, affordable |
| `cells` (121) | hidden |
| `global` | kind, character, act, floor, HP, max HP, gold, ascension, boss, second boss, encounter, run counters; in combat turn, energy, stars, block; event ID and page; selection purpose, minimum, maximum, picked count; treasure relic; Crystal Sphere divinations and tool |

A card's features: ID, upgrade, type, rarity, damage, block, magic (the first other variable in the game's order), keywords as multi-hot, enchantment ID and amount, affliction ID and amount. Numbers follow fixed rules: HP as a fraction of max HP, signed `log1p` for amounts, map positions divided by the grid size, booleans as 0 or 1. Every ID goes through the vocabulary, its category taken from the field it is in.

Action segments, in order:

| Segment | Size | Legal when |
|---|---|---|
| `play` | 10 × (1 + E) | a hand card, untargeted or on living enemy j |
| `potion` | P × (1 + E) | a potion slot, untargeted or on enemy j |
| `end_turn` | 1 | |
| `travel` | M | a map point the game lets the player move to |
| `reward` | R | a reward that can be taken now |
| `card` | C | a card reward card, or a selection card not yet picked |
| `option` | O | an event option, rest site option or card reward alternative |
| `shop` | I | an item in stock the player can afford |
| `bundle` | B | |
| `cell` | 121 | a hidden Crystal Sphere cell |
| `tool` | 1 | switch the divination |
| `take` | 1 | the treasure relic |
| `confirm` | 1 | a selection with at least the minimum picked |
| `proceed` | 1 | proceed, leave or skip |

Each of the game's actions maps to exactly one index, and the mask is exactly those indices. A card selection is played as single picks: each pick step marks a card as picked without involving the game, confirm is legal from the minimum, and at the maximum the environment sends the picks, sorted. A decision that does not fit a set's size raises, naming the set, its size and the limit.

**`reward.py`** defines the reward once, with its documentation: `+1` for a win, `-1` for a loss, and for each shaping term `w * (gamma * score(next) - score(state))` with `gamma` the learner's discount; `score(next)` is 0 when the step is terminated, not when truncated.

| Score | Meaning |
|---|---|
| floor | floor / 48, a full run at ascension 0 |
| hp | HP / max HP |
| combat | (combats won + the current combat's fraction of enemy HP removed) / 48, at most one combat per floor; the fraction is over every enemy seen in this combat by combat ID, so a summon adds its HP when it appears |
| kills | (elites + bosses killed) / 48: the map generator's cap of 15 elites per act plus one boss per act |

The four weights sit in one dict, starting at 0.25 each, so every weighted score stays within ±1.

**`environment.py`**, one per game process:
- `reset(seed=None, options=None)` (re)launches the game if it is not waiting at `ready`, canonicalises the seed as the game does or draws one from the environment's own seeded generator, sends `start`, and returns the first observation with `info` holding the seed.
- `step(action)` checks the action against the mask. An index outside it logs an error naming the index and its segment, keeps the run's full trace and raises; the next `reset` relaunches the game. Otherwise it answers the decision or records a pick, and returns `(obs, reward, terminated, truncated, info)`, with `info` holding the seed, floor, kind, outcome, the outcome reward and each term's score.
- `action_masks()` returns the current mask.
- Only `run_end` is terminated. The game exiting, the connection closing, or no message within `hang_seconds` (a setting, 120 s by default) of anything sent ends the episode as truncated: the environment kills the game, returns the last observation, sets the outcome to `failed: <reason>` and logs an error with the reason (the game log's own error line when there is one), decision kind, floor, seed and game log. Reaching `step_cap` is truncated with outcome `step_limit`; the game's run is still in progress, so the next `reset` relaunches the game.
- Per run, `info["run"]` reports each term's discounted contribution, highest score and score just before the end. The environment logs each new largest size of any set.
- Records go in the run folder: a full trace (`.trace.jsonl`, one row per step: the decision, the action index, the outcome reward and each term's score) for evaluation runs (`options={"evaluation": True}`), failed runs and one in `trace_every` training runs; otherwise one row in `summary.jsonl` with the seed, outcome, floor, steps, each term's discounted contribution, highest and final score, the failure reason and the action indices.

**`games.py`** finds and launches the game. The game copy for the targeted build lives in `games/<build>/` (gitignored; `STH_GAMES_DIR` overrides the location). Its hash is SHA-256 over the relative paths and contents of every file except `mods/`, and the environment refuses a copy whose hash differs from `GAME_VERSION.md`'s. `SlayTheSpire2.exe` is launched directly with `SteamAppId` and `SteamGameId` set to the app ID, `--slay-the-human-run`, the port, `--headless`, `--time-scale` and the game's own `--log-file`; Steam must be running, which `games.py` checks first. `make_environments(n, ...)` launches n games one after another, each waiting for its game's first `ready` before the next launches, so start-ups never pile up.

### Random agent and tools

`agent/random_agent.py` drives environments, picking uniformly among legal indices from a seeded generator, and is the speed command:

    python -m agent.random_agent --games N --runs R [--seed S] [--trace-every N] [--think-seconds S --think-count K] [--replay SUMMARY --row I]

It runs one thread per game and prints steps per second (per game and total), runs per hour, mean and largest floor, and the largest size of each set. `--think-seconds` sleeps before K actions, to check the game waits. `--replay` plays a summary row's seed and action indices and checks outcome, floor and steps match.

`tools/run.sh` goes: `--games 1 --runs 1` covers it, and its checks leave `tools/test.sh`. `tools/copy-game.sh` (new) checks the installed build as the other tools do, copies the game to `games/<build>/` and prints the hash for `GAME_VERSION.md`. `tools/mod.sh` also installs the mod into that copy when it exists.

### Fake game and recordings

`agent/tests/fake_game.py` speaks protocol 4 and is launched exactly like the game, through `games.py`, with Python as the executable. After `start` it plays recorded decisions in order, checks each answer, ends with `run_end` and goes back to `ready`. It has modes to hang, exit mid-run, speak another version or game version, or send a value outside the vocabulary.

`agent/tests/recordings/decisions.jsonl` holds one real decision of every kind, taken from traces of real protocol 4 runs, including a mid-combat selection, a selection with a maximum above 1, a bundle and the Crystal Sphere (found by searching seeds). The encoding test round-trips each: every array has its constant's shape and values in range, the mask count equals the legal actions, action → index → action is the identity, and IDs map to vocabulary indices and back.

### Known limits

- Orbs (Defect) and Osty (Necrobinder) are not in the protocol; this environment covers characters without them, which includes Ironclad. A later character adds them.
- The reward's denominators assume 48 floors (ascension 0); ascension 10's second boss on floor 49 is the ascension spec's to handle.
- The random agent now picks uniformly over masked indices, card selections pick by pick, so the random baseline is measured again on this environment.

## Changes

- `docs/protocol.md`: protocol 4.
- `mod/Bridge.cs`: connects at the first main menu; `hello` with game version and vocabulary; `ready`, `start`; no answer timeout; one connection across runs; ids reset per run.
- `mod/RunLoop.cs` (replaces `mod/StartAutoSlay.cs`): the run loop, the game kept open after a run that ended normally, per-run reset, the unlock check.
- `mod/RunProfile.cs`: the unlock prefixes, the fixed in-memory profile, no progress writes.
- `mod/RunTiming.cs`: AutoSlay's delays become one frame, its timeouts and watchdog off.
- `mod/Wait.cs`: `Until` logs instead of throwing; `For` removed.
- `mod/RunMode.cs`, `mod/RunLog.cs`: per-run seed and character; room handler attached once; end flag reset; combat counters.
- `mod/GameState.cs`: the run, map, combat and card objects, moved from `Decision.cs`, `CombatSnapshot.cs` and `AgentMap.cs`.
- `mod/Decision.cs`, `mod/CombatSnapshot.cs` (actions only), `mod/AgentMap.cs`, `mod/AgentRewards.cs`, `mod/AgentEvent.cs`, `mod/AgentShop.cs`, `mod/AgentCardReward.cs`, `mod/AgentCardSelect.cs`, `mod/AgentBundle.cs`, `mod/AgentCombat.cs`: protocol 4 state, card objects, waits on outcomes.
- `mod/Vocabulary.cs`: the key list.
- `agent/__init__.py`, `agent/bridge.py` (protocol 4 client), `agent/random_agent.py`.
- `agent/env/`: `environment.py`, `encoding.py`, `vocabulary.py`, `vocabulary.json`, `reward.py`, `games.py`.
- `agent/tests/`: `test_bridge.py` (moved), `test_vocabulary.py`, `test_encoding.py`, `test_reward.py`, `test_games.py`, `test_environment.py`, `fake_game.py`, `recordings/decisions.jsonl`.
- `pyproject.toml`; `.github/workflows/tests.yml` installs it and runs the tests under `agent/tests`.
- `tools/copy-game.sh` (new), `tools/mod.sh`, `tools/test.sh`; `tools/run.sh` removed.
- `.gitignore` (`/games/`), `GAME_VERSION.md` (game version, copy location and hash), `README.md` (the environment and speed command; numpy replaces "standard library only"), `docs/architecture.md`, `CONTEXT.md` ("game copy"), `ROADMAP.md` (the training environment done; measured speed).

## Verification

| Acceptance criterion | Check |
|---|---|
| Gymnasium shape, seed recorded, info | `test_environment`: reset with and without a seed, step tuples, `info` keys, `action_masks`; a real run with the speed command |
| Environment starts runs over the bridge; protocol documented | `test_bridge` (`ready`/`start`/`run_end`, version mismatch); `tools/test.sh` protocol check; the game log's `run start seed=<s> character=<c>` matches what the environment sent |
| Fixed-shape observation, sizes in one place, largest logged, overflow loud | `test_encoding` on every recording; an oversize decision raises naming the set; the environment log's largest-size lines; the speed command's sizes |
| Everything a player can look up | `test_encoding`: every card in every recording has every card field, every decision has `map` and `boss`, the mid-combat selection has `combat` with `encounter` and piles. In a real trace, a card whose base number grew shows it in `vars`; with Strength, a hand card's `preview` damage exceeds its base |
| One index per legal action, exact mask | `test_encoding`: mask count equals the legal actions; index → action → index is the identity |
| Multi-card picks | `test_environment` with a recorded selection (minimum 1, maximum 3): picks in any order, picked marked, confirm from the minimum, automatic submit at the maximum, indices sent sorted |
| Vocabulary | `test_vocabulary`: keys by category, append-only update, hash, unknown value raises, another `game_version` or missing keys refused (also via the fake game); on the targeted build, `--update` adds nothing to the committed file |
| Illegal action | `test_environment`: an unmasked index raises naming it, the run's trace is kept, the next reset relaunches the game |
| Reward definition | `test_reward`: hand-worked values; shaping over a terminated run sums to the starting scores' negative; scores 0 on terminated, not on truncated; a summon lowers the fraction but winning the fight never lowers the combat score |
| Per-step terms, recomputable, per-run report | `test_environment`: every step's `info` has the outcome reward and scores; shaping recomputed from a trace with the same and another `gamma` matches the formula; `info["run"]` has the three per-term figures |
| Several games, launched directly, staggered | `test_environment` with 3 fake games: each launches only after the previous one's `ready`; real `--games 8` runs with no `steam.exe -applaunch` |
| Game copy and hash | `test_games`: hash stable, a changed file refused; `copy-game.sh` output in `GAME_VERSION.md` |
| Unlocks all, no profile writes | `unlocks=all` in every run's game log; the modded profile folder's hash unchanged after 20 runs; the two-profile determinism check |
| 10 runs per process | `--games 1 --runs 10`: one launch in the environment log, ten `run start` lines in one game log; `test_environment`: the same fake game process across 10 resets |
| Waits on state, not fixed times | no delay or `Wait.For` left in `mod/`; `RunTiming`'s startup counts; 20 full runs without failure; decisions per second before and after |
| No time limit on answers | `--think-seconds 360 --think-count 5`: the run completes, passing every handler timeout and the 25-minute run timeout |
| Failures truncated and logged; restart | `test_environment` with the fake game's hang and exit modes; real: kill the game mid-run, see the error line (reason, kind, floor) and a relaunch at the next reset |
| Step limit | `test_environment` with a small `step_cap` |
| Same seed and actions, same results | same seed and agent seed with `--trace-every 1`, traces compared with `cmp`: first run after launch vs after three other seeds in the same process; one game vs one of eight; idle vs every core loaded by busy loops; the modded profile as is vs a fresh default profile (files moved aside and restored); plus `--replay` of a summary row |
| Traces and summary rows | `test_environment`: full traces for evaluation, failed and one in N runs; summary rows with every field; replaying a row's actions on the fake game gives the same steps |
| Speed command | `--games 1` and `--games 8` print the figures |
| Tests in CI | `.github/workflows/tests.yml` green, running the fake game and the recordings |

## Risks

- JIT inlining skips patches on small methods → patches on state machines and big methods; the run-start unlock check and `RunTiming`'s counts fail loudly otherwise.
- Removing fixed waits exposes races (a click before the UI is ready) → each wait becomes a wait on a named state; full runs and the determinism checks find what remains.
- With no in-game timeouts, a real hang waits for Python's hang detection → the game log keeps a "still waiting" line naming the state.
- A long-lived process can leak state or memory across runs → per-run resets; the "after other runs" determinism check; memory watched over 50 runs, with a restart every N runs only if it grows.
- The fixed profile could miss a progress read that changes content → the two-profile and after-other-runs checks.
- The game might write into its own folder, breaking the hash → checked after the first runs; such files excluded by name if found.
- The vocabulary could miss a string value (an event or dialogue key) → fails loudly; a sweep of random runs before the file is committed.
- Set sizes could be too small (random play grows big decks) → measured with margin; overflow fails loudly; a resize changes the schema before any training.
- Bundles and the Crystal Sphere are rare → seeds searched with the speed command.
- The state is sent whole at every decision → the speed command's per-decision time shows its cost.
- Many simultaneous start-ups load slowly → in-game timeouts off, so they wait instead of failing; launches staggered.
- Steam not running makes direct launches fail → `games.py` checks first and says so.
