#!/bin/sh
# Decompiles the installed game's sts2.dll into decompiled/ (gitignored), after checking the installed build is the one
# GAME_VERSION.md targets. Windows only (Git Bash).
#   sh tools/decompile.sh [--any-build]
# --any-build decompiles a build other than the targeted one, such as a game update not yet in GAME_VERSION.md.
# STEAM_DIR overrides the Steam folder found in the registry.
set -eu
usage='usage: sh tools/decompile.sh [--any-build]'
any_build=''
for arg; do
  case $arg in
  --any-build) any_build=1 ;;
  *) echo "$usage" >&2; exit 2 ;;
  esac
done
cd "$(dirname "$0")/.."
APPID=2868840 # Slay the Spire 2 on Steam

fail() { echo "decompile: $*" >&2; exit 1; }
# One registry value, or nothing when the key or value is missing.
reg_value() { reg query "$1" //v "$2" 2>/dev/null | tr -d '\r' | sed -n "s/^ *$2 *REG_[A-Z_]* *//p"; }

# Without long paths, the decompiler silently drops files whose paths pass 260 characters.
[ "$(reg_value 'HKLM\SYSTEM\CurrentControlSet\Control\FileSystem' LongPathsEnabled)" = 0x1 ] ||
  fail "Windows long paths are off. Turn them on in an admin PowerShell, then run again:
  New-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force"

steam=${STEAM_DIR:-$(reg_value 'HKCU\Software\Valve\Steam' SteamPath)}
[ -n "$steam" ] && [ -f "$steam/steamapps/libraryfolders.vdf" ] ||
  fail "Steam not found. Set STEAM_DIR to the Steam folder (the one holding steamapps), e.g. STEAM_DIR='C:/Program Files (x86)/Steam'"

# Every Steam library is a "path" line in libraryfolders.vdf, with backslashes escaped (C:\\Program Files (x86)\\Steam).
manifest=$(tr -d '\r' <"$steam/steamapps/libraryfolders.vdf" |
  sed -n 's/^[[:space:]]*"path"[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' | sed 's#\\\\#/#g' |
  while IFS= read -r lib; do
    if [ -f "$lib/steamapps/appmanifest_$APPID.acf" ]; then echo "$lib/steamapps/appmanifest_$APPID.acf"; break; fi
  done)
[ -n "$manifest" ] || fail "Slay the Spire 2 (app $APPID) is not installed in any library listed in $steam/steamapps/libraryfolders.vdf"

field() { tr -d '\r' <"$manifest" | sed -n "s/^[[:space:]]*\"$1\"[[:space:]]*\"\(.*\)\"[[:space:]]*$/\1/p"; }
build=$(field buildid)
data="$(dirname "$manifest")/common/$(field installdir)/data_sts2_windows_x86_64"
want=$(sed -n 's/^| Slay the Spire 2 (Steam build ID) | \([0-9]*\) |.*/\1/p' GAME_VERSION.md)
[ -n "$build" ] || fail "no buildid in $manifest"
[ -n "$want" ] || fail "no Steam build ID found in GAME_VERSION.md"
[ "$build" = "$want" ] || [ -n "$any_build" ] ||
  fail "installed build $build, but GAME_VERSION.md targets $want. Pass --any-build to decompile it anyway."
[ -f "$data/sts2.dll" ] || fail "missing $data/sts2.dll"

echo "Decompiling build $build: $data/sts2.dll"
dotnet tool restore >/dev/null
# Into decompiled.new first, so a failed run leaves the previous decompiled/ whole.
rm -rf decompiled.new
dotnet tool run ilspycmd -- --disable-updatecheck -p -r "$data" -o decompiled.new "$data/sts2.dll"
echo "$build" >decompiled.new/BUILD
rm -rf decompiled
mv decompiled.new decompiled
echo "Wrote decompiled/ ($(find decompiled -name '*.cs' | wc -l | tr -d ' ') files, build $build)"
