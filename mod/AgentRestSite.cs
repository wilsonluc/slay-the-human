using System;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using HarmonyLib;
using MegaCrit.Sts2.Core.AutoSlay.Handlers.Rooms;
using MegaCrit.Sts2.Core.AutoSlay.Helpers;
using MegaCrit.Sts2.Core.Nodes.RestSite;
using MegaCrit.Sts2.Core.Nodes.Rooms;
using MegaCrit.Sts2.Core.Nodes.Screens.Map;
using MegaCrit.Sts2.Core.Nodes.Screens.Overlays;

namespace SlayTheHuman;

/// <summary>
/// In run mode with an agent, the agent chooses among the rest site's options, and when to leave once the game allows
/// it. AutoSlay picks an option at random. Choosing Smith leads to a card selection the agent also answers.
/// </summary>
[HarmonyPatch(typeof(RestSiteRoomHandler), nameof(RestSiteRoomHandler.HandleAsync))]
internal static class AgentRestSite
{
    private static readonly TimeSpan RoomTimeout = TimeSpan.FromSeconds(10);
    private static readonly TimeSpan RespondTimeout = TimeSpan.FromSeconds(60);

    private static bool Prepare() => RunMode.WithAgent;

    private static bool Prefix(CancellationToken ct, ref Task __result)
    {
        __result = ChooseAsync(ct);
        return false;
    }

    private static async Task ChooseAsync(CancellationToken ct)
    {
        NRestSiteRoom? room = null;
        await Wait.Until(() => (room = NRestSiteRoom.Instance) is not null && room.IsVisibleInTree(), RoomTimeout,
            "the rest site", ct);
        var done = false;
        while (!done)
        {
            ct.ThrowIfCancellationRequested();
            var buttons = UiHelper.FindAll<NRestSiteButton>(room!);
            var decision = new Decision("rest");
            decision.State["options"] = new JsonArray(buttons.Select(button => (JsonNode)new JsonObject
            {
                ["id"] = button.Option.OptionId, ["enabled"] = button.Option.IsEnabled,
            }).ToArray());
            for (var i = 0; i < buttons.Count; i++)
            {
                var button = buttons[i];
                if (button.Option.IsEnabled)
                {
                    decision.Add(new JsonObject { ["kind"] = "rest", ["option"] = i }, async () =>
                    {
                        await UiHelper.Click(button);
                        // The option resolves when the game lets the player leave, or opens a screen of its own.
                        await Wait.Until(() => room!.ProceedButton.IsEnabled || (NOverlayStack.Instance?.ScreenCount ?? 0) > 0,
                            RespondTimeout, $"rest site option {button.Option.OptionId} to resolve", ct);
                        if ((NOverlayStack.Instance?.ScreenCount ?? 0) > 0)
                        {
                            throw new InvalidOperationException(
                                $"rest site option {button.Option.OptionId} opened a screen the agent cannot answer");
                        }
                    });
                }
            }
            if (room!.ProceedButton.IsEnabled)
            {
                decision.Add(new JsonObject { ["kind"] = "proceed" }, async () =>
                {
                    done = true;
                    await UiHelper.Click(room.ProceedButton);
                    // The button stays enabled once the map opens, so AutoSlay's own check clicks it again,
                    // harmlessly, after this hands back.
                    await Wait.Until(() => NMapScreen.Instance?.IsOpen ?? false, RoomTimeout, "the map to open", ct);
                });
            }
            await decision.RunAsync(ct);
        }
    }
}
