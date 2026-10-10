using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.AutoSlay.Handlers.Rooms;
using MegaCrit.Sts2.Core.AutoSlay.Helpers;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Nodes.CommonUi;
using MegaCrit.Sts2.Core.Nodes.GodotExtensions;
using MegaCrit.Sts2.Core.Nodes.Events;
using MegaCrit.Sts2.Core.Nodes.Screens.Map;
using MegaCrit.Sts2.Core.Nodes.Screens.Overlays;
using MegaCrit.Sts2.Core.Rooms;
using MegaCrit.Sts2.Core.Runs;

namespace SlayTheHuman;

/// <summary>
/// In run mode with an agent, the agent chooses each event option. AutoSlay picks at random. The loop keeps
/// AutoSlay's structure and its own non-choice steps (waiting for the room, clicking through ancient dialogue, event
/// combats, which go to the agent's combat loop); a screen the event opens is left to AutoSlay's screen loop, which
/// dispatches to the agent's handlers.
/// </summary>
[HarmonyPatch(typeof(EventRoomHandler), nameof(EventRoomHandler.HandleAsync))]
internal static class AgentEvent
{
    private const int MaxChoices = 50;
    private static readonly TimeSpan ChangeTimeout = TimeSpan.FromSeconds(30);
    private static readonly TimeSpan CloseTimeout = TimeSpan.FromSeconds(10);

    private static readonly MethodInfo WaitForEventRoom = AccessTools.Method(typeof(EventRoomHandler), "WaitForEventRoom");
    private static readonly MethodInfo WaitForEventOptions = AccessTools.Method(typeof(EventRoomHandler), "WaitForEventOptions");
    private static readonly MethodInfo HandleEventCombat = AccessTools.Method(typeof(EventRoomHandler), "HandleEventCombat");

    private static bool Prepare() => RunMode.WithAgent;

    private static bool Prefix(EventRoomHandler __instance, CancellationToken ct, ref Task __result)
    {
        __result = PlayAsync(__instance, ct);
        return false;
    }

    private static async Task PlayAsync(EventRoomHandler handler, CancellationToken ct)
    {
        var eventRoom = await (Task<Node>)WaitForEventRoom.Invoke(handler, new object[] { ct })!;
        // True when a custom event (FakeMerchant) was handled whole.
        if (await (Task<bool>)WaitForEventOptions.Invoke(handler, new object[] { eventRoom, ct })!)
        {
            return;
        }
        for (var choices = 0; choices < MaxChoices; choices++)
        {
            ct.ThrowIfCancellationRequested();
            if (!Alive(eventRoom))
            {
                // The room closed. A combat may be replacing it, which the game registers a moment later, so wait to
                // see what comes next; after a combat, the event may resume in a new room.
                await Wait.Until(() => CombatStarting || (NOverlayStack.Instance?.ScreenCount ?? 0) > 0 ||
                    (NMapScreen.Instance?.IsOpen ?? false) || RunOver.IsOver, ChangeTimeout,
                    "what follows the event room closing", ct);
                var run = RunManager.Instance.DebugOnlyGetState();
                if (!CombatStarting || run is null || run.CurrentRoomCount <= 1 || run.BaseRoom?.RoomType != RoomType.Event)
                {
                    return;
                }
                await (Task)HandleEventCombat.Invoke(handler, new object[] { ct })!;
                var resumed = ((SceneTree)Engine.GetMainLoop()).Root
                    .GetNodeOrNull("/root/Game/RootSceneContainer/Run/RoomContainer/EventRoom");
                if (resumed is null)
                {
                    return;
                }
                await Wait.Until(() => !Alive(resumed) || Options(resumed).Count > 0 || (NMapScreen.Instance?.IsOpen ?? false) ||
                    (NOverlayStack.Instance?.ScreenCount ?? 0) > 0 || RunOver.IsOver, ChangeTimeout,
                    "the event to resume after its combat", ct);
                if (!Alive(resumed) || Options(resumed).Count == 0)
                {
                    return;
                }
                eventRoom = resumed;
                continue;
            }
            var buttons = Options(eventRoom);
            if (buttons.Count == 0)
            {
                // A click clears the options at once; wait for what follows before deciding the event is over.
                await Wait.Until(() => !Alive(eventRoom) || Options(eventRoom).Count > 0 || CombatStarting ||
                    (NOverlayStack.Instance?.ScreenCount ?? 0) > 0 || (NMapScreen.Instance?.IsOpen ?? false) || RunOver.IsOver,
                    ChangeTimeout, "the event to show what follows", ct);
                if (!Alive(eventRoom) || Options(eventRoom).Count > 0)
                {
                    continue;
                }
                if (CombatStarting)
                {
                    await (Task)HandleEventCombat.Invoke(handler, new object[] { ct })!;
                    continue;
                }
                return;
            }
            var before = new HashSet<NEventOptionButton>(buttons);
            var chosen = await ChooseAsync(eventRoom, buttons, ct);
            // Whatever the option does shows on screen: a new page, a screen, a combat, the map, the room closing, or,
            // for an option that gives up the run, the game's confirmation.
            await Wait.Until(() => GivingUp || (NOverlayStack.Instance?.ScreenCount ?? 0) > 0 ||
                (NMapScreen.Instance?.IsOpen ?? false) || !Alive(eventRoom) || CombatManager.Instance.IsInProgress ||
                !before.SetEquals(Options(eventRoom)) || RunOver.IsOver,
                ChangeTimeout, $"the event to respond to {chosen.Option.TextKey}", ct);
            await ConfirmGivingUpAsync(ct);
            if (RunOver.IsOver)
            {
                await RunOver.EndIfLostAsync(ct);
            }
            if (chosen.Option.IsProceed)
            {
                await Wait.Until(() => !Alive(eventRoom) || (NMapScreen.Instance?.IsOpen ?? false), CloseTimeout,
                    "the event to close", ct);
                return;
            }
            if ((NOverlayStack.Instance?.ScreenCount ?? 0) > 0)
            {
                return;
            }
            if (CombatManager.Instance.IsInProgress)
            {
                await (Task)HandleEventCombat.Invoke(handler, new object[] { ct })!;
                if (!Alive(eventRoom))
                {
                    return;
                }
                await Wait.Until(() => !Alive(eventRoom) || (NMapScreen.Instance?.IsOpen ?? false) ||
                    (NOverlayStack.Instance?.ScreenCount ?? 0) > 0 || Options(eventRoom).Count > 0 || RunOver.IsOver,
                    ChangeTimeout, "the event to resume after its combat", ct);
                if (!Alive(eventRoom) || Options(eventRoom).Count == 0)
                {
                    return;
                }
            }
        }
        throw new InvalidOperationException($"the event was still asking after {MaxChoices} choices");
    }

