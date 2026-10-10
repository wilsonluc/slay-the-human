using System.Linq;
using HarmonyLib;
using MegaCrit.Sts2.Core.Logging;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Nodes;
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
        var characters = ModelDb.AllCharacters.Select(character => character.Id.Entry).ToList();
        if (!characters.Contains(RunMode.Character))
        {
            // Fail before AutoSlay starts, so the reason is not buried under its timeout.
            Log.Error($"[{ModEntry.Id}] run error: no character {RunMode.Character}; the game has " +
                string.Join(", ", characters));
            NGame.Instance?.Quit();
            return;
        }
        RunLog.Attach();
        new AutoSlayer().Start(RunMode.Seed);
    }
}
