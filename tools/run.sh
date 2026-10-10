#!/bin/sh
# Plays one unattended run. Starts the random Python agent (agent/random_agent.py), then launches the game through
# Steam with no window and a raised game speed. The agent makes every combat decision over the bridge
# (docs/protocol.md); the game's AutoSlay bot still decides outside combat. Prints the run's seed, outcome, last floor
# and time, and the agent's seed and decision count.
# Windows only (Git Bash). Needs Steam running, the mod installed (sh tools/mod.sh) and Python 3.13 (PYTHON overrides
# the python command).
#   sh tools/run.sh [--seed=<seed>] [--agent-seed=<n>] [--time-scale=<n>] [--any-build]
# Without --seed, the game picks a new random seed; without --agent-seed, the agent does. Each run's full game log and
# the agent's output and its trace of every decision are kept in runs/ (gitignored).
# STALL_SECONDS (default 120) is how long the run may go without a new log line before it counts as stuck.
set -eu
seed='' agent_seed='' time_scale=20
options='[--seed=<seed>] [--agent-seed=<n>] [--time-scale=<n>]'
script_option() {
  case $1 in
  --seed=?*) seed=${1#--seed=} ;;
  --agent-seed=?*) agent_seed=${1#--agent-seed=} ;;
  --time-scale=?*) time_scale=${1#--time-scale=} ;;
  *) return 1 ;;
  esac
}
. "$(dirname "$0")/game.sh"
stall_seconds=${STALL_SECONDS:-120}
start_seconds=90      # for Steam to start the game
agent_start_seconds=10 # for the agent to start listening
python=${PYTHON:-python}

case $seed in *[!A-Za-z0-9]*) fail "a seed is letters and digits only, not '$seed'" ;; esac
case $agent_seed in *[!0-9]*) fail "--agent-seed is a whole number, not '$agent_seed'" ;; esac
case $time_scale in '' | *[!0-9.]* | *.*.*) fail "--time-scale is a positive number, not '$time_scale'" ;; esac

running() { tasklist //FI "IMAGENAME eq $1" 2>/dev/null | grep -qi "$1"; }
stop_game() { taskkill //IM SlayTheSpire2.exe //F >/dev/null 2>&1 || true; }
agent_running() { kill -0 "$agent_pid" 2>/dev/null; }
agent_error() { grep -m1 '^agent: ' "$agent_log" 2>/dev/null || echo "agent: exited without saying why"; }

find_game
running steam.exe || fail "Steam is not running. Start Steam, then run again."
! running SlayTheSpire2.exe || fail "the game is already running. Close it, then run again."
[ -f "$game/mods/SlayTheHuman/SlayTheHuman.dll" ] || fail "the mod is not installed. Run sh tools/mod.sh first."

mkdir -p runs
name="runs/$(date +%Y%m%d-%H%M%S)"
log="$name.log" agent_log="$name.agent.log" trace="$name.trace.jsonl"
start=$(date +%s)

# The agent listens first and prints the port it chose; the game connects to it.
"$python" -u agent/random_agent.py ${agent_seed:+--seed "$agent_seed"} --trace "$trace" >"$agent_log" 2>&1 &
agent_pid=$!
trap 'kill "$agent_pid" 2>/dev/null || true' EXIT
waited=0 port=''
until port=$(sed -n 's/^port=\([0-9]*\)$/\1/p' "$agent_log") && [ -n "$port" ]; do
  agent_running || fail "the agent did not start: $(agent_error). Output: $agent_log"
  waited=$((waited + 1))
  [ "$waited" -le "$agent_start_seconds" ] || fail "the agent did not start listening within $agent_start_seconds seconds"
  sleep 1
done

# Steam passes everything after the app ID to the game. Godot's own --log-file sends the whole game log to $log.
"$steam/steam.exe" -applaunch "$APPID" --slay-the-human-run ${seed:+"--slay-the-human-seed=$seed"} \
  --slay-the-human-agent-port="$port" --headless --time-scale "$time_scale" --log-file "$(cygpath -w "$PWD/$log")"

waited=0
until running SlayTheSpire2.exe; do
  waited=$((waited + 1))
  [ "$waited" -le "$start_seconds" ] || fail "Steam did not start the game within $start_seconds seconds"
  sleep 1
done

# Progress is any new mod or AutoSlay line. The run is over when the game exits; it should have logged "run end".
# An agent that fails first stops the run; one that finished (it got run_end) leaves the game to exit.
lines=0 changed=$(date +%s) agent_status=''
while running SlayTheSpire2.exe; do
  now=$(date +%s)
  current=$(grep -c -E '\[SlayTheHuman\] |\[AutoSlay\] ' "$log" 2>/dev/null || true)
  if [ "$current" != "$lines" ]; then
    lines=$current changed=$now
  elif [ $((now - changed)) -gt "$stall_seconds" ]; then
    stop_game
    fail "no progress for $stall_seconds seconds; stopped the game. Log: $log"
  fi
  if [ -z "$agent_status" ] && ! agent_running; then
    wait "$agent_pid" && agent_status=0 || agent_status=$?
    [ "$agent_status" = 0 ] || { stop_game; fail "$(agent_error); stopped the game. Log: $log"; }
  fi
  sleep 1
done

end=$(grep -m1 '\[SlayTheHuman\] run end ' "$log" 2>/dev/null) ||
  fail "the game exited before the run ended$(grep -m1 -o '\[AutoSlay\] Run failed.*' "$log" | sed 's/^/: /'). Log: $log"
if [ -z "$agent_status" ]; then
  waited=0
  while agent_running; do
    waited=$((waited + 1))
    [ "$waited" -le "$agent_start_seconds" ] || fail "the agent did not finish after the run ended. Output: $agent_log"
    sleep 1
  done
  wait "$agent_pid" || fail "$(agent_error). Output: $agent_log"
fi
agent_summary=$(grep -m1 '^agent_seed=' "$agent_log") || fail "the agent printed no summary. Output: $agent_log"
run_seed=$(sed -n 's/.*\[SlayTheHuman\] run start seed=\([A-Za-z0-9]*\).*/\1/p' "$log" | head -n 1)
outcome=$(echo "$end" | sed -n 's/.*outcome=\([a-z]*\).*/\1/p')
floor=$(echo "$end" | sed -n 's/.*floor=\([0-9]*\).*/\1/p')
echo "seed=$run_seed outcome=$outcome floor=$floor seconds=$(($(date +%s) - start)) $agent_summary log=$log"
