using System;
using System.Threading;
using System.Threading.Tasks;
using HarmonyLib;
using MegaCrit.Sts2.Core.AutoSlay;
using MegaCrit.Sts2.Core.AutoSlay.Handlers.Rooms;
using MegaCrit.Sts2.Core.Combat;
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

    private static bool Prepare() => RunMode.WithAgent;

    private static bool Prefix(CancellationToken ct, ref Task __result)
    {
        __result = PlayAsync(ct);
        return false;
    }

    public static async Task PlayAsync(CancellationToken ct)
    {
        await Wait.Until(() => CombatManager.Instance.IsInProgress, StartTimeout, "combat to start", ct);
        var player = Decision.Me();
        while (true)
        {
            await Wait.Until(() => CanAct(player) || !CombatManager.Instance.IsInProgress, TurnTimeout,
                "the player's turn", ct);
            if (!CombatManager.Instance.IsInProgress)
            {
                break;
            }
            AutoSlayer.CurrentWatchdog?.Reset("Agent decision");
            await CombatSnapshot.Take(player).RunAsync(ct);
            await Wait.NextFrame();
        }
        await Wait.Until(() => !CombatManager.Instance.IsInProgress, EndTimeout, "combat to end", ct);
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
}

/// <summary>
/// In run mode with an agent, plays combats that events start like any other combat. AutoSlay would buff the player
/// and kill every enemy.
/// </summary>
[HarmonyPatch(typeof(EventRoomHandler), "HandleEventCombat")]
internal static class AgentEventCombat
{
    private static bool Prepare() => RunMode.WithAgent;

    private static bool Prefix(CancellationToken ct, ref Task __result)
    {
        MegaCrit.Sts2.Core.Logging.Log.Info($"[{ModEntry.Id}] event combat");
        __result = AgentCombat.PlayAsync(ct);
        return false;
    }
}
