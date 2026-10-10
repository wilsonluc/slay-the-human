#!/bin/sh
# Builds the mod in mod/ against the installed game and installs it into the game's mods folder, after checking the
# installed build is the one GAME_VERSION.md targets. Windows only (Git Bash). Close the game first: it loads mods only
# at startup, and Windows locks a loaded DLL.
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
dest="$game/mods/$id"
rm -rf "$dest"
mkdir -p "$dest"
cp "mod/$id.json" "$out/$id.dll" "$dest/"
echo "Installed $dest. Start the game to load it."