    /// <summary>Lists every option on the page, locked ones too, and offers the ones that can be chosen.</summary>
    private static async Task<NEventOptionButton> ChooseAsync(Node eventRoom, List<NEventOptionButton> buttons,
        CancellationToken ct)
    {
        var shown = UiHelper.FindAll<NEventOptionButton>(eventRoom);
        var model = buttons[0].Event;
        var owner = model.Owner;
        var decision = new Decision("event");
        decision.State["id"] = model.Id.Entry;
        decision.State["page"] = model.Description?.LocEntryKey;
        decision.State["options"] = new JsonArray(shown.Select(button => (JsonNode)new JsonObject
        {
            ["text_key"] = button.Option.TextKey,
            ["locked"] = button.Option.IsLocked,
            ["proceed"] = button.Option.IsProceed,
            ["deadly"] = owner is not null && (button.Option.WillKillPlayer?.Invoke(owner) ?? false),
            ["relic"] = button.Option.Relic?.Id.Entry,
        }).ToArray());
        NEventOptionButton? chosen = null;
        for (var i = 0; i < shown.Count; i++)
        {
            var button = shown[i];
            if (buttons.Contains(button))
            {
                decision.Add(new JsonObject { ["kind"] = "choose", ["option"] = i }, async () =>
                {
                    chosen = button;
                    await UiHelper.Click(button);
                });
            }
        }
        await decision.RunAsync(ct);
        return chosen!;
    }

    /// <summary>
    /// An option that gives up the run (such as TRIAL's double down) opens the game's abandon-run confirmation.
    /// Choosing that option was the agent's decision, so it is confirmed here.
    /// </summary>
    private static async Task ConfirmGivingUpAsync(CancellationToken ct)
    {
        if (!GivingUp)
        {
            return;
        }
        var popup = (Node)NModalContainer.Instance!.OpenModal!;
        await UiHelper.Click(popup.GetNode<NButton>("VerticalPopup/YesButton"));
        await Wait.Until(() => RunOver.IsOver, ChangeTimeout, "the run to end after giving up", ct);
    }

    /// <summary>The game is asking to confirm giving up the run.</summary>
    private static bool GivingUp => NModalContainer.Instance?.OpenModal is NAbandonRunConfirmPopup;

    /// <summary>The event has started a combat: its room is a combat room now, or the combat is under way.</summary>
    private static bool CombatStarting => CombatManager.Instance.IsInProgress ||
        RunManager.Instance.DebugOnlyGetState()?.CurrentRoom is CombatRoom;

    /// <summary>The options that can be chosen now: enabled and not locked.</summary>
    private static List<NEventOptionButton> Options(Node eventRoom) => UiHelper.FindAll<NEventOptionButton>(eventRoom)
        .Where(button => !button.Option.IsLocked && button.IsEnabled).ToList();

    private static bool Alive(Node node) => GodotObject.IsInstanceValid(node) && node.IsInsideTree();
}
