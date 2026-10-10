using System;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.AutoSlay;
using MegaCrit.Sts2.Core.AutoSlay.Handlers.Screens;
using MegaCrit.Sts2.Core.AutoSlay.Helpers;
using MegaCrit.Sts2.Core.Nodes.Cards;
using MegaCrit.Sts2.Core.Nodes.CommonUi;
using MegaCrit.Sts2.Core.Nodes.Screens.CardSelection;

namespace SlayTheHuman;

/// <summary>
/// In run mode with an agent, the agent picks one of the offered card bundles. AutoSlay picks at random. The game
/// shows this screen itself; it never asks the card selector.
/// </summary>
[HarmonyPatch(typeof(ChooseABundleScreenHandler), nameof(ChooseABundleScreenHandler.HandleAsync))]
internal static class AgentBundle
{
    private static readonly TimeSpan ConfirmTimeout = TimeSpan.FromSeconds(10);

    private static bool Prepare() => RunMode.WithAgent;

    private static bool Prefix(CancellationToken ct, ref Task __result)
    {
        __result = ChooseAsync(AutoSlayer.GetCurrentScreen<NChooseABundleSelectionScreen>(), ct);
        return false;
    }

    private static async Task ChooseAsync(NChooseABundleSelectionScreen screen, CancellationToken ct)
    {
        var bundles = UiHelper.FindAll<NCardBundle>(screen);
        var decision = new Decision("bundle");
        decision.State["bundles"] = new JsonArray(bundles.Select(bundle =>
            (JsonNode)new JsonArray(bundle.Bundle.Select(card => (JsonNode)Decision.Card(card)).ToArray())).ToArray());
        for (var i = 0; i < bundles.Count; i++)
        {
            var bundle = bundles[i];
            decision.Add(new JsonObject { ["kind"] = "pick", ["bundle"] = i }, async () =>
            {
                await UiHelper.Click(bundle.Hitbox);
                NConfirmButton? confirm = null;
                await Wait.Until(() => (confirm = UiHelper.FindFirst<NConfirmButton>(screen)) is { IsEnabled: true } &&
                    confirm.IsVisibleInTree(), ConfirmTimeout, "the bundle's confirm button", ct);
                await UiHelper.Click(confirm!);
                await Wait.Until(() => !GodotObject.IsInstanceValid(screen) || !screen.IsVisibleInTree(), ConfirmTimeout,
                    "the bundle screen to close", ct);
            });
        }
        await decision.RunAsync(ct);
    }
}
