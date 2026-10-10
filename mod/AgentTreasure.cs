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
using MegaCrit.Sts2.Core.Multiplayer.Game;
using MegaCrit.Sts2.Core.Rooms;

namespace SlayTheHuman;

/// <summary>
/// In run mode with an agent, the agent takes or skips the treasure chest's relic. AutoSlay always takes it. In
/// singleplayer a chest holds at most one relic, and none with Silver Crucible.
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

    private static readonly AccessTools.FieldRef<NTreasureRoom, bool> ChestOpened =
        AccessTools.FieldRefAccess<NTreasureRoom, bool>("_hasChestBeenOpened");

    private static async Task OpenAsync(CancellationToken ct)
    {
        var root = ((SceneTree)Engine.GetMainLoop()).Root;
        NTreasureRoom? room = null;
        // The room shows before the game has drawn the chest's relic. A chest opened before that counts as empty, and its
        // relic is lost, so wait for the draw too.
        await Wait.Until(() => (room = root.GetNodeOrNull<NTreasureRoom>("/root/Game/RootSceneContainer/Run/RoomContainer/TreasureRoom"))
            is not null && room.IsVisibleInTree() && RelicDrawn.Done, RoomTimeout, "the treasure room", ct);
        await UiHelper.Click(room!.GetNode<NClickableControl>("Chest"));
        NTreasureRoomRelicHolder? Holder() =>
            UiHelper.FindAll<NTreasureRoomRelicHolder>(room).FirstOrDefault(holder => holder.IsEnabled && holder.Visible);
        // The room's button is enabled before the chest opens, so wait for the game to finish opening it: then the relic
        // is offered, or an empty chest only enables the button.
        await Wait.Until(() => ChestOpened(room) && (Holder() is not null || room.ProceedButton.IsEnabled), RoomTimeout,
            "the chest to open", ct);

        var holder = Holder();
        var skipping = holder is not null;
        var decision = new Decision("treasure");
        decision.State["relic"] = holder?.Relic.Model.Id.Entry;
        if (holder is not null)
        {
            decision.Add(new JsonObject { ["kind"] = "take" }, () =>
            {
                skipping = false;
                return UiHelper.Click(holder);
            });
        }
        decision.Add(new JsonObject { ["kind"] = "skip" }, () => Task.CompletedTask);
        await decision.RunAsync(ct);

        // Skipping a relic presses the button while it reads "skip". After taking the relic, or with an empty chest, the
        // game finishes on its own and the button then reads "proceed"; pressing it while it still reads "skip" (the
        // game enables it at times before then) would skip a relic that is no longer offered, which throws.
        await Wait.Until(() => room.ProceedButton.IsEnabled && (skipping || !room.ProceedButton.IsSkip), RoomTimeout,
            "the treasure room's button", ct);
        await UiHelper.Click(room.ProceedButton);
        await Wait.Until(() => NMapScreen.Instance?.IsOpen ?? false, RoomTimeout, "the map after the treasure room", ct);
    }
}

/// <summary>
/// Whether the current treasure room has drawn its chest's relic (or found it empty): the game does it at the end of
/// entering the room, after the room shows.
/// </summary>
internal static class RelicDrawn
{
    public static bool Done { get; private set; }

    public static void Reset() => Done = false;

    [HarmonyPatch(typeof(TreasureRoomRelicSynchronizer), nameof(TreasureRoomRelicSynchronizer.BeginRelicPicking))]
    private static class Drawn
    {
        private static bool Prepare() => RunMode.WithAgent;

        private static void Postfix() => Done = true;
    }

    [HarmonyPatch(typeof(TreasureRoom), nameof(TreasureRoom.Exit))]
    private static class Left
    {
        private static bool Prepare() => RunMode.WithAgent;

        private static void Postfix() => Done = false;
    }
}
