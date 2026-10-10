#!/bin/sh
# Copies the installed game, after checking its build is the one GAME_VERSION.md targets, to games/<build>/ (STH_GAMES_DIR
# overrides the folder holding the copies), and prints the copy's hash for GAME_VERSION.md. Training and evaluation run
# this copy, which Steam never updates. The mods folder is left out; tools/mod.sh installs the mod into the copy.
#   sh tools/copy-game.sh [--any-build]
# STEAM_DIR overrides the Steam folder found in the registry.
set -eu
. "$(dirname "$0")/game.sh"

find_game
dest="${STH_GAMES_DIR:-games}/$build"
[ ! -e "$dest" ] || fail "$dest already exists. Remove it first to copy again."
mkdir -p "$dest"
echo "Copying build $build to $dest"
for entry in "$game"/*; do
  [ "$(basename "$entry")" = mods ] || cp -R "$entry" "$dest/"
done
echo "Game copy (hash): $(${PYTHON:-python} -m agent.env.games hash "$dest")"
