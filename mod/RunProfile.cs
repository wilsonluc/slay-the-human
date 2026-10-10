using System.Linq;
using System.Reflection;
using HarmonyLib;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Multiplayer.Game.Lobby;
using MegaCrit.Sts2.Core.Multiplayer.Replay;
using MegaCrit.Sts2.Core.Runs;
using MegaCrit.Sts2.Core.Saves;
using MegaCrit.Sts2.Core.Saves.Managers;
using MegaCrit.Sts2.Core.Saves.Validation;
using MegaCrit.Sts2.Core.Unlocks;

namespace SlayTheHuman;

/// <summary>
/// In run mode, a seed's content depends neither on the profile the game loaded nor on earlier runs in the process. The
/// game builds a run from the profile's unlocks and also reads the profile directly during a run (undiscovered acts are
/// forced, a profile's first run is scripted, a few events and one relic read its stats and ID), and it updates the
/// profile in memory after every combat won. So each run starts from one fixed profile, with everything unlocked, and
/// nothing is ever written back.
/// </summary>
internal static class RunProfile
{
    /// <summary>The fixed profile's ID; the game would otherwise draw a random one, which a relic reads.</summary>
    private const string ProfileId = "slayhuman";

    /// <summary>Whether the lobby took the run's unlocks from <see cref="AllUnlocksInLobby"/> this run.</summary>
    public static bool LobbyPatched { get; set; }

    /// <summary>
    /// At each run's start: the game's in-memory profile becomes the default one with a fixed ID, every act discovered
    /// and one recorded loss, so no first-run scripting applies.
    /// </summary>
    public static void Reset()
    {
        var progress = ProgressState.FromSerializable(new SerializableProgress { UniqueId = ProfileId }, new DeserializationContext());
        foreach (var act in ModelDb.Acts)
        {
            progress.MarkActAsSeen(act.Id);
        }
        progress.GetOrCreateCharacterStats(ModelDb.AllCharacters.First().Id).TotalLosses = 1;
        SaveManager.Instance.Progress = progress;
        LobbyPatched = false;
    }

    /// <summary>Whether the run's player and shared unlocks are everything, as the patches below make them.</summary>
    public static bool HasAllUnlocks(RunState state) =>
        LobbyPatched && state.Players.All(player => ReferenceEquals(player.UnlockState, UnlockState.all)) &&
        state.UnlockState.NumberOfRuns == UnlockState.all.NumberOfRuns;
}

/// <summary>In run mode, the lobby (which picks the run's acts) gets every unlock, as the game's Daily mode does.</summary>
[HarmonyPatch(typeof(StartRunLobby), nameof(StartRunLobby.AddLocalHostPlayer))]
internal static class AllUnlocksInLobby
{
    private static bool Prepare() => RunMode.IsOn;

    private static void Prefix(ref UnlockState unlocks)
    {
        unlocks = UnlockState.all;
        RunProfile.LobbyPatched = true;
    }
}

/// <summary>
/// In run mode, a new player gets every unlock. A singleplayer run builds its player from the profile, not from the
/// lobby. The constructor is patched rather than the small methods that pass the unlocks along, which the JIT may inline.
/// </summary>
[HarmonyPatch]
internal static class AllUnlocksForPlayer
{
    private static bool Prepare() => RunMode.IsOn;

    private static MethodBase TargetMethod() =>
        AccessTools.GetDeclaredConstructors(typeof(Player))
            .Single(constructor => constructor.GetParameters().Any(parameter => parameter.ParameterType == typeof(UnlockState)));

    private static void Prefix(ref UnlockState unlockState) => unlockState = UnlockState.all;
}

/// <summary>In run mode, the game never writes the profile, including the save after every combat won.</summary>
[HarmonyPatch(typeof(ProgressSaveManager), nameof(ProgressSaveManager.SaveProgress))]
internal static class NoProgressWrites
{
    private static bool Prepare() => RunMode.IsOn;

    private static bool Prefix() => false;
}

/// <summary>In run mode, no combat replay is written into the profile folder. Recording still stops when asked.</summary>
[HarmonyPatch(typeof(CombatReplayWriter), nameof(CombatReplayWriter.WriteReplay))]
internal static class NoReplayWrites
{
    private static bool Prepare() => RunMode.IsOn;

    private static bool Prefix(CombatReplayWriter __instance, bool stopRecording)
    {
        if (stopRecording)
        {
            __instance.StopRecording();
        }
        return false;
    }
}
