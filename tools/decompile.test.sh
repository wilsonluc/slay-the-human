#!/bin/sh
# Checks how tools/decompile.sh refuses to run, with a fake registry and a fake Steam install. Needs no game.
#   sh tools/decompile.test.sh
set -u
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
failed=0

# A copy of the repo, so no run touches the real decompiled/.
repo="$tmp/repo"
mkdir -p "$repo/tools" "$tmp/bin" "$tmp/empty"
cp "$root/tools/decompile.sh" "$repo/tools/"
cp -r "$root/GAME_VERSION.md" "$root/nuget.config" "$root/.config" "$repo/"
want=$(sed -n 's/^| Slay the Spire 2 (Steam build ID) | \([0-9]*\) |.*/\1/p' "$repo/GAME_VERSION.md")

# A fake reg answering only LongPathsEnabled, from $LONG_PATHS, in reg's CRLF output format.
cat >"$tmp/bin/reg" <<'EOF'
#!/bin/sh
case $2 in
*FileSystem) printf '\r\n    LongPathsEnabled    REG_DWORD    %s\r\n\r\n' "$LONG_PATHS" ;;
*) exit 1 ;;
esac
EOF

# A Steam install with two libraries: its own folder (no game) and a second one holding build 1 of the game.
steam="$tmp/steam" lib="$tmp/library"
mkdir -p "$steam/steamapps" "$lib/steamapps/common/Slay the Spire 2/data_sts2_windows_x86_64"
: >"$lib/steamapps/common/Slay the Spire 2/data_sts2_windows_x86_64/sts2.dll"
vdf_path() { cygpath -w "$1" | sed 's#\\#\\\\#g'; } # as Steam writes it, backslashes escaped
printf '"libraryfolders"\r\n{\r\n\t"0"\r\n\t{\r\n\t\t"path"\t\t"%s"\r\n\t}\r\n\t"1"\r\n\t{\r\n\t\t"path"\t\t"%s"\r\n\t}\r\n}\r\n' \
  "$(vdf_path "$steam")" "$(vdf_path "$lib")" >"$steam/steamapps/libraryfolders.vdf"
printf '"AppState"\r\n{\r\n\t"appid"\t\t"2868840"\r\n\t"installdir"\t\t"Slay the Spire 2"\r\n\t"buildid"\t\t"1"\r\n}\r\n' \
  >"$lib/steamapps/appmanifest_2868840.acf"
mkdir "$repo/decompiled"
echo old >"$repo/decompiled/BUILD"

# run <long paths> <steam dir> [args]: sets $out and $code.
run() {
  long=$1 dir=$2
  shift 2
  out=$(LONG_PATHS=$long STEAM_DIR=$dir PATH="$tmp/bin:$PATH" sh "$repo/tools/decompile.sh" "$@" 2>&1)
  code=$?
}
check() { # check <name> <condition...>
  name=$1
  shift
  if "$@"; then echo "ok   $name"; else echo "FAIL $name (exit $code): $out"; failed=1; fi
}
has() { case $out in *"$1"*) return 0 ;; esac; return 1; }
untouched() { [ "$(cat "$repo/decompiled/BUILD")" = old ] && [ ! -e "$repo/decompiled.new/BUILD" ]; }

run 0x0 "$steam"
check 'long paths off' eval '[ $code = 1 ] && has "long paths are off" && has LongPathsEnabled'

run 0x1 "$tmp/empty"
check 'Steam not found' eval '[ $code = 1 ] && has "Steam not found" && has STEAM_DIR'

run 0x1 "$steam"
check 'build mismatch' eval '[ $code = 1 ] && has "installed build 1" && has "targets $want" && has --any-build && untouched'

run 0x1 "$steam" --any-build
check '--any-build passes the check' eval 'has "Decompiling build 1" && ! has "targets"'
check 'failed decompile keeps decompiled/' untouched

run 0x1 "$steam" --bogus
check 'unknown flag' eval '[ $code = 2 ] && has usage'

exit $failed
