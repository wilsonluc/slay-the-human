"""Turns a decision (docs/protocol.md) into a fixed-shape observation, and maps between the game's actions and one fixed
action space.

The observation is a dict of numpy arrays. Each set (hand, piles, enemies, relics, map, ...) is a padded array of fixed
size with a presence mask; IDs are vocabulary indices (0 is padding) for the model to embed, and numbers are scaled by
fixed rules: HP as a fraction of max HP, signed log1p for amounts, positions by the grid size, flags as 0 or 1. Every
size is a constant below; a decision that does not fit raises, naming the set.

The action space is one flat set of segments (ACTIONS), so every legal action of every kind has its own index, and the
mask marks exactly the legal ones. A card selection is played as single picks: each pick is a step of its own, marked in
the observation, and the environment sends the picks once confirmed or at the maximum.
"""

from collections import deque

import numpy as np

from agent.env.vocabulary import Vocabulary

# Set sizes. Where the game has a limit, it is used; the rest come from the largest sizes measured over random runs,
# with margin.
HAND = 10
ENEMIES = 8
POTIONS = 5
DECK = 100
PILE = 100
RELICS = 40
POWERS = 20
ENEMY_POWERS = 10
INTENTS = 3
MAP = 128
REWARDS = 10
CHOICES = 100
OPTIONS = 10
SHOP = 20
BUNDLES = 4
GRID = 11
CELLS = GRID * GRID
KEYWORDS = 32
MAP_COLUMNS = 7
MAP_ROWS = 20

ACTIONS = [
    ("play", HAND * (1 + ENEMIES)),
    ("potion", POTIONS * (1 + ENEMIES)),
    ("end_turn", 1),
    ("travel", MAP),
    ("reward", REWARDS),
    ("card", CHOICES),
    ("option", OPTIONS),
    ("shop", SHOP),
    ("bundle", BUNDLES),
    ("cell", CELLS),
    ("tool", 1),
    ("take", 1),
    ("confirm", 1),
    ("proceed", 1),
]
OFFSETS = {}
_offset = 0
for _name, _size in ACTIONS:
    OFFSETS[_name] = _offset
    _offset += _size
ACTION_COUNT = _offset

KINDS = ["combat", "map", "reward", "card_reward", "rest", "card_select", "event", "shop", "treasure", "bundle",
         "crystal_sphere"]

# A card's numbers: the three most cards have, then the first other one ("magic"), in the game's order.
CARD_FLOATS = 6 + KEYWORDS  # upgrade, damage, block, magic, enchantment amount, affliction amount, keywords
HAND_FLOATS = 9  # cost, X cost, star cost, playable, damage, block and magic after modifiers, has cost, has star cost
GLOBAL_FLOATS = 22
ROUTE_FLOATS = 8


class EncodingError(Exception):
    """A decision does not fit the fixed sizes, or does not follow the protocol."""


def slog(value) -> float:
    """Signed log1p: keeps small amounts distinct and large ones in range."""
    value = float(value or 0)
    return float(np.sign(value) * np.log1p(abs(value)))


def segment(name: str, i: int = 0) -> int:
    return OFFSETS[name] + i


def describe(index: int) -> str:
    """An action index as segment[i], for errors."""
    for name, size in reversed(ACTIONS):
        if index >= OFFSETS[name]:
            return f"{name}[{index - OFFSETS[name]}]"
    return str(index)


def _fit(name: str, items: list, limit: int) -> list:
    if len(items) > limit:
        raise EncodingError(f"{name} has {len(items)} entries; the observation holds {limit}")
    return items


