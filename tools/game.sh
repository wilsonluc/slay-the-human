# Sourced by the scripts in tools/ (POSIX sh, Git Bash on Windows). Parses their one option, --any-build, moves to the
# repo root, and defines find_game, which finds the installed game through Steam and checks its build against
# GAME_VERSION.md. STEAM_DIR overrides the Steam folder found in the registry.
script=$(basename "$0" .sh)
usage="usage: sh tools/$script.sh [--any-build]"
any_build=''
for arg; do
  case $arg in
  --any-build) any_build=1 ;;
  *) echo "$usage" >&2; exit 2 ;;
  esac
done
cd "$(dirname "$0")/.."
APPID=2868840 # Slay the Spire 2 on Steam

fail() { echo "$script: $*" >&2; exit 1; }
# One registry value, or nothing when the key or value is missing.
reg_value() { reg query "$1" //v "$2" 2>/dev/null | tr -d '\r' | sed -n "s/^ *$2 *REG_[A-Z_]* *//p"; }

# Sets game (the game folder), data (its data folder, holding sts2.dll) and build (the installed Steam build ID).
# Stops when the game is missing, or its build is not the one GAME_VERSION.md targets and --any-build was not given.
find_game() {
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

  build=$(manifest_field buildid)
  game="$(dirname "$manifest")/common/$(manifest_field installdir)"
  data="$game/data_sts2_windows_x86_64"
  want=$(sed -n 's/^| Slay the Spire 2 (Steam build ID) | \([0-9]*\) |.*/\1/p' GAME_VERSION.md)
  [ -n "$build" ] || fail "no buildid in $manifest"
  [ -n "$want" ] || fail "no Steam build ID found in GAME_VERSION.md"
  [ "$build" = "$want" ] || [ -n "$any_build" ] ||
    fail "installed build $build, but GAME_VERSION.md targets $want. Pass --any-build to use it anyway."
  [ -f "$data/sts2.dll" ] || fail "missing $data/sts2.dll"
}

manifest_field() { tr -d '\r' <"$manifest" | sed -n "s/^[[:space:]]*\"$1\"[[:space:]]*\"\(.*\)\"[[:space:]]*$/\1/p"; }
