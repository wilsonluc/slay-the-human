# 002: Tasks

- [ ] 1. Move the game lookup and build check into `tools/game.sh`; `tools/decompile.sh` sources it, and its checks still pass.
- [ ] 2. Write the mod project, manifest, initializer and main menu patch; it builds against the game's data folder with no game files in the output.
- [ ] 3. Write `tools/mod.sh`; it installs only the manifest and the DLL into `<game>/mods/SlayTheHuman/`.
- [ ] 4. Rename the test to `tools/test.sh` and add the `tools/mod.sh` build mismatch check; it passes.
- [ ] 5. Launch the game, accept the mods warning, and check `godot.log` for the load and patch lines.
- [ ] 6. Check a failing patch stops the mod, then remove it.
- [ ] 7. Update `README.md` and `GAME_VERSION.md`.
- [ ] 8. Check every acceptance criterion and tick it in `spec.md`.
