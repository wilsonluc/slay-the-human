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
    private static readonly TimeSpan ResumeTimeout = TimeSpan.FromSeconds(10);
    private static readonly TimeSpan CloseTimeout = TimeSpan.FromSeconds(10);
    private static readonly TimeSpan PopupTimeout = TimeSpan.FromMilliseconds(300);
    private static readonly TimeSpan CombatTimeout = TimeSpan.FromSeconds(3);

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
                await Wait.For(() => CombatStarting || (NOverlayStack.Instance?.ScreenCount ?? 0) > 0, CombatTimeout, ct);
                var run = RunManager.Instance.DebugOnlyGetState();
                if (!CombatStarting || run is null || run.CurrentRoomCount <= 1 || run.BaseRoom?.RoomType != RoomType.Event)
                {
                    return;
                }
                await (Task)HandleEventCombat.Invoke(handler, new object[] { ct })!;
                var resumed = ((SceneTree)Engine.GetMainLoop()).Root
                    .GetNodeOrNull("/root/Game/RootSceneContainer/Run/RoomContainer/EventRoom");
                if (resumed is null || !await Wait.For(() => Options(resumed).Count > 0, ResumeTimeout, ct))
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
                if (await Wait.For(() => !Alive(eventRoom) || Options(eventRoom).Count > 0 || CombatStarting ||
                        (NOverlayStack.Instance?.ScreenCount ?? 0) > 0 || (NMapScreen.Instance?.IsOpen ?? false),
                        ChangeTimeout, ct) && (!Alive(eventRoom) || Options(eventRoom).Count > 0))
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
            var chosen = await ChooseAsync(eventRoom, buttons, ct);
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
            var before = new HashSet<NEventOptionButton>(buttons);
            await Wait.Until(() => (NOverlayStack.Instance?.ScreenCount ?? 0) > 0 || (NMapScreen.Instance?.IsOpen ?? false) ||
                !Alive(eventRoom) || CombatManager.Instance.IsInProgress || !before.SetEquals(Options(eventRoom)),
                ChangeTimeout, $"the event to respond to {chosen.Option.TextKey}", ct);
            if ((NOverlayStack.Instance?.ScreenCount ?? 0) > 0)
            {
                return;
            }
            if (CombatManager.Instance.IsInProgress)
            {
                await (Task)HandleEventCombat.Invoke(handler, new object[] { ct })!;
                if (!Alive(eventRoom) || !await Wait.For(() => !Alive(eventRoom) || (NMapScreen.Instance?.IsOpen ?? false) ||
                        (NOverlayStack.Instance?.ScreenCount ?? 0) > 0 || Options(eventRoom).Count > 0, ResumeTimeout, ct) ||
                    !Alive(eventRoom))
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
        if (!await Wait.For(() => NModalContainer.Instance?.OpenModal is NAbandonRunConfirmPopup, PopupTimeout, ct))
        {
            if (NModalContainer.Instance?.OpenModal is { } open)
            {
                MegaCrit.Sts2.Core.Logging.Log.Info($"[{ModEntry.Id}] a modal is open: {open.GetType().Name}");
            }
            return;
        }
        var popup = (Node)NModalContainer.Instance!.OpenModal!;
        await UiHelper.Click(popup.GetNode<NButton>("VerticalPopup/YesButton"));
        await Wait.Until(() => RunOver.IsOver, ChangeTimeout, "the run to end after giving up", ct);
    }

    /// <summary>The event has started a combat: its room is a combat room now, or the combat is under way.</summary>
    private static bool CombatStarting => CombatManager.Instance.IsInProgress ||
        RunManager.Instance.DebugOnlyGetState()?.CurrentRoom is CombatRoom;

    /// <summary>The options that can be chosen now: enabled and not locked.</summary>
    private static List<NEventOptionButton> Options(Node eventRoom) => UiHelper.FindAll<NEventOptionButton>(eventRoom)
        .Where(button => !button.Option.IsLocked && button.IsEnabled).ToList();

    private static bool Alive(Node node) => GodotObject.IsInstanceValid(node) && node.IsInsideTree();
}
