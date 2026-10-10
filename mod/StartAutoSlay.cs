using HarmonyLib;
using MegaCrit.Sts2.Core.AutoSlay;
using MegaCrit.Sts2.Core.Nodes.Screens.MainMenu;

namespace SlayTheHuman;

/// <summary>
/// In run mode, starts the game's AutoSlay bot once the main menu is ready. AutoSlay plays the run as a stand-in for
/// the agent and quits the game when the run ends.
/// </summary>
[HarmonyPatch(typeof(NMainMenu), nameof(NMainMenu._Ready))]
internal static class StartAutoSlay
{
    private static bool _started;

    private static bool Prepare() => RunMode.IsOn;

    private static void Postfix()
    {
        // The main menu comes back after the run ends; only the first one starts a run.
        if (_started)
        {
            return;
        }
        _started = true;
        RunLog.Attach();
        new AutoSlayer().Start(RunMode.Seed);
    }
}
