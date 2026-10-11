using System.Threading.Tasks;
using HarmonyLib;
using MegaCrit.Sts2.Core.Models.Events;

namespace SlayTheHuman;

/// <summary>
/// In run mode, the PunchOff event's two constructs do not punch each other while the event waits. That animation loops
/// until an option is chosen, waiting between punches with Cmd.Wait, which returns at once while AutoSlay runs; the loop
/// then never yields, and the game's main thread spins forever. It is only a visual.
/// </summary>
[HarmonyPatch(typeof(PunchOff), "PunchEachOther")]
internal static class NoPunchOffLoop
{
    private static bool Prepare() => RunMode.IsOn;

    private static bool Prefix(ref Task __result)
    {
        __result = Task.CompletedTask;
        return false;
    }
}
