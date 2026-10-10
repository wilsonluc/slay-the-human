using HarmonyLib;
using MegaCrit.Sts2.Core.Logging;
using MegaCrit.Sts2.Core.Nodes.Screens.MainMenu;

namespace SlayTheHuman;

/// <summary>Logs when the main menu is ready: proof that the mod's patches run.</summary>
[HarmonyPatch(typeof(NMainMenu), nameof(NMainMenu._Ready))]
internal static class MainMenuReady
{
    private static void Postfix() => Log.Info($"[{ModEntry.Id}] main menu ready");
}
