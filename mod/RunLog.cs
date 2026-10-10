using HarmonyLib;
using MegaCrit.Sts2.Core.Logging;
using MegaCrit.Sts2.Core.Runs;

namespace SlayTheHuman;

/// <summary>
/// In run mode, logs the lines tools/run.sh reads: "run start", one "room" per room entered, and "run end".
/// </summary>
[HarmonyPatch(typeof(RunManager), nameof(RunManager.OnEnded))]
internal static class RunLog
{
    private static bool _ended;

    private static bool Prepare() => RunMode.IsOn;

    public static void Attach()
    {
        Log.Info($"[{ModEntry.Id}] run start seed={RunMode.Seed}");
        RunManager.Instance.RoomEntered += () =>
        {
            var state = RunManager.Instance.DebugOnlyGetState();
            if (state?.CurrentRoom is { } room)
            {
                Log.Info($"[{ModEntry.Id}] room act={state.CurrentActIndex + 1} floor={state.TotalFloor} type={room.RoomType}");
            }
        };
    }

    private static void Postfix(RunManager __instance, bool isVictory)
    {
        if (_ended)
        {
            return;
        }
        _ended = true;
        var floor = __instance.DebugOnlyGetState()?.TotalFloor;
        Log.Info($"[{ModEntry.Id}] run end outcome={(isVictory ? "win" : "loss")} floor={floor}");
    }
}
