using System;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.AutoSlay.Handlers.Rooms;
using MegaCrit.Sts2.Core.AutoSlay.Helpers;
using MegaCrit.Sts2.Core.Nodes.GodotExtensions;
using MegaCrit.Sts2.Core.Nodes.Rooms;
using MegaCrit.Sts2.Core.Nodes.Screens.Map;
using MegaCrit.Sts2.Core.Nodes.Screens.TreasureRoomRelic;

namespace SlayTheHuman;

/// <summary>
/// In run mode with an agent, the agent takes or skips the treasure chest's relic. AutoSlay always takes it. In
/// singleplayer a chest holds at most one relic.
/// </summary>
[HarmonyPatch(typeof(TreasureRoomHandler), nameof(TreasureRoomHandler.HandleAsync))]
internal static class AgentTreasure
{
    private static readonly TimeSpan RoomTimeout = TimeSpan.FromSeconds(10);

    private static bool Prepare() => RunMode.WithAgent;

    private static bool Prefix(CancellationToken ct, ref Task __result)
    {
        __result = OpenAsync(ct);
        return false;
    }

    private static async Task OpenAsync(CancellationToken ct)
    {
        var root = ((SceneTree)Engine.GetMainLoop()).Root;
        NTreasureRoom? room = null;
        await Wait.Until(() => (room = root.GetNodeOrNull<NTreasureRoom>("/root/Game/RootSceneContainer/Run/RoomContainer/TreasureRoom"))
            is not null && room.IsVisibleInTree(), RoomTimeout, "the treasure room", ct);
        await UiHelper.Click(room!.GetNode<NClickableControl>("Chest"));
        NTreasureRoomRelicHolder? Holder() =>
            UiHelper.FindAll<NTreasureRoomRelicHolder>(room).FirstOrDefault(holder => holder.IsEnabled && holder.Visible);
        // The relic appears once the chest opens; an empty chest only enables the button.
        await Wait.Until(() => Holder() is not null || room.ProceedButton.IsEnabled, RoomTimeout, "the chest to open", ct);

        var holder = Holder();
        var decision = new Decision("treasure");
        decision.State["relic"] = holder?.Relic.Model.Id.Entry;
        if (holder is not null)
        {
            decision.Add(new JsonObject { ["kind"] = "take" }, () => UiHelper.Click(holder));
        }
        decision.Add(new JsonObject { ["kind"] = "skip" }, () => Task.CompletedTask);
        await decision.RunAsync(ct);

        // After taking, the button reads "proceed"; without, it reads "skip". Either way it leaves.
        await Wait.Until(() => room.ProceedButton.IsEnabled, RoomTimeout, "the treasure room's button", ct);
        await UiHelper.Click(room.ProceedButton);
        await Wait.Until(() => NMapScreen.Instance?.IsOpen ?? false, RoomTimeout, "the map after the treasure room", ct);
    }
}
