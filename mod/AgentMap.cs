using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.AutoSlay.Handlers.Screens;
using MegaCrit.Sts2.Core.AutoSlay.Helpers;
using MegaCrit.Sts2.Core.Map;
using MegaCrit.Sts2.Core.Nodes;
using MegaCrit.Sts2.Core.Nodes.Screens.Map;
using MegaCrit.Sts2.Core.Runs;

namespace SlayTheHuman;

/// <summary>
/// In run mode with an agent, the agent chooses the next room on the map, among the points the game's own map screen
/// lets the player travel to. AutoSlay always takes the first path.
/// </summary>
[HarmonyPatch(typeof(MapScreenHandler), nameof(MapScreenHandler.HandleAsync))]
internal static class AgentMap
{
    private static readonly TimeSpan ScreenTimeout = TimeSpan.FromSeconds(10);
    private static readonly TimeSpan EnterTimeout = TimeSpan.FromSeconds(30);

    private static bool Prepare() => RunMode.WithAgent;

    private static bool Prefix(CancellationToken ct, ref Task __result)
    {
        __result = ChooseAsync(ct);
        return false;
    }

    private static async Task ChooseAsync(CancellationToken ct)
    {
        // A death outside combat (a deadly event option) reaches the map handler next; end the run here.
        await RunOver.EndIfLostAsync(ct);
        var screen = NRun.Instance?.GlobalUi.MapScreen ?? throw new InvalidOperationException("no map screen");
        List<NMapPoint> travelable = new();
        await Wait.Until(() =>
        {
            travelable = screen.IsVisibleInTree()
                ? UiHelper.FindAll<NMapPoint>(screen)
                    .Where(point => point.State == MapPointState.Travelable && point.IsEnabled).ToList()
                : new List<NMapPoint>();
            return travelable.Count > 0;
        }, ScreenTimeout, "a travelable map point", ct);

        var run = RunManager.Instance.DebugOnlyGetState() ?? throw new InvalidOperationException("no run in progress");
        // The map is in every decision's state (GameState.Map); travel actions index its points.
        var index = GameState.MapPoints(run.Map).Select((point, i) => (point.coord, i))
            .ToDictionary(pair => pair.coord, pair => pair.i);
        var decision = new Decision("map");
        foreach (var target in travelable)
        {
            if (index.TryGetValue(target.Point.coord, out var pointIndex))
            {
                decision.Add(new JsonObject { ["kind"] = "travel", ["point"] = pointIndex }, () => TravelAsync(target, ct));
            }
        }
        await decision.RunAsync(ct);
    }

    private static async Task TravelAsync(NMapPoint target, CancellationToken ct)
    {
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        void OnEntered() => entered.TrySetResult();
        RunManager.Instance.RoomEntered += OnEntered;
        try
        {
            await UiHelper.Click(target);
            await Wait.Until(() => entered.Task.IsCompleted, EnterTimeout, "the room after traveling", ct);
        }
        finally
        {
            RunManager.Instance.RoomEntered -= OnEntered;
        }
    }
}
