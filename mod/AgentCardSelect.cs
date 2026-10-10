using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using HarmonyLib;
using MegaCrit.Sts2.Core.AutoSlay.Helpers;
using MegaCrit.Sts2.Core.Commands;
using MegaCrit.Sts2.Core.Models;

namespace SlayTheHuman;

/// <summary>
/// In run mode with an agent, every card selection the game asks for goes to the agent instead of AutoSlay's
/// selector, which shuffles and takes the most cards allowed.
/// </summary>
[HarmonyPatch(typeof(AutoSlayCardSelector), nameof(AutoSlayCardSelector.GetSelectedCards))]
internal static class AgentCardSelect
{
    private static bool Prepare() => RunMode.WithAgent;

    private static bool Prefix(IEnumerable<CardModel> options, int minSelect, int maxSelect,
        ref Task<IEnumerable<CardModel>> __result)
    {
        __result = SelectAsync(options.ToList(), minSelect, maxSelect, SelectionPurpose.Take());
        return false;
    }

    private static async Task<IEnumerable<CardModel>> SelectAsync(List<CardModel> cards, int min, int max,
        string purpose)
    {
        var most = Math.Min(max, cards.Count);
        // Only one answer is possible: all of the cards, or none.
        if (most == 0 || cards.Count <= min)
        {
            return cards.Take(most).ToList();
        }
        var state = new JsonObject
        {
            ["purpose"] = purpose, ["min"] = min, ["max"] = most,
            ["cards"] = new JsonArray(cards.Select(card => (JsonNode)Decision.Card(card)).ToArray()),
        };
        var indices = await Bridge.AskIndicesAsync(Decision.WithRun("card_select", state), cards.Count, min, most,
            CancellationToken.None);
        return indices.Select(i => cards[i]).ToList();
    }
}

/// <summary>
/// Records why the game is asking for a card selection, from the <see cref="CardSelectCmd"/> entry point it came
/// through. The game does not pass this to the selector.
/// </summary>
[HarmonyPatch]
internal static class SelectionPurpose
{
    private static readonly Dictionary<string, string> Purposes = new()
    {
        ["FromChooseACardScreen"] = "choose",
        ["FromSimpleGridForRewards"] = "reward_grid",
        ["FromSimpleGrid"] = "grid",
        ["FromCombatPile"] = "combat_pile",
        ["FromDeckForUpgrade"] = "upgrade",
        ["FromDeckForTransformation"] = "transform",
        ["FromDeckForEnchantment"] = "enchant",
        ["FromDeckForRemoval"] = "remove",
        ["FromDeckGeneric"] = "deck",
        ["FromHand"] = "hand",
        ["FromHandForDiscard"] = "discard",
        ["FromHandForUpgrade"] = "hand_upgrade",
    };

    /// <summary>Entry points that only pass through to another one, which then keeps their purpose.</summary>
    private static readonly HashSet<string> PassThrough = new() { "FromDeckForRemoval", "FromHandForDiscard" };

    private static readonly AsyncLocal<string?> Current = new();
    private static string? _handedDown;

    private static bool Prepare() => RunMode.WithAgent;

    private static IEnumerable<MethodBase> TargetMethods() => AccessTools.GetDeclaredMethods(typeof(CardSelectCmd))
        .Where(method => method.IsStatic && method.IsPublic && Purposes.ContainsKey(method.Name));

    private static void Prefix(MethodBase __originalMethod)
    {
        var purpose = Purposes[__originalMethod.Name];
        if (PassThrough.Contains(__originalMethod.Name))
        {
            // It calls the inner entry point straight away, which takes this purpose.
            _handedDown = purpose;
            return;
        }
        Current.Value = _handedDown ?? purpose;
        _handedDown = null;
    }

    /// <summary>The purpose of the selection being asked for, or "other" when it came through no entry point.</summary>
    public static string Take()
    {
        var purpose = Current.Value ?? "other";
        Current.Value = null;
        return purpose;
    }
}
