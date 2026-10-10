using HarmonyLib;
using MegaCrit.Sts2.Core.Logging;
using MegaCrit.Sts2.Core.Runs;

namespace SlayTheHuman;

/// <summary>
/// In run mode, logs one "room" line per room entered and a "run end" line per run, and sends the agent run_end.
/// </summary>
[HarmonyPatch(typeof(RunManager), nameof(RunManager.OnEnded))]
internal static class RunLog
{
    private static bool _ended;

    private static bool Prepare() => RunMode.IsOn;

    /// <summary>Once per game process: RunManager lives for the whole process.</summary>
    public static void Attach()
    {
        RunManager.Instance.RoomEntered += () =>
        {
            var state = RunManager.Instance.DebugOnlyGetState();
            if (state?.CurrentRoom is { } room)
            {
                Log.Info($"[{ModEntry.Id}] room act={state.CurrentActIndex + 1} floor={state.TotalFloor} type={room.RoomType}");
            }
        };
    }

    /// <summary>At each run's start.</summary>
    public static void Reset() => _ended = false;

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
