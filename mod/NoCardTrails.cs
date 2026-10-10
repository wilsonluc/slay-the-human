using HarmonyLib;
using MegaCrit.Sts2.Core.Nodes.Vfx;

namespace SlayTheHuman;

/// <summary>
/// In run mode, the trail behind a flying card draws nothing. It fills the gap since its last point with a point every
/// 48 pixels, in a float loop: when the card's position jumps far enough (as it sometimes does at high time scales), the
/// loop's step drowns in float rounding, and it adds points forever on the main thread until memory runs out. The trail
/// is only a visual.
/// </summary>
[HarmonyPatch(typeof(NCardTrail), nameof(NCardTrail._Process))]
internal static class NoCardTrails
{
    private static bool Prepare() => RunMode.IsOn;

    private static bool Prefix() => false;
}
