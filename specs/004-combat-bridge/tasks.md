# 004: Tasks

- [x] 1. Write `docs/protocol.md`.
- [x] 2. Write `agent/bridge.py` and its tests against a fake mod: handshake, version mismatch, decision exchange, disconnect, connect timeout, bad messages.
- [x] 3. Write `agent/random_agent.py`; same seed, same choices.
- [x] 4. Write the mod's bridge, snapshot and combat loop; it builds.
- [x] 5. Extend `tools/run.sh` and `tools/test.sh`; tests pass.
- [x] 6. Run a full game with the random agent; check the state, honest energy, no buffs, decisions per second.
- [x] 7. Run the same seeds twice; compare.
- [x] 8. Check the error paths in the game: bad index, no answer in time, version mismatch; and a normal launch.
- [x] 9. Update `README.md`.
- [x] 10. Check every acceptance criterion and tick it in `spec.md`.
