# 008: Tasks

- [x] 1. Torch pinned in `pyproject.toml`; CI installs it. Tests pass locally and in CI.
- [x] 2. `encoding.OBSERVATION`, `SCHEMA_REVISION`, `schema_hash()`; `reward.REWARD_REVISION`, `definition_hash()`. `test_encoding` checks every recording against `OBSERVATION`; the hashes change when a size, segment or weight changes.
- [x] 3. `agent/tests/fake_env.py`: the environment's interface with real-shaped observations, the delayed-reward task, optional truncation and failures.
- [x] 4. `agent/ppo/model.py`: embeddings, entity networks, pooling, state, value, per-segment logits, `masked`. `test_model`: shapes, reordering, masked probability and gradient, legal-only entropy.
- [x] 5. `agent/ppo/buffer.py`: storage and GAE, minibatches. `test_buffer`: hand-worked GAE with terminated, truncated and rollout-end steps.
- [ ] 6. `agent/ppo/config.py` and `agent/ppo/rollout.py`: a thread per game, bootstrap on truncation, reset retries, ended runs returned.
- [ ] 7. `agent/ppo/train.py`: the update, metrics, the loop, step and failure budgets, interrupts. `test_train`: one update, identical runs from one seed, step budget, failure budget, three fake environments.
- [ ] 8. `agent/checkpoint.py`: run folder, `config.json`, `metrics.csv`, save, resume, hash checks, vocabulary growth; the environment's game-seed generator state. `test_checkpoint`: every field, resume equals uninterrupted, mismatches refused, growth migrated, a cut row repaired.
- [ ] 9. PPO learns the fake environment in `test_train`, under five minutes in CI.
- [ ] 10. Real game: a short training run (a few updates) on 4 games, killed and resumed; the random agent's 500-run baseline with 4 games.
- [ ] 11. Real game: the one-million-step training run, killed once and resumed; mean floor of its last 500 runs and its steps per second against the random agent's.
- [ ] 12. `README.md`, `docs/architecture.md`, `CONTEXT.md`, `ROADMAP.md` updated; every acceptance criterion checked and ticked.
