# 001: Tasks

- [x] 1. Add `nuget.config` and `.config/dotnet-tools.json` pinning ilspycmd `9.1.0.7988`; `dotnet tool restore` succeeds.
- [x] 2. Ignore `decompiled/` and `decompiled.new/` in `.gitignore`.
- [x] 3. Write `tools/decompile.sh`; a run on this machine writes `decompiled/` with `BUILD` = `23811903`.
- [x] 4. Write `tools/decompile.test.sh` for long paths off, game not found, build mismatch (output untouched) and `--any-build`; it passes.
- [x] 5. Run twice and `diff -r` the outputs: identical.
- [x] 6. `grep` the hook methods in the output.
- [x] 7. Update `README.md`, `CLAUDE.md` and `GAME_VERSION.md`.
- [x] 8. Check every acceptance criterion and tick it in `spec.md`.
