using System;
using System.Threading;
using System.Threading.Tasks;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.AutoSlay;
using MegaCrit.Sts2.Core.AutoSlay.Handlers.Rooms;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Context;
using MegaCrit.Sts2.Core.Entities.Multiplayer;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Runs;

namespace SlayTheHuman;

/// <summary>
/// In run mode with an agent, replaces AutoSlay's combat (which buffs the player and plays cards for free) with a loop
/// that asks the agent at every decision and plays its choice the way the game's own UI does.
/// </summary>
[HarmonyPatch(typeof(CombatRoomHandler), nameof(CombatRoomHandler.HandleAsync))]
internal static class AgentCombat
{
    private static readonly TimeSpan StartTimeout = TimeSpan.FromSeconds(10);
    private static readonly TimeSpan TurnTimeout = TimeSpan.FromSeconds(60);
    private static readonly TimeSpan EndTimeout = TimeSpan.FromSeconds(30);

    private static bool Prepare() => RunMode.IsOn && Bridge.IsOn;

    private static bool Prefix(CancellationToken ct, ref Task __result)
    {
        __result = PlayAsync(ct);
        return false;
    }

    private static async Task PlayAsync(CancellationToken ct)
    {
        await Bridge.EnsureConnectedAsync(ct);
        await Until(() => CombatManager.Instance.IsInProgress, StartTimeout, "combat to start", ct);
        var player = LocalContext.GetMe(RunManager.Instance.DebugOnlyGetState())
            ?? throw new InvalidOperationException("no local player");
        while (true)
        {
            await Until(() => CanAct(player) || !CombatManager.Instance.IsInProgress, TurnTimeout,
                "the player's turn", ct);
            if (!CombatManager.Instance.IsInProgress)
            {
                break;
            }
            AutoSlayer.CurrentWatchdog?.Reset("Agent decision");
            var snapshot = CombatSnapshot.Take(player);
            snapshot.Execute(await Bridge.AskAsync(snapshot.State, snapshot.Actions, ct));
            await NextFrame();
        }
        await Until(() => !CombatManager.Instance.IsInProgress, EndTimeout, "combat to end", ct);
    }

    /// <summary>The player can act now, and nothing they did before is still resolving.</summary>
    private static bool CanAct(Player player)
    {
        var combat = CombatManager.Instance;
        var run = RunManager.Instance;
        return combat.IsInProgress && !combat.IsOverOrEnding &&
            player.PlayerCombatState?.Phase == PlayerTurnPhase.Play &&
            player.Creature.CombatState?.CurrentSide == CombatSide.Player &&
            !combat.PlayerActionsDisabled && !combat.IsPlayerReadyToEndTurn(player) && player.Creature.IsAlive &&
            run.ActionQueueSynchronizer.CombatState == ActionSynchronizerCombatState.PlayPhase &&
            run.ActionQueueSet.IsEmpty && run.ActionExecutor.CurrentlyRunningAction is null;
    }

    /// <summary>Checks the condition once per frame until it holds; throws after the timeout.</summary>
    private static async Task Until(Func<bool> condition, TimeSpan timeout, string what, CancellationToken ct)
    {
        var deadline = DateTime.UtcNow + timeout;
        while (!condition())
        {
            ct.ThrowIfCancellationRequested();
            if (DateTime.UtcNow > deadline)
            {
                throw new TimeoutException($"waited {timeout.TotalSeconds:g} seconds for {what}");
            }
            await NextFrame();
        }
    }

    private static async Task NextFrame()
    {
        var tree = (SceneTree)Engine.GetMainLoop();
        await tree.ToSignal(tree, SceneTree.SignalName.ProcessFrame);
    }
}
