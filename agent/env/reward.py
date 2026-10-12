"""The reward, defined once.

A step's reward is the sum of its terms, plus the outcome on the step that ends the run:

- Progress (floor, kills, bosses): w * the score's rise. A floor reached for the first time, or an elite or boss killed,
  pays when it happens and is never taken back, so a run's total grows with how far it got.
- Shaping (hp, combat): w * (gamma * score(next state) - score(state)), with gamma the learner's discount. This is
  potential-based shaping: over a terminated run it adds up to minus the starting scores, so it rewards nothing by
  itself and only helps credit the actions within a fight. Its scores fall to 0 when the run is terminated (a win or a
  loss), but not when it is truncated (a failure or the step limit), where the learner bootstraps instead.
- Outcome: a win adds WIN. A loss costs nothing of its own: dying is bad because it ends the progress that would have
  followed, so nothing is gained by putting it off. (A loss penalty would be discounted, so a loss later in steps would
  cost less, and dragging fights out would pay.)

The scores, each between 0 and 1 (a few events can push combat a little past 1):

- floor: floors climbed, out of a full run's 48 at ascension 0.
- hp: HP as a fraction of max HP.
- combat: combats won, plus the current combat's fraction of enemy HP removed, out of 48 (at most one combat a floor).
  The fraction is over every enemy seen in the combat, so a summoned enemy adds its HP when it appears. The score only
  falls when an enemy heals or a summon arrives; winning a fight never lowers it.
- kills: elites and bosses killed, out of 48 (the map's cap of 15 elites an act, plus one boss an act).
- bosses: act bosses killed, out of the 3 acts.

Weights: a full run's floors pay 1, the same as a win, so reaching the end is worth as much as winning there; each kill
pays as much as a floor. Each boss killed also pays one act's share of a win (1/3): an act's boss is the wall a run
has to pass, and as a floor and a kill alone it paid about 0.04, no more than any other floor (spec 011). The shaping
terms keep their weighted scores within 0.25 each. The environment gives the learner each step's outcome reward and
scores, so the terms can be recomputed with another discount without rewriting rewards.
"""

import hashlib
import json

FULL_RUN = 48
ACTS = 3
PROGRESS = {"floor": 1.0, "kills": 1.0, "bosses": 1.0}
SHAPING = {"hp": 0.25, "combat": 0.25}
WEIGHTS = {**PROGRESS, **SHAPING}
OUTCOMES = {"win": 1.0, "loss": 0.0}
# Raised whenever a score's definition changes, so the reward hash changes with it.
REWARD_REVISION = 3


def definition_hash() -> str:
    """SHA-256 of the reward's weights, outcomes, run length and revision: a checkpoint trained on another reward
    refuses to load."""
    definition = {"progress": PROGRESS, "shaping": SHAPING, "outcomes": OUTCOMES, "full_run": FULL_RUN,
                  "revision": REWARD_REVISION}
    return hashlib.sha256(json.dumps(definition, sort_keys=True).encode()).hexdigest()


class Scores:
    """Scores the states of one run. It remembers the enemies of the current combat, for the combat score."""

    def __init__(self) -> None:
        self._combats_won = -1
        self._enemies: dict[int, tuple[int, int]] = {}  # combat ID -> (HP, max HP), for every enemy seen this combat

    def __call__(self, state: dict) -> dict[str, float]:
        run = state["run"]
        if run["combats_won"] != self._combats_won:
            self._combats_won = run["combats_won"]
            self._enemies = {}
        combat = state.get("combat")
        if combat:
            for enemy in combat["enemies"]:
                self._enemies[enemy["combat_id"]] = (max(enemy["hp"], 0) if enemy["alive"] else 0, enemy["max_hp"])
        total = sum(max_hp for _, max_hp in self._enemies.values())
        removed = sum(max_hp - hp for hp, max_hp in self._enemies.values())
        fraction = removed / total if combat and total else 0.0
        return {
            "floor": run["floor"] / FULL_RUN,
            "hp": run["hp"] / run["max_hp"] if run["max_hp"] else 0.0,
            "combat": (run["combats_won"] + fraction) / FULL_RUN,
            "kills": (run["elites_killed"] + run["bosses_killed"]) / FULL_RUN,
            "bosses": run["bosses_killed"] / ACTS,
        }


def zero() -> dict[str, float]:
    """The scores after a terminated run."""
    return dict.fromkeys(WEIGHTS, 0.0)


def terms(before: dict[str, float], after: dict[str, float], gamma: float) -> dict[str, float]:
    """Each term's reward for one step. After a terminated run, after is zero(): progress terms then pay nothing (they
    never go down), and shaping terms fall to their final potential of 0."""
    rewards = {term: weight * max(after[term] - before[term], 0.0) for term, weight in PROGRESS.items()}
    rewards.update({term: weight * (gamma * after[term] - before[term]) for term, weight in SHAPING.items()})
    return rewards


def outcome(result: str | None) -> float:
    """The outcome reward: WIN for a win, 0 for a loss and for a step that does not end the run in the game."""
    return OUTCOMES.get(result, 0.0)


class RunReport:
    """Per run, each term's discounted contribution, highest score and score just before the run ended."""

    def __init__(self, gamma: float, first: dict[str, float]) -> None:
        self._gamma = gamma
        self._discount = 1.0
        self.contribution = dict.fromkeys(WEIGHTS, 0.0)
        self.highest = dict(first)
        self.final = dict(first)

    def add(self, before: dict[str, float], after: dict[str, float], terminated: bool) -> None:
        for term, value in terms(before, after, self._gamma).items():
            self.contribution[term] += self._discount * value
        self._discount *= self._gamma
        if not terminated:
            self.final = dict(after)
            self.highest = {term: max(self.highest[term], after[term]) for term in self.highest}

    def as_dict(self) -> dict:
        return {"contribution": self.contribution, "highest": self.highest, "final": self.final}
