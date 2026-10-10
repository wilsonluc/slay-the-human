using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.AutoSlay;
using MegaCrit.Sts2.Core.AutoSlay.Handlers.Screens;
using MegaCrit.Sts2.Core.Entities.CardRewardAlternatives;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Nodes.Screens.CardSelection;

namespace SlayTheHuman;

/// <summary>
/// In run mode with an agent, the agent answers the card reward screen: one of the offered cards, or one of the
/// screen's other options such as skipping. The game asks the screen through OptionSelected(): an index into the
/// cards, or past them into the other options.
/// </summary>
[HarmonyPatch(typeof(NCardRewardSelectionScreen), nameof(NCardRewardSelectionScreen.OptionSelected))]
internal static class AgentCardReward
{
    private static readonly AccessTools.FieldRef<NCardRewardSelectionScreen, IReadOnlyList<CardCreationResult>> Options =
        AccessTools.FieldRefAccess<NCardRewardSelectionScreen, IReadOnlyList<CardCreationResult>>("_options");

    private static readonly AccessTools.FieldRef<NCardRewardSelectionScreen, IReadOnlyList<CardRewardAlternative>> Extra =
        AccessTools.FieldRefAccess<NCardRewardSelectionScreen, IReadOnlyList<CardRewardAlternative>>("_extraOptions");

    private static bool Prepare() => RunMode.WithAgent;

    private static bool Prefix(NCardRewardSelectionScreen __instance, ref Task<int?> __result)
    {
        __result = ChooseAsync(__instance);
        return false;
    }

    private static async Task<int?> ChooseAsync(NCardRewardSelectionScreen screen)
    {
        var cards = Options(screen) ?? Array.Empty<CardCreationResult>();
        var alternatives = Extra(screen) ?? Array.Empty<CardRewardAlternative>();
        var decision = new Decision("card_reward");
        decision.State["cards"] = new JsonArray(cards.Select(option => (JsonNode)Decision.Card(option.Card)).ToArray());
        decision.State["alternatives"] = new JsonArray(alternatives.Select(option => (JsonNode)option.OptionId).ToArray());
        int? chosen = null;
        for (var i = 0; i < cards.Count; i++)
        {
            var index = i;
            decision.Add(new JsonObject { ["kind"] = "pick", ["card"] = index }, () => chosen = index);
        }
        for (var j = 0; j < alternatives.Count; j++)
        {
            var index = cards.Count + j;
            decision.Add(new JsonObject { ["kind"] = "alternative", ["option"] = alternatives[j].OptionId },
                () => chosen = index);
        }
        await decision.RunAsync(CancellationToken.None);
        return chosen;
    }
}

/// <summary>
/// In run mode with an agent, AutoSlay's card reward handler only waits for the screen to close, since
/// <see cref="AgentCardReward"/> answers it. AutoSlay would press a random card.
/// </summary>
[HarmonyPatch(typeof(CardRewardScreenHandler), nameof(CardRewardScreenHandler.HandleAsync))]
internal static class WaitForCardReward
{
    private static readonly TimeSpan CloseTimeout = TimeSpan.FromSeconds(60);

    private static bool Prepare() => RunMode.WithAgent;

    private static bool Prefix(CancellationToken ct, ref Task __result)
    {
        var screen = AutoSlayer.GetCurrentScreen<NCardRewardSelectionScreen>();
        __result = Wait.Until(() => !GodotObject.IsInstanceValid(screen) || !screen.IsVisibleInTree(), CloseTimeout,
            "the card reward screen to close", ct);
        return false;
    }
}
