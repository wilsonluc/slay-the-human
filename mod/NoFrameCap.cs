using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.Logging;
using MegaCrit.Sts2.Core.Nodes;

namespace SlayTheHuman;

/// <summary>
/// In run mode, the game runs as many frames a second as the machine allows. At startup the game caps the frame rate
/// from the player's settings (60 by default), with no window as well, and a decision takes several frames. The
/// background limit never applies: a game with no window gets no focus events.
/// </summary>
[HarmonyPatch(typeof(NGame), "InitializeGraphicsPreferences")]
internal static class NoFrameCap
{
    private static bool Prepare() => RunMode.IsOn;

    private static void Postfix()
    {
        Engine.MaxFps = 0;
        Log.Info($"[{ModEntry.Id}] frame cap off (max fps {Engine.MaxFps})");
    }
}
