using HarmonyLib;
using MegaCrit.Sts2.Core.Multiplayer.Game.Lobby;
using MegaCrit.Sts2.Core.Nodes;

namespace SlayTheHuman;

/// <summary>
/// In run mode, gives the run the run-mode seed. The lobby derives the run's acts and seed from the seed passed here;
/// AutoSlay's own seed only drives its choices.
/// </summary>
[HarmonyPatch(typeof(StartRunLobby), "BeginRunLocally")]
internal static class SeedRun
{
    private static bool Prepare() => RunMode.IsOn;

    private static void Prefix(ref string seed) => seed = RunMode.Seed;
}

/// <summary>In run mode, starts the run without saving, so runs leave no save files or run history behind.</summary>
[HarmonyPatch(typeof(NGame), nameof(NGame.StartNewSingleplayerRun))]
internal static class NoSave
{
    private static bool Prepare() => RunMode.IsOn;

    private static void Prefix(ref bool shouldSave) => shouldSave = false;
}
