"""The policy and value network over the structured observation (docs/architecture.md).

Every ID is embedded from one table over the whole vocabulary. Each set's entities go through a network shared within
the set, then are pooled with the presence masks (mean and max) into the state vector, with the global IDs and numbers.
Action logits are pointer-style: each segment scores the entities its actions name together with the state, so a
card's logit follows the card wherever it sits, and reordering a set's entities reorders its logits and nothing else.
"""

import numpy as np
import torch
from torch import nn

from agent.env import encoding
from agent.env.encoding import ACTIONS, GRID

# Sets of entities with their own network: name -> (IDs per entity, numbers per entity). Their arrays are
# <name>_ids, <name> and <name>_present in the observation.
SETS = {
    "deck": (5, encoding.CARD_FLOATS),
    "hand": (5, encoding.CARD_FLOATS + encoding.HAND_FLOATS),
    "draw": (5, encoding.CARD_FLOATS),
    "discard": (5, encoding.CARD_FLOATS),
    "exhaust": (5, encoding.CARD_FLOATS),
    "choices": (5, encoding.CARD_FLOATS + 2),
    "shop_cards": (5, encoding.CARD_FLOATS),
    "relics": (1, 2),
    "potions": (2, 0),
    "map": (1, 4 + encoding.ROUTE_FLOATS),
    "rewards": (2, 3),
    "options": (2, 4),
    "shop": (2, 3),
}
# Pooled into the state, besides SETS: player powers, enemies and Crystal Sphere cells.
POOLED = list(SETS) + ["player_powers", "enemies", "cells"]
SINGLE = ["end_turn", "tool", "take", "confirm", "proceed"]
# Illegal actions' logits; exp of it is exactly 0 in float32, so they get no probability and no gradient.
ILLEGAL = -1e8


