"""Collects rollouts: each game fills its own column of the buffer, in its own thread.

Games never wait for each other, so a slow combat on one game does not hold up the rest, and each game's choices depend
only on its own seeds (its environment's game seeds and its own sampling generator): the result is the same however
the threads interleave. The policy's weights do not change while collecting.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import torch

from agent.bridge import BridgeError
from agent.ppo.buffer import Buffer
from agent.ppo.model import Policy, as_tensors, masked

RESET_TRIES = 3

log = logging.getLogger(__name__)


class Collector:
    def __init__(self, envs: list, policy: Policy, seed: int, device: str = "cpu") -> None:
        self.envs, self.policy, self.device = envs, policy, device
        self.generators = [torch.Generator().manual_seed(seed * 1000 + i) for i in range(len(envs))]
        self.obs: list = [None] * len(envs)  # None: the game's next step starts a new run
        self.masks: list = [None] * len(envs)
        self.episode_steps = [0] * len(envs)
        self._pool = ThreadPoolExecutor(len(envs), thread_name_prefix="game")

    def collect(self, buffer: Buffer) -> tuple[list[dict], np.ndarray]:
        """Fills the buffer. Returns the runs that ended, in game order, and each game's value of the observation after
        its last step (0 when that step ended a run)."""
        threads = torch.get_num_threads()
        torch.set_num_threads(1)  # one thread per game already; more would fight over the cores
        try:
            self.policy.eval()
            columns = [self._pool.submit(self._column, game, buffer) for game in range(len(self.envs))]
            results = [column.result() for column in columns]
        finally:
            torch.set_num_threads(threads)
        ended = [run for runs, _ in results for run in runs]
        return ended, np.array([value for _, value in results], np.float32)

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _evaluate(self, obs: dict, mask) -> tuple[torch.Tensor, torch.Tensor]:
        with torch.no_grad():
            logits, value = self.policy(as_tensors({key: value[None] for key, value in obs.items()}, self.device))
        if mask is None:
            return None, value[0]
        return masked(logits, torch.as_tensor(mask, device=self.device)[None])[0], value[0]

    def _column(self, game: int, buffer: Buffer) -> tuple[list[dict], float]:
        env, generator = self.envs[game], self.generators[game]
        ended: list[dict] = []
        for t in range(buffer.steps):
            if self.obs[game] is None:
                self._reset(game, ended)
            obs, mask = self.obs[game], self.masks[game]
            logits, value = self._evaluate(obs, mask)
            probs = torch.softmax(logits, -1).cpu()
            action = int(torch.multinomial(probs, 1, generator=generator))
            log_prob = float(torch.log_softmax(logits, -1)[action])
            buffer.store(t, game, obs, mask, action, log_prob, float(value))
            next_obs, reward, terminated, truncated, info = env.step(action)
            self.episode_steps[game] += 1
            bootstrap = float(self._evaluate(next_obs, None)[1]) if truncated else 0.0
            buffer.result(t, game, reward, terminated, truncated, bootstrap)
            if terminated or truncated:
                ended.append({"game": game, "seed": info["seed"], "outcome": info["outcome"], "floor": info["floor"],
                              "act": info.get("act", 0), "steps": self.episode_steps[game], "run": info.get("run")})
                self.obs[game] = None
            else:
                self.obs[game], self.masks[game] = next_obs, env.action_masks()
        last = 0.0 if self.obs[game] is None else float(self._evaluate(self.obs[game], None)[1])
        return ended, last

    def _reset(self, game: int, ended: list[dict]) -> None:
        """Starts the game's next run. A run that never starts counts as a failed run; after RESET_TRIES in a row,
        training stops."""
        env = self.envs[game]
        for attempt in range(1, RESET_TRIES + 1):
            try:
                obs, _ = env.reset()
                break
            except BridgeError as e:
                log.error("%s: the run did not start (try %d of %d): %s", env.name, attempt, RESET_TRIES, e)
                ended.append({"game": game, "seed": None, "outcome": f"failed: the run did not start: {e}",
                              "floor": 0, "act": 0, "steps": 0, "run": None})
                if attempt == RESET_TRIES:
                    raise
        self.obs[game], self.masks[game] = obs, env.action_masks()
        self.episode_steps[game] = 0
