"""Every name the observation encodes, each with its own index, for the targeted game build.

The keys are CATEGORY.ENTRY (CARD.BASH, RELIC.BURNING_BLOOD, ENCOUNTER.NIBBITS_WEAK, ...), so the same name in two
categories gets two indices. They come from the game (the mod sends them in its hello) and from the protocol's own names
(PROTOCOL_KEYS). vocabulary.json is committed and only grows: new keys are appended at the end and removed ones keep
their index, so a game patch that adds content never moves an existing index. Index 0 is padding.

    python -m agent.env.vocabulary --update    launches the game copy and appends the keys the file lacks
"""

import hashlib
import json
import sys
from pathlib import Path

FILE = Path(__file__).with_name("vocabulary.json")

# Names the protocol defines (docs/protocol.md) rather than the game.
PROTOCOL_KEYS = [
    *(f"KIND.{kind}" for kind in ("combat", "map", "reward", "card_reward", "rest", "card_select", "event", "shop",
                                  "treasure", "bundle", "crystal_sphere")),
    *(f"REWARD_TYPE.{kind}" for kind in ("gold", "potion", "relic", "card", "special_card", "card_removal", "other")),
    *(f"SHOP_ITEM.{kind}" for kind in ("card", "relic", "potion", "card_removal", "other")),
    *(f"PURPOSE.{purpose}" for purpose in ("upgrade", "transform", "enchant", "remove", "discard", "exhaust",
                                           "hand_upgrade", "hand", "deck", "choose", "grid", "reward_grid",
                                           "combat_pile", "other")),
    "INTENT.Hidden",
    "TOOL.Big", "TOOL.Small",
]


class VocabularyError(Exception):
    """A value outside the vocabulary, or a game the vocabulary was not made from."""


class Vocabulary:
    def __init__(self, game_version: str, keys: list[str]) -> None:
        self.game_version = game_version
        self.keys = list(keys)
        self._index = {key: i + 1 for i, key in enumerate(self.keys)}
        if len(self._index) != len(self.keys):
            raise VocabularyError("the vocabulary has a key twice")

    @classmethod
    def load(cls, path: Path = FILE) -> "Vocabulary":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data["game_version"], data["keys"])

    def save(self, path: Path = FILE) -> None:
        path.write_text(json.dumps({"game_version": self.game_version, "keys": self.keys}, indent=1) + "\n",
                        encoding="utf-8", newline="\n")

    def __len__(self) -> int:
        """The number of indices, padding included."""
        return len(self.keys) + 1

    @property
    def hash(self) -> str:
        return hashlib.sha256("\n".join(self.keys).encode()).hexdigest()

    def index(self, category: str, entry: str | None) -> int:
        """The index of CATEGORY.ENTRY; 0 for None (nothing there). Any other value outside the vocabulary raises."""
        if entry is None:
            return 0
        key = f"{category}.{entry}"
        if (found := self._index.get(key)) is None:
            raise VocabularyError(f"{key} is not in the vocabulary; update it for this game build "
                                  f"(python -m agent.env.vocabulary --update)")
        return found

    def has(self, category: str, entry: str) -> bool:
        return f"{category}.{entry}" in self._index

    def check(self, hello: dict) -> None:
        """Refuses a game whose version differs from the vocabulary's, or that has names the vocabulary lacks."""
        if hello.get("game_version") != self.game_version:
            raise VocabularyError(f"the game is {hello.get('game_version')}, but the vocabulary was made from "
                                  f"{self.game_version}")
        if missing := sorted(set(hello.get("vocabulary", [])) - set(self.keys)):
            raise VocabularyError(f"the vocabulary lacks {len(missing)} of the game's names, such as {missing[:5]}")

    def updated(self, game_version: str, game_keys: list[str]) -> "Vocabulary":
        """A vocabulary with every new key appended, sorted, after the existing ones."""
        new = sorted((set(game_keys) | set(PROTOCOL_KEYS)) - set(self.keys))
        return Vocabulary(game_version, self.keys + new)


def game_hello() -> dict:
    """Launches one game copy and returns its hello, then lets it quit."""
    from agent.bridge import Bridge
    from agent.env import games

    bridge = Bridge()
    log = Path("runs") / "vocabulary.log"
    log.parent.mkdir(exist_ok=True)
    game = games.launch(bridge.port, log.resolve())
    try:
        hello = bridge.accept()
        if bridge.receive(120).get("type") != "ready":
            raise VocabularyError("the game did not reach the main menu")
        bridge.close()
        game.wait(timeout=60)
        return hello
    finally:
        if game.poll() is None:
            game.kill()


def main() -> int:
    if sys.argv[1:] != ["--update"]:
        sys.exit("usage: python -m agent.env.vocabulary --update")
    hello = game_hello()
    current = Vocabulary.load() if FILE.exists() else Vocabulary(hello["game_version"], [])
    updated = current.updated(hello["game_version"], hello["vocabulary"])
    updated.save()
    print(f"vocabulary: {len(updated.keys) - len(current.keys)} keys added, {len(updated.keys)} in all, "
          f"game {updated.game_version}, hash {updated.hash}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