def masked(logits: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """Logits with every illegal action replaced, for sampling and for the update alike."""
    return torch.where(mask, logits, torch.full_like(logits, ILLEGAL))


def as_tensors(obs: dict[str, np.ndarray], device="cpu") -> dict[str, torch.Tensor]:
    """A batch of observations (arrays with a leading batch axis) as tensors: IDs as int64, the rest as float32."""
    return {key: torch.as_tensor(value, device=device).long() if key.endswith("_ids")
            else torch.as_tensor(value, device=device).float() for key, value in obs.items()}


class Entities(nn.Module):
    """One entity per row: its ID embeddings and numbers through two layers. Only present entities are computed (most
    rows of the big sets are padding); absent ones are zeros. Outputs are non-negative (ReLU), so a masked max over a
    set is a max of the entities times their presence."""

    def __init__(self, inputs: int, hidden: int) -> None:
        super().__init__()
        self.hidden = hidden
        self.net = nn.Sequential(nn.Linear(inputs, hidden), nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU())

    def forward(self, x: torch.Tensor, present: torch.Tensor) -> torch.Tensor:
        rows = present > 0
        out = x.new_zeros(*x.shape[:-1], self.hidden)
        out[rows] = self.net(x[rows])
        return out


class Scorer(nn.Module):
    """A segment's logit for each entity: w . relu(A entity + B state)."""

    def __init__(self, entity: int, state: int, hidden: int) -> None:
        super().__init__()
        self.entity, self.state = nn.Linear(entity, hidden), nn.Linear(state, hidden, bias=False)
        self.out = nn.Linear(hidden, 1)
        nn.init.orthogonal_(self.out.weight, gain=0.01)  # near-uniform policy at the start
        nn.init.zeros_(self.out.bias)

    def forward(self, entities: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        """entities [B, ..., E], state [B, S] -> logits [B, ...]."""
        s = self.state(state)
        s = s.view(s.shape[0], *([1] * (entities.dim() - 2)), s.shape[-1])
        return self.out(torch.relu(self.entity(entities) + s)).squeeze(-1)


class PairScorer(Scorer):
    """A logit for each (actor, target) pair: w . relu(A actor + C target + B state), with A and C applied once per
    entity rather than once per pair."""

    def __init__(self, entity: int, state: int, hidden: int) -> None:
        super().__init__(entity, state, hidden)
        self.target = nn.Linear(entity, hidden, bias=False)

    def forward(self, actors: torch.Tensor, targets: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        """actors [B, A, E], targets [B, T, E], state [B, S] -> logits [B, A * T], actor-major."""
        x = (self.entity(actors).unsqueeze(2) + self.target(targets).unsqueeze(1)
             + self.state(state).unsqueeze(1).unsqueeze(1))
        return self.out(torch.relu(x)).squeeze(-1).flatten(1)


def pool(x: torch.Tensor, present: torch.Tensor) -> torch.Tensor:
    """Masked mean and max over the entity axis (-2): [..., N, H] -> [..., 2H]. An empty set gives zeros."""
    m = present.unsqueeze(-1)
    x = x * m
    return torch.cat([x.sum(-2) / m.sum(-2).clamp(min=1), x.max(-2).values], -1)


class Policy(nn.Module):
    def __init__(self, vocabulary_size: int, embed: int = 32, hidden: int = 128, state: int = 256) -> None:
        super().__init__()
        self.embedding = nn.Embedding(vocabulary_size, embed, padding_idx=0)
        self.sets = nn.ModuleDict({name: Entities(ids * embed + floats, hidden) for name, (ids, floats) in SETS.items()})
        self.powers = Entities(embed + 1, hidden)
        self.intents = Entities(embed + 2, hidden)
        self.enemies = Entities(embed + 3 + 4 * hidden, hidden)
        self.cells = Entities(3, hidden)
        cell = torch.arange(encoding.CELLS)
        self.register_buffer("cell_position", torch.stack([cell % GRID, cell // GRID], -1).float() / GRID,
                             persistent=False)
        globals_in = 10 * embed + encoding.GLOBAL_FLOATS + 2 * hidden * len(POOLED)
        self.state = nn.Sequential(nn.Linear(globals_in, state), nn.ReLU(), nn.Linear(state, state), nn.ReLU())
        self.value = nn.Linear(state, 1)
        self.no_target = nn.Parameter(torch.zeros(hidden))
        self.scorers = nn.ModuleDict({
            "play": PairScorer(hidden, state, hidden), "potion": PairScorer(hidden, state, hidden),
            **{name: Scorer(hidden, state, hidden) for name in ("travel", "reward", "card", "option", "shop", "bundle",
                                                               "cell")}})
        self.single = nn.Linear(state, len(SINGLE))
        nn.init.orthogonal_(self.single.weight, gain=0.01)
        nn.init.zeros_(self.single.bias)

    def forward(self, obs: dict[str, torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor]:
        """A batch of observations -> (logits [B, ACTION_COUNT] before masking, value [B])."""
        entity: dict[str, torch.Tensor] = {}
        for name, (ids, floats) in SETS.items():
            parts = [self.embedding(obs[f"{name}_ids"]).flatten(-2) if ids > 1 else self.embedding(obs[f"{name}_ids"])]
            if floats:
                parts.append(obs[name])
            entity[name] = self.sets[name](torch.cat(parts, -1), obs[f"{name}_present"])

        entity["player_powers"] = self.powers(torch.cat([self.embedding(obs["player_powers_ids"]),
                                                         obs["player_powers"].unsqueeze(-1)], -1),
                                              obs["player_powers_present"])
        enemy_powers = self.powers(torch.cat([self.embedding(obs["enemy_powers_ids"]),
                                              obs["enemy_powers"].unsqueeze(-1)], -1), obs["enemy_powers_present"])
        intents = self.intents(torch.cat([self.embedding(obs["intents_ids"]), obs["intents"]], -1),
                               obs["intents_present"])
        entity["enemies"] = self.enemies(torch.cat([
            self.embedding(obs["enemies_ids"]), obs["enemies"], pool(enemy_powers, obs["enemy_powers_present"]),
            pool(intents, obs["intents_present"])], -1), obs["enemies_present"])
        # Crystal Sphere cells: the hidden ones are the entities (only they can be revealed).
        cells = obs["cells"]
        entity["cells"] = self.cells(torch.cat([cells.unsqueeze(-1),
                                                self.cell_position.expand(cells.shape[0], -1, -1)], -1), cells)

        present = {name: obs[f"{name}_present"] for name in POOLED if name != "cells"}
        present["cells"] = cells
        pooled = [pool(entity[name], present[name]) for name in POOLED]
        state = self.state(torch.cat([self.embedding(obs["global_ids"]).flatten(-2), obs["global"], *pooled], -1))

        batch = state.shape[0]
        targets = torch.cat([self.no_target.expand(batch, 1, -1), entity["enemies"]], 1)  # [B, 1 + ENEMIES, H]

        choices = entity["choices"]
        bundle_of = obs["choices"][..., -1]
        in_bundle = torch.stack([(bundle_of == b) & (obs["choices_present"] > 0)
                                 for b in range(encoding.BUNDLES)], 1).float()  # [B, BUNDLES, CHOICES]
        bundles = in_bundle @ choices / in_bundle.sum(-1, keepdim=True).clamp(min=1)
        single = self.single(state)
        segments = {
            "play": self.scorers["play"](entity["hand"], targets, state),
            "potion": self.scorers["potion"](entity["potions"], targets, state),
            "travel": self.scorers["travel"](entity["map"], state),
            "reward": self.scorers["reward"](entity["rewards"], state),
            "card": self.scorers["card"](choices, state),
            "option": self.scorers["option"](entity["options"], state),
            "shop": self.scorers["shop"](entity["shop"] + entity["shop_cards"], state),
            "bundle": self.scorers["bundle"](bundles, state),
            "cell": self.scorers["cell"](entity["cells"], state),
            **{name: single[:, i:i + 1] for i, name in enumerate(SINGLE)},
        }
        logits = torch.cat([segments[name] for name, _ in ACTIONS], 1)
        return logits, self.value(state).squeeze(-1)
