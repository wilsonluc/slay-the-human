#!/bin/sh
# Decompiles the installed game's sts2.dll into decompiled/ (gitignored), after checking the installed build is the one
# GAME_VERSION.md targets. Windows only (Git Bash).
#   sh tools/decompile.sh [--any-build]
# --any-build decompiles a build other than the targeted one, such as a game update not yet in GAME_VERSION.md.
# STEAM_DIR overrides the Steam folder found in the registry.
set -eu
. "$(dirname "$0")/game.sh"

# Without long paths, the decompiler silently drops files whose paths pass 260 characters.
[ "$(reg_value 'HKLM\SYSTEM\CurrentControlSet\Control\FileSystem' LongPathsEnabled)" = 0x1 ] ||
  fail "Windows long paths are off. Turn them on in an admin PowerShell, then run again:
  New-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force"

find_game
echo "Decompiling build $build: $data/sts2.dll"
dotnet tool restore >/dev/null
# Into decompiled.new first, so a failed run leaves the previous decompiled/ whole.
rm -rf decompiled.new
dotnet tool run ilspycmd -- --disable-updatecheck -p -r "$data" -o decompiled.new "$data/sts2.dll"
echo "$build" >decompiled.new/BUILD
rm -rf decompiled
mv decompiled.new decompiled
echo "Wrote decompiled/ ($(find decompiled -name '*.cs' | wc -l | tr -d ' ') files, build $build)"
