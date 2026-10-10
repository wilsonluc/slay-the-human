# 004: Tasks

- [ ] 1. Write `docs/protocol.md`.
- [ ] 2. Write `agent/bridge.py` and its tests against a fake mod: handshake, version mismatch, decision exchange, bad index, disconnect, timeout.
- [ ] 3. Write `agent/random_agent.py`; same seed, same choices.
- [ ] 4. Write the mod's bridge, snapshot and combat loop; it builds.
- [ ] 5. Extend `tools/run.sh` and `tools/test.sh`; tests pass.
- [ ] 6. Run a full game with the random agent; check the state, honest energy, no buffs, decisions per second.
- [ ] 7. Run the same seeds twice; compare.
- [ ] 8. Check the error paths in the game: bad index, version mismatch; and a normal launch.
- [ ] 9. Update `README.md`.
- [ ] 10. Check every acceptance criterion and tick it in `spec.md`.
