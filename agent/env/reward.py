"""The reward, defined once.

A step's reward is the outcome plus shaping:

- Outcome: +1 for a win and -1 for a loss, on the step that ends the run.
- Shaping: for each term, w * (gamma * score(next state) - score(state)), with gamma the learner's discount. This is
  potential-based shaping, which never changes which policy is best. Every score falls to 0 when the run is terminated
  (a win or a loss), but not when it is truncated (a failure or the step limit), where the learner bootstraps instead.

The scores, each between 0 and 1 (a few events can push combat a little past 1):

- floor: floors climbed, out of a full run's 48 at ascension 0.
- hp: HP as a fraction of max HP.
- combat: combats won, plus the current combat's fraction of enemy HP removed, out of 48 (at most one combat a floor).
  The fraction is over every enemy seen in the combat, so a summoned enemy adds its HP when it appears. The score only
  falls when an enemy heals or a summon arrives; winning a fight never lowers it.
- kills: elites and bosses killed, out of 48 (the map's cap of 15 elites an act, plus one boss an act).

Each term's weight keeps its weighted score within 1, so the return needs no scaling. The environment gives the learner
each step's outcome reward and scores, so shaping can be recomputed with another discount without rewriting rewards.
"""

FULL_RUN = 48
WEIGHTS = {"floor": 0.25, "hp": 0.25, "combat": 0.25, "kills": 0.25}
OUTCOMES = {"win": 1.0, "loss": -1.0}


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
        }


def zero() -> dict[str, float]:
    """The scores after a terminated run."""
    return dict.fromkeys(WEIGHTS, 0.0)


def shaping(before: dict[str, float], after: dict[str, float], gamma: float,
            weights: dict[str, float] = WEIGHTS) -> dict[str, float]:
    """Each term's shaping reward for one step."""
    return {term: weight * (gamma * after[term] - before[term]) for term, weight in weights.items()}


def outcome(result: str | None) -> float:
    """The outcome reward: +1 for a win, -1 for a loss, 0 for a step that does not end the run in the game."""
    return OUTCOMES.get(result, 0.0)


class RunReport:
    """Per run, each term's discounted contribution, highest score and score just before the run ended."""

    def __init__(self, gamma: float, first: dict[str, float], weights: dict[str, float] = WEIGHTS) -> None:
        self._gamma, self._weights = gamma, weights
        self._discount = 1.0
        self.contribution = dict.fromkeys(weights, 0.0)
        self.highest = dict(first)
        self.final = dict(first)

    def add(self, before: dict[str, float], after: dict[str, float], terminated: bool) -> None:
        for term, value in shaping(before, after, self._gamma, self._weights).items():
            self.contribution[term] += self._discount * value
        self._discount *= self._gamma
        if not terminated:
            self.final = dict(after)
            self.highest = {term: max(self.highest[term], after[term]) for term in self.highest}

    def as_dict(self) -> dict:
        return {"contribution": self.contribution, "highest": self.highest, "final": self.final}
