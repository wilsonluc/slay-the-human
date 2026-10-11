using HarmonyLib;
using MegaCrit.Sts2.Core.Nodes.Vfx.Utilities;

namespace SlayTheHuman;

/// <summary>
/// In run mode, a big hit does not freeze the game for a moment (hit stop). The effect slows the engine's time scale and
/// then sets it back to 1, not to what it was, so after the first big hit the game ran at normal speed instead of the
/// run's --time-scale, about three times slower. It is only a visual.
/// </summary>
[HarmonyPatch(typeof(NHitStop), nameof(NHitStop.DoHitStop))]
internal static class NoHitStop
{
    private static bool Prepare() => RunMode.IsOn;

    private static bool Prefix() => false;
}
