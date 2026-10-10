#!/bin/sh
# Builds the mod in mod/ against the installed game, after checking its build is the one GAME_VERSION.md targets, and
# installs it into the game's mods folder and into the build's game copy (tools/copy-game.sh) when there is one.
# Windows only (Git Bash). Close the game first: it loads mods only at startup, and Windows locks a loaded DLL.
#   sh tools/mod.sh [--any-build]
# --any-build installs into a build other than the targeted one, such as a game update not yet in GAME_VERSION.md.
# STEAM_DIR overrides the Steam folder found in the registry.
set -eu
. "$(dirname "$0")/game.sh"

find_game
id=SlayTheHuman
out=mod/bin/Release/net9.0
echo "Building $id for build $build"
dotnet build mod -c Release --nologo -v quiet -p:GameDataDir="$data"
copy="${STH_GAMES_DIR:-games}/$build"
for folder in "$game" "$copy"; do
  [ -d "$folder" ] || continue
  dest="$folder/mods/$id"
  rm -rf "$dest"
  mkdir -p "$dest"
  cp "mod/$id.json" "$out/$id.dll" "$dest/"
  echo "Installed $dest."
done
echo "Start the game to load it."
