using HarmonyLib;
using MegaCrit.Sts2.Core.Logging;
using MegaCrit.Sts2.Core.Nodes;
using MegaCrit.Sts2.Core.Runs;

namespace SlayTheHuman;

/// <summary>
/// In run mode, logs one "room" line per room entered and a "run end" line per run, and sends the agent run_end. In each
/// run's first room it checks the run has every unlock (<see cref="RunProfile"/>): a patch the JIT inlined away would
/// otherwise go unnoticed.
/// </summary>
[HarmonyPatch(typeof(RunManager), nameof(RunManager.OnEnded))]
internal static class RunLog
{
    private static bool _ended;
    private static bool _checked;

    private static bool Prepare() => RunMode.IsOn;

    /// <summary>Once per game process: RunManager lives for the whole process.</summary>
    public static void Attach()
    {
        RunManager.Instance.RoomEntered += () =>
        {
            var state = RunManager.Instance.DebugOnlyGetState();
            if (state?.CurrentRoom is not { } room)
            {
                return;
            }
            Log.Info($"[{ModEntry.Id}] room act={state.CurrentActIndex + 1} floor={state.TotalFloor} type={room.RoomType}");
            if (_checked)
            {
                return;
            }
            _checked = true;
            if (RunProfile.HasAllUnlocks(state))
            {
                Log.Info($"[{ModEntry.Id}] unlocks=all");
            }
            else
            {
                Log.Error($"[{ModEntry.Id}] run error: the run does not have every unlock, so its content depends on the profile");
                NGame.Instance?.GetTree().Quit(1);
            }
        };
    }

    /// <summary>At each run's start.</summary>
    public static void Reset()
    {
        _ended = false;
        _checked = false;
    }

    private static void Postfix(RunManager __instance, bool isVictory)
    {
        if (_ended)
        {
            return;
        }
        _ended = true;
        var floor = __instance.DebugOnlyGetState()?.TotalFloor ?? 0;
        Log.Info($"[{ModEntry.Id}] run end outcome={(isVictory ? "win" : "loss")} floor={floor}");
        Bridge.SendRunEnd(isVictory, floor, RunMode.Seed);
    }
}