class Encoder:
    """Encodes decisions with one vocabulary, and records the largest size seen of each set."""

    def __init__(self, vocabulary: Vocabulary) -> None:
        self.vocabulary = vocabulary
        self.largest: dict[str, int] = {}
        keyword_keys = [key for key in vocabulary.keys if key.startswith("KEYWORD.")]
        self._keywords = {key.split(".", 1)[1]: i for i, key in enumerate(keyword_keys)}
        if len(self._keywords) > KEYWORDS:
            raise EncodingError(f"the vocabulary has {len(self._keywords)} keywords; a card holds {KEYWORDS}")

    def _id(self, category: str, entry) -> int:
        return self.vocabulary.index(category, entry)

    def _event_text(self, event: str, key: str) -> int:
        """An event page's or option's text key. An ancient keeps no text of its own (its options are relics, encoded
        beside them), so all of its pages and options go by the ancient's key."""
        if self.vocabulary.has("ANCIENT", event):
            return self._id("ANCIENT", event)
        return self._id("EVENT_TEXT", key)

    def _seen(self, name: str, size: int) -> None:
        if size > self.largest.get(name, -1):
            self.largest[name] = size

    # Cards

    def _card(self, card: dict) -> tuple[list[int], list[float]]:
        """A card's IDs (card, type, rarity, enchantment, affliction) and numbers."""
        enchantment, affliction = card.get("enchantment"), card.get("affliction")
        ids = [self._id("CARD", card["id"]), self._id("CARD_TYPE", card["type"]), self._id("CARD_RARITY", card["rarity"]),
               self._id("ENCHANTMENT", enchantment and enchantment["id"]),
               self._id("AFFLICTION", affliction and affliction["id"])]
        floats = [card["upgrade"], *(slog(value) for value in _numbers(card["vars"])),
                  slog(enchantment and enchantment["amount"]), slog(affliction and affliction["amount"])]
        keywords = [0.0] * KEYWORDS
        for keyword in card["keywords"]:
            if keyword not in self._keywords:
                self._id("KEYWORD", keyword)  # raises, naming it
            keywords[self._keywords[keyword]] = 1.0
        return ids, floats + keywords

    def _cards(self, obs: dict, name: str, cards: list[dict], limit: int, extra=None, extra_size: int = 0) -> None:
        _fit(name, cards, limit)
        self._seen(name, len(cards))
        ids = np.zeros((limit, 5), np.int64)
        floats = np.zeros((limit, CARD_FLOATS + extra_size), np.float32)
        present = np.zeros(limit, np.float32)
        for i, card in enumerate(cards):
            if card is None:
                continue
            card_ids, card_floats = self._card(card)
            ids[i] = card_ids
            floats[i, :CARD_FLOATS] = card_floats
            if extra:
                floats[i, CARD_FLOATS:] = extra(i, card)
            present[i] = 1
        obs[f"{name}_ids"], obs[name], obs[f"{name}_present"] = ids, floats, present

    # The observation

    def encode(self, decision: dict, picked: frozenset = frozenset()) -> tuple[dict, np.ndarray]:
        """The observation and the action mask for a decision; picked is the cards already picked in a selection."""
        state, kind = decision["state"], decision["kind"]
        if kind not in KINDS:
            raise EncodingError(f"unknown decision kind {kind!r}")
        obs: dict[str, np.ndarray] = {}
        run, combat = state["run"], state.get("combat")
        own = state.get(kind) if kind != "map" else state["map"]

        self._cards(obs, "deck", run["deck"], DECK)
        self._relics(obs, run["relics"])
        self._potions(obs, run["potions"])
        self._map(obs, state["map"])
        living = self._combat(obs, combat)
        self._rewards(obs, own["rewards"] if kind == "reward" else [])
        choices, bundle_of = self._choice_cards(kind, own)
        self._cards(obs, "choices", choices, CHOICES, lambda i, card: [float(i in picked), float(bundle_of[i])], 2)
        self._options(obs, kind, own)
        self._shop(obs, own["items"] if kind == "shop" else [])
        self._cells(obs, own if kind == "crystal_sphere" else None)
        self._global(obs, decision, run, combat, own, picked)
        mask = self.mask(decision, living, picked)
        return obs, mask

    def _relics(self, obs, relics):
        _fit("relics", relics, RELICS)
        self._seen("relics", len(relics))
        obs["relics_ids"] = np.zeros(RELICS, np.int64)
        obs["relics"] = np.zeros((RELICS, 2), np.float32)
        obs["relics_present"] = np.zeros(RELICS, np.float32)
        for i, relic in enumerate(relics):
            obs["relics_ids"][i] = self._id("RELIC", relic["id"])
            obs["relics"][i] = [slog(relic["counter"]), float(relic["counter"] is not None)]
            obs["relics_present"][i] = 1

    def _potions(self, obs, potions):
        _fit("potions", potions, POTIONS)
        obs["potions_ids"] = np.zeros((POTIONS, 2), np.int64)
        obs["potions_present"] = np.zeros(POTIONS, np.float32)
        for i, potion in enumerate(potions):
            if potion:
                obs["potions_ids"][i] = [self._id("POTION", potion["id"]), self._id("TARGET", potion["target"])]
                obs["potions_present"][i] = 1

    def _map(self, obs, map_state):
        points, edges = map_state["points"], map_state["edges"]
        _fit("map", points, MAP)
        self._seen("map", len(points))
        children = [[] for _ in points]
        for parent, child in edges:
            children[parent].append(child)
        current = map_state["current"]
        reachable = set(children[current]) if current is not None else {i for i, p in enumerate(points) if p["row"] == 0}
        obs["map_ids"] = np.zeros(MAP, np.int64)
        obs["map"] = np.zeros((MAP, 4 + ROUTE_FLOATS), np.float32)
        obs["map_present"] = np.zeros(MAP, np.float32)
        routes = _routes(points, children)
        for i, point in enumerate(points):
            obs["map_ids"][i] = self._id("MAP_POINT", point["type"])
            obs["map"][i, :4] = [point["row"] / MAP_ROWS, point["col"] / MAP_COLUMNS, float(i == current),
                                 float(i in reachable)]
            obs["map"][i, 4:] = [value / 10 for value in routes[i]]
            obs["map_present"][i] = 1

    def _combat(self, obs, combat) -> list[int]:
        """Encodes the combat (zeros when none) and returns the protocol indices of the living enemies, in slot order."""
        hand = combat["hand"] if combat else []
        self._cards(obs, "hand", hand, HAND, lambda i, card: _hand_numbers(card), HAND_FLOATS)
        for pile in ("draw", "discard", "exhaust"):
            self._cards(obs, pile, combat[pile] if combat else [], PILE)
        player_powers = combat["player"]["powers"] if combat else []
        obs["player_powers_ids"], obs["player_powers"], obs["player_powers_present"] = self._powers(
            "player_powers", player_powers, POWERS)
        living = [i for i, enemy in enumerate(combat["enemies"]) if enemy["alive"]] if combat else []
        _fit("enemies", living, ENEMIES)
        self._seen("enemies", len(living))
        obs["enemies_ids"] = np.zeros(ENEMIES, np.int64)
        obs["enemies"] = np.zeros((ENEMIES, 3), np.float32)
        obs["enemies_present"] = np.zeros(ENEMIES, np.float32)
        obs["enemy_powers_ids"] = np.zeros((ENEMIES, ENEMY_POWERS), np.int64)
        obs["enemy_powers"] = np.zeros((ENEMIES, ENEMY_POWERS), np.float32)
        obs["enemy_powers_present"] = np.zeros((ENEMIES, ENEMY_POWERS), np.float32)
        obs["intents_ids"] = np.zeros((ENEMIES, INTENTS), np.int64)
        obs["intents"] = np.zeros((ENEMIES, INTENTS, 2), np.float32)
        obs["intents_present"] = np.zeros((ENEMIES, INTENTS), np.float32)
        for slot, i in enumerate(living):
            enemy = combat["enemies"][i]
            obs["enemies_ids"][slot] = self._id("MONSTER", enemy["id"])
            obs["enemies"][slot] = [enemy["hp"] / enemy["max_hp"] if enemy["max_hp"] else 0.0, slog(enemy["max_hp"]),
                                    slog(enemy["block"])]
            obs["enemies_present"][slot] = 1
            (obs["enemy_powers_ids"][slot], obs["enemy_powers"][slot],
             obs["enemy_powers_present"][slot]) = self._powers("enemy_powers", enemy["powers"], ENEMY_POWERS)
            intents = _fit("intents", enemy["intents"], INTENTS)
            for j, intent in enumerate(intents):
                obs["intents_ids"][slot, j] = self._id("INTENT", intent["type"])
                obs["intents"][slot, j] = [slog(intent["damage"]), slog(intent["hits"])]
                obs["intents_present"][slot, j] = 1
        return living

    def _powers(self, name, powers, limit):
        _fit(name, powers, limit)
        self._seen(name, len(powers))
        ids, amounts, present = np.zeros(limit, np.int64), np.zeros(limit, np.float32), np.zeros(limit, np.float32)
        for i, power in enumerate(powers):
            ids[i], amounts[i], present[i] = self._id("POWER", power["id"]), slog(power["amount"]), 1
        return ids, amounts, present

    def _rewards(self, obs, rewards):
        _fit("rewards", rewards, REWARDS)
        self._seen("rewards", len(rewards))
        categories = {"potion": "POTION", "relic": "RELIC", "special_card": "CARD"}
        obs["rewards_ids"] = np.zeros((REWARDS, 2), np.int64)
        obs["rewards"] = np.zeros((REWARDS, 3), np.float32)
        obs["rewards_present"] = np.zeros(REWARDS, np.float32)
        for i, reward in enumerate(rewards):
            category = categories.get(reward["type"])
            obs["rewards_ids"][i] = [self._id("REWARD_TYPE", reward["type"]),
                                     self._id(category, reward["id"]) if category else 0]
            obs["rewards"][i] = [slog(reward["amount"]), float(reward["group"] is not None),
                                 (reward["group"] or 0) / REWARDS]
            obs["rewards_present"][i] = 1

    def _choice_cards(self, kind, own) -> tuple[list[dict], list[int]]:
        """The cards offered to choose from, and for a bundle screen the bundle each belongs to."""
        if kind in ("card_reward", "card_select"):
            return own["cards"], [0] * len(own["cards"])
        if kind == "bundle":
            _fit("bundles", own["bundles"], BUNDLES)
            cards = [card for bundle in own["bundles"] for card in bundle]
            return cards, [b for b, bundle in enumerate(own["bundles"]) for _ in bundle]
        return [], []

    def _options(self, obs, kind, own):
        obs["options_ids"] = np.zeros((OPTIONS, 2), np.int64)
        obs["options"] = np.zeros((OPTIONS, 4), np.float32)
        obs["options_present"] = np.zeros(OPTIONS, np.float32)
        rows = []
        if kind == "event":
            rows = [([self._event_text(own["id"], _option_text(o)), self._id("RELIC", o["relic"])],
                     [float(o["locked"]), float(o["proceed"]), float(o["deadly"]), 1.0]) for o in own["options"]]
        elif kind == "rest":
            rows = [([self._id("REST_OPTION", o["id"]), 0], [float(not o["enabled"]), 0.0, 0.0, 1.0])
                    for o in own["options"]]
        elif kind == "card_reward":
            rows = [([self._id("CARD_REWARD_ALTERNATIVE", a.upper()), 0], [0.0, 0.0, 0.0, 1.0])
                    for a in own["alternatives"]]
        _fit("options", rows, OPTIONS)
        self._seen("options", len(rows))
        for i, (ids, floats) in enumerate(rows):
            obs["options_ids"][i], obs["options"][i], obs["options_present"][i] = ids, floats, 1

    def _shop(self, obs, items):
        _fit("shop", items, SHOP)
        self._seen("shop", len(items))
        categories = {"relic": "RELIC", "potion": "POTION"}
        obs["shop_ids"] = np.zeros((SHOP, 2), np.int64)
        obs["shop"] = np.zeros((SHOP, 3), np.float32)
        obs["shop_present"] = np.zeros(SHOP, np.float32)
        for i, item in enumerate(items):
            category = categories.get(item["type"])
            obs["shop_ids"][i] = [self._id("SHOP_ITEM", item["type"]), self._id(category, item["id"]) if category else 0]
            obs["shop"][i] = [slog(item["cost"]), float(item["on_sale"]), float(item["stocked"])]
            obs["shop_present"][i] = 1
        # A card item's card, in the item's slot.
        self._cards(obs, "shop_cards", [item.get("card") for item in items], SHOP)

    def _cells(self, obs, sphere):
        obs["cells"] = np.zeros(CELLS, np.float32)
        if sphere:
            for x, y in sphere["hidden"]:
                obs["cells"][y * GRID + x] = 1

    def _global(self, obs, decision, run, combat, own, picked):
        kind = decision["kind"]
        ids = [self._id("KIND", kind), self._id("CHARACTER", run["character"]), self._id("ENCOUNTER", run["boss"]),
               self._id("ENCOUNTER", run["second_boss"]), self._id("ENCOUNTER", combat and combat["encounter"]),
               self._id("EVENT", own["id"]) if kind == "event" else 0,
               self._event_text(own["id"], own["page"]) if kind == "event" and own["page"] else 0,
               self._id("PURPOSE", own["purpose"]) if kind == "card_select" else 0,
               self._id("RELIC", own["relic"]) if kind == "treasure" else 0,
               self._id("TOOL", own["tool"]) if kind == "crystal_sphere" else 0]
        player = combat["player"] if combat else {}
        select = own if kind == "card_select" else {}
        floats = [
            run["hp"] / run["max_hp"] if run["max_hp"] else 0.0, slog(run["max_hp"]), slog(run["gold"]),
            run["ascension"] / 10, run["act"] / 4, run["floor"] / 50,
            slog(run["combats_won"]), slog(run["elites_killed"]), slog(run["bosses_killed"]),
            float(combat is not None), slog(combat and combat["turn"]), slog(player.get("block")),
            slog(player.get("energy")), slog(player.get("max_energy")), slog(player.get("stars")),
            slog(select.get("min")), slog(select.get("max")), slog(len(picked)),
            slog(own.get("divinations")) if kind == "crystal_sphere" else 0.0,
            float(kind == "treasure" and own["relic"] is not None),
            float(run["second_boss"] is not None), float(len(picked) > 0),
        ]
        assert len(floats) == GLOBAL_FLOATS
        obs["global_ids"] = np.array(ids, np.int64)
        obs["global"] = np.array(floats, np.float32)

    # Actions

    def actions(self, decision: dict, living: list[int], picked: frozenset = frozenset()) -> dict[int, object]:
        """Every legal action index, mapped to the answer it gives the game: an index into the decision's actions, or
        for a card selection ("pick", i) and ("confirm",)."""
        kind, state = decision["kind"], decision["state"]
        slots = {enemy: slot for slot, enemy in enumerate(living)}
        result: dict[int, object] = {}
        if kind == "card_select":
            select = state["card_select"]
            cards = len(select["cards"])
            _fit("choices", select["cards"], CHOICES)
            for i in range(cards):
                if i not in picked and len(picked) < select["max"]:
                    result[segment("card", i)] = ("pick", i)
            if len(picked) >= select["min"]:
                result[segment("confirm")] = ("confirm",)
            return result
        for answer, action in enumerate(decision["actions"]):
            index = self._action_index(kind, state, action, slots)
            if index in result:
                raise EncodingError(f"two of the game's actions map to {describe(index)}: {action}")
            result[index] = answer
        return result

    def _action_index(self, kind, state, action, slots) -> int:
        name = action["kind"]
        if name in ("play", "potion"):
            target = action["target"]
            which = action["card"] if name == "play" else action["slot"]
            limit = HAND if name == "play" else POTIONS
            if which >= limit:
                raise EncodingError(f"{name} {which} is past the {limit} the action space holds")
            if target is not None and target not in slots:
                raise EncodingError(f"{name} targets enemy {target}, which is not alive")
            return segment(name, which * (1 + ENEMIES) + (0 if target is None else 1 + slots[target]))
        if name == "end_turn":
            return segment("end_turn")
        if name == "travel":
            return segment("travel", action["point"])
        if name == "take":
            return segment("reward", action["reward"]) if kind == "reward" else segment("take")
        if name == "pick":
            return segment("bundle", action["bundle"]) if kind == "bundle" else segment("card", action["card"])
        if name == "alternative":
            return segment("option", state["card_reward"]["alternatives"].index(action["option"]))
        if name == "rest":
            return segment("option", action["option"])
        if name == "choose":
            return segment("option", action["option"])
        if name == "buy":
            return segment("shop", action["item"])
        if name == "reveal":
            return segment("cell", action["y"] * GRID + action["x"])
        if name == "tool":
            return segment("tool")
        if name in ("proceed", "leave", "skip"):
            return segment("proceed")
        raise EncodingError(f"unknown action {action}")

    def mask(self, decision: dict, living: list[int], picked: frozenset = frozenset()) -> np.ndarray:
        mask = np.zeros(ACTION_COUNT, bool)
        mask[list(self.actions(decision, living, picked))] = True
        return mask

    def living(self, decision: dict) -> list[int]:
        combat = decision["state"].get("combat")
        return [i for i, enemy in enumerate(combat["enemies"]) if enemy["alive"]] if combat else []


