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
        var points = AllPoints(run.Map);
        var index = points.Select((point, i) => (point.coord, i)).ToDictionary(pair => pair.coord, pair => pair.i);
        var decision = new Decision("map");
        decision.State["points"] = new JsonArray(points.Select(point => (JsonNode)new JsonObject
        {
            ["col"] = point.coord.col, ["row"] = point.coord.row, ["type"] = point.PointType.ToString(),
        }).ToArray());
        decision.State["edges"] = new JsonArray(points.SelectMany(point => point.Children
                .Where(child => index.ContainsKey(child.coord))
                .Select(child => (JsonNode)new JsonArray(index[point.coord], index[child.coord])))
            .ToArray());
        decision.State["current"] = run.CurrentMapCoord is { } here && index.TryGetValue(here, out var at) ? at : null;
        foreach (var target in travelable)
        {
            if (index.TryGetValue(target.Point.coord, out var pointIndex))
            {
                decision.Add(new JsonObject { ["kind"] = "travel", ["point"] = pointIndex }, () => TravelAsync(target, ct));
            }
        }
        await decision.RunAsync(ct);
    }

    /// <summary>Every point of the act's map: the grid, the start and the boss (or bosses).</summary>
    private static List<MapPoint> AllPoints(ActMap map)
    {
        var points = new List<MapPoint> { map.StartingMapPoint };
        points.AddRange(map.GetAllMapPoints());
        points.Add(map.BossMapPoint);
        if (map.SecondBossMapPoint is { } second)
        {
            points.Add(second);
        }
        return points.DistinctBy(point => point.coord).ToList();
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
