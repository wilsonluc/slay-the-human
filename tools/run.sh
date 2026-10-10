#!/bin/sh
# Plays one unattended run. Launches the game through Steam with no window and a raised game speed; the game's AutoSlay
# bot plays the run (a stand-in for the agent until spec 004); then prints the run's seed, outcome, last floor and time.
# Windows only (Git Bash). Needs Steam running and the mod installed (sh tools/mod.sh).
#   sh tools/run.sh [--seed=<seed>] [--time-scale=<n>] [--any-build]
# Without --seed, the game picks a new random seed. Each run's full game log is kept in runs/ (gitignored).
# STALL_SECONDS (default 120) is how long the run may go without a new log line before it counts as stuck.
set -eu
seed='' time_scale=20
options='[--seed=<seed>] [--time-scale=<n>]'
script_option() {
  case $1 in
  --seed=?*) seed=${1#--seed=} ;;
  --time-scale=?*) time_scale=${1#--time-scale=} ;;
  *) return 1 ;;
  esac
}
. "$(dirname "$0")/game.sh"
stall_seconds=${STALL_SECONDS:-120}
start_seconds=90 # for Steam to start the game

case $seed in *[!A-Za-z0-9]*) fail "a seed is letters and digits only, not '$seed'" ;; esac
case $time_scale in '' | *[!0-9.]* | *.*.*) fail "--time-scale is a positive number, not '$time_scale'" ;; esac

running() { tasklist //FI "IMAGENAME eq $1" 2>/dev/null | grep -qi "$1"; }
stop_game() { taskkill //IM SlayTheSpire2.exe //F >/dev/null 2>&1 || true; }

find_game
running steam.exe || fail "Steam is not running. Start Steam, then run again."
! running SlayTheSpire2.exe || fail "the game is already running. Close it, then run again."
[ -f "$game/mods/SlayTheHuman/SlayTheHuman.dll" ] || fail "the mod is not installed. Run sh tools/mod.sh first."

mkdir -p runs
log="runs/$(date +%Y%m%d-%H%M%S).log"
start=$(date +%s)
# Steam passes everything after the app ID to the game. Godot's own --log-file sends the whole game log to $log.
"$steam/steam.exe" -applaunch "$APPID" --slay-the-human-run ${seed:+"--slay-the-human-seed=$seed"} \
  --headless --time-scale "$time_scale" --log-file "$(cygpath -w "$PWD/$log")"

waited=0
until running SlayTheSpire2.exe; do
  waited=$((waited + 1))
  [ "$waited" -le "$start_seconds" ] || fail "Steam did not start the game within $start_seconds seconds"
  sleep 1
done

# Progress is any new mod or AutoSlay line. The run is over when the game exits; it should have logged "run end".
lines=0 changed=$(date +%s)
while running SlayTheSpire2.exe; do
  now=$(date +%s)
  current=$(grep -c -E '\[SlayTheHuman\] |\[AutoSlay\] ' "$log" 2>/dev/null || true)
  if [ "$current" != "$lines" ]; then
    lines=$current changed=$now
  elif [ $((now - changed)) -gt "$stall_seconds" ]; then
    stop_game
    fail "no progress for $stall_seconds seconds; stopped the game. Log: $log"
  fi
  sleep 1
done

end=$(grep -m1 '\[SlayTheHuman\] run end ' "$log" 2>/dev/null) ||
  fail "the game exited before the run ended$(grep -m1 -o '\[AutoSlay\] Run failed.*' "$log" | sed 's/^/: /'). Log: $log"
run_seed=$(sed -n 's/.*\[SlayTheHuman\] run start seed=\([A-Za-z0-9]*\).*/\1/p' "$log" | head -n 1)
outcome=$(echo "$end" | sed -n 's/.*outcome=\([a-z]*\).*/\1/p')
floor=$(echo "$end" | sed -n 's/.*floor=\([0-9]*\).*/\1/p')
echo "seed=$run_seed outcome=$outcome floor=$floor seconds=$(($(date +%s) - start)) log=$log"