def _option_text(option: dict) -> str:
    """An event option's text key. One that grants a relic is named after the relic at run time
    (NEOW.pages.INITIAL.options.<RELIC>), so its page's options stem stands for it; the relic is encoded beside it."""
    key, relic = option["text_key"], option["relic"]
    if relic and key.endswith(f".options.{relic}"):
        return key[:-len(relic) - 1]
    return key


def _numbers(variables: dict) -> list[float]:
    """Damage, block, and the first other number in the game's order."""
    others = [value for name, value in variables.items() if name not in ("Damage", "Block")]
    return [variables.get("Damage", 0), variables.get("Block", 0), others[0] if others else 0]


def _hand_numbers(card: dict) -> list[float]:
    cost, star = card["cost"], card["star_cost"]
    preview = _numbers(card.get("preview", {}))
    return [slog(max(cost, 0)), float(card["costs_x"]), slog(max(star, 0)), float(card["playable"]),
            *(slog(value) for value in preview), float(cost >= 0), float(star >= 0)]


def _routes(points: list[dict], children: list[list[int]]) -> list[list[int]]:
    """For each point, over every path from it to a point with no children (the boss): the fewest and most elites, rest
    sites, shops and unknown rooms along the way, the point itself included."""
    kinds = ["Elite", "RestSite", "Shop", "Unknown"]
    order = _topological(len(points), children)
    result: list[list[int]] = [[0] * 8 for _ in points]
    for i in reversed(order):
        own = [int(points[i]["type"] == k) for k in kinds]
        if children[i]:
            low = [min(result[c][2 * k] for c in children[i]) for k in range(4)]
            high = [max(result[c][2 * k + 1] for c in children[i]) for k in range(4)]
        else:
            low = high = [0] * 4
        result[i] = [v for k in range(4) for v in (own[k] + low[k], own[k] + high[k])]
    return result


def _topological(count: int, children: list[list[int]]) -> list[int]:
    incoming = [0] * count
    for kids in children:
        for c in kids:
            incoming[c] += 1
    queue = deque(i for i in range(count) if incoming[i] == 0)
    order = []
    while queue:
        i = queue.popleft()
        order.append(i)
        for c in children[i]:
            incoming[c] -= 1
            if incoming[c] == 0:
                queue.append(c)
    if len(order) != count:
        raise EncodingError("the map has a cycle")
    return order
