using System;
using System.Threading;
using System.Threading.Tasks;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.AutoSlay;
using MegaCrit.Sts2.Core.AutoSlay.Handlers.Screens;
using MegaCrit.Sts2.Core.Logging;
using MegaCrit.Sts2.Core.Nodes.Screens;
using MegaCrit.Sts2.Core.Nodes.Screens.GameOverScreen;
using MegaCrit.Sts2.Core.Nodes.Screens.Map;
using MegaCrit.Sts2.Core.Nodes.Screens.Overlays;
using MegaCrit.Sts2.Core.Random;
using MegaCrit.Sts2.Core.Runs;

namespace SlayTheHuman;

/// <summary>
/// Ends a lost run promptly and cleanly. AutoSlay only expects wins: after a combat it waits for a rewards screen,
/// and when the player has died that wait times out and fails the run. Here a death goes through the game over screen
/// to the main menu, then a <see cref="RunOverSignal"/> ends AutoSlay's run loop the way a win does.
/// </summary>
[HarmonyPatch(typeof(AutoSlayer), "WaitForRewardsScreenAsync")]
internal static class RunOver
{
    private static readonly TimeSpan RewardsTimeout = TimeSpan.FromSeconds(10);
    private static readonly TimeSpan ScreenTimeout = TimeSpan.FromSeconds(30);

    private static bool Prepare() => RunMode.WithAgent;

    private static bool Prefix(CancellationToken ct, ref Task __result)
    {
        __result = WaitForRewardsAsync(ct);
        return false;
    }

    private static async Task WaitForRewardsAsync(CancellationToken ct)
    {
        await Wait.Until(() => NOverlayStack.Instance?.Peek() is NRewardsScreen || (NMapScreen.Instance?.IsOpen ?? false) ||
            IsOver, RewardsTimeout, "the rewards screen after combat", ct);
        await EndIfLostAsync(ct);
    }

    /// <summary>
    /// The run has ended in a loss (all players dead, or the game over screen up, as after giving up the run), or has
    /// already been cleaned up after one.
    /// </summary>
    public static bool IsOver => RunManager.Instance.IsGameOver || !RunManager.Instance.IsInProgress ||
        NOverlayStack.Instance?.Peek() is NGameOverScreen;

    /// <summary>When the run is lost, goes through the game over screen to the main menu and ends AutoSlay's loop.</summary>
    public static async Task EndIfLostAsync(CancellationToken ct)
    {
        if (!IsOver)
        {
            return;
        }
        var root = ((SceneTree)Engine.GetMainLoop()).Root;
        bool AtMainMenu() => root.GetNodeOrNull<Control>("/root/Game/RootSceneContainer/MainMenu")?.IsVisibleInTree() ?? false;
        await Wait.Until(() => NOverlayStack.Instance?.Peek() is NGameOverScreen || AtMainMenu(), ScreenTimeout,
            "the game over screen", ct);
        if (!AtMainMenu())
        {
            // No choice here: AutoSlay's game over handler clicks continue, then back to the main menu.
            await new GameOverScreenHandler().HandleAsync(new Rng(), ct);
        }
        await Wait.Until(AtMainMenu, ScreenTimeout, "the main menu after the game over screen", ct);
        throw new RunOverSignal();
    }
}

/// <summary>Ends AutoSlay's run loop after a loss, so AutoSlay finishes the run as it finishes a win.</summary>
[HarmonyPatch(typeof(AutoSlayer), "PlayRunAsync")]
internal static class CatchRunOver
{
    private static bool Prepare() => RunMode.WithAgent;

    private static void Postfix(ref Task __result) => __result = EndQuietlyAsync(__result);

    private static async Task EndQuietlyAsync(Task run)
    {
        try
        {
            await run;
        }
        catch (RunOverSignal)
        {
            Log.Info($"[{ModEntry.Id}] run over; back at the main menu");
        }
    }
}

/// <summary>Not an error: the run is over (lost, given up or won) and has been wound down.</summary>
internal sealed class RunOverSignal() : Exception("the run is over");
