using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using HarmonyLib;
using MegaCrit.Sts2.Core.AutoSlay.Helpers;
using MegaCrit.Sts2.Core.CardSelection;
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
            ["cards"] = new JsonArray(cards.Select(card => (JsonNode)GameState.Card(card)).ToArray()),
        };
        var indices = await Bridge.AskIndicesAsync(Decision.WithRun("card_select", state), cards.Count, min, most,
            CancellationToken.None);
        return indices.Select(i => cards[i]).ToList();
    }
}

/// <summary>
/// Records why the game is asking for a card selection; the game does not pass this to the selector. Each
/// <see cref="CardSelectCmd"/> entry point is an async method, and its state machine's MoveNext runs right before it
/// asks the selector, including after an await. The patch is on MoveNext, not on the entry point itself, because the
/// JIT can inline the small entry point stubs into their callers, which skips patches on them. The purpose is the
/// prompt's (the shop's removal reaches FromDeckGeneric with the "to remove" prompt), else the entry point's.
/// </summary>
[HarmonyPatch]
internal static class SelectionPurpose
{
    private static readonly Dictionary<string, string> EntryPurposes = new()
    {
        ["FromChooseACardScreen"] = "choose",
        ["FromSimpleGridForRewards"] = "reward_grid",
        ["FromSimpleGrid"] = "grid",
        ["FromCombatPile"] = "combat_pile",
        ["FromDeckForUpgrade"] = "upgrade",
        ["FromDeckForTransformation"] = "transform",
        ["FromDeckForEnchantment"] = "enchant",
        ["FromDeckGeneric"] = "deck",
        ["FromHand"] = "hand",
        ["FromHandForDiscard"] = "discard",
        ["FromHandForUpgrade"] = "hand_upgrade",
    };

    /// <summary>The game's own selection prompts (card_selection.TO_*), each naming its purpose.</summary>
    private static readonly Dictionary<string, string> PromptPurposes = new()
    {
        ["TO_REMOVE"] = "remove", ["TO_UPGRADE"] = "upgrade", ["TO_TRANSFORM"] = "transform",
        ["TO_ENCHANT"] = "enchant", ["TO_DISCARD"] = "discard", ["TO_EXHAUST"] = "exhaust",
    };

    /// <summary>
    /// Entry points that only pass through to another one (FromHandForDiscard awaits FromHand), which then keeps their
    /// purpose rather than its own.
    /// </summary>
    private static readonly HashSet<string> PassThrough = new() { "FromHandForDiscard" };

    /// <summary>For each entry point's state machine type: its purpose, its prefs field and its state field.</summary>
    private static readonly Dictionary<Type, (string Purpose, FieldInfo? Prefs, FieldInfo State, bool PassThrough)> Machines = new();

    private static string? _last;
    private static string? _handedDown;

    /// <summary>The purpose a pass-through handed to an entry point, kept for each of its later steps.</summary>
    private static readonly ConditionalWeakTable<object, string> Inherited = new();

    private static bool Prepare() => RunMode.WithAgent;

    /// <summary>At each run's start, so a purpose from the last run never reaches this one.</summary>
    public static void Reset()
    {
        _last = null;
        _handedDown = null;
    }

    private static IEnumerable<MethodBase> TargetMethods()
    {
        foreach (var method in AccessTools.GetDeclaredMethods(typeof(CardSelectCmd))
                     .Where(method => method.IsStatic && method.IsPublic && EntryPurposes.ContainsKey(method.Name)))
        {
            var moveNext = AccessTools.AsyncMoveNext(method)
                ?? throw new InvalidOperationException($"CardSelectCmd.{method.Name} is no longer async");
            var machine = moveNext.DeclaringType!;
            Machines[machine] = (EntryPurposes[method.Name], AccessTools.Field(machine, "prefs"),
                AccessTools.Field(machine, "<>1__state")
                    ?? throw new InvalidOperationException($"no state field on {machine.Name}"),
                PassThrough.Contains(method.Name));
            yield return moveNext;
        }
    }

    private static void Prefix(object __instance)
    {
        var (purpose, prefs, state, passThrough) = Machines[__instance.GetType()];
        // A state machine's first step has state -1; later steps resume after an await.
        var starting = (int)state.GetValue(__instance)! == -1;
        var prompt = prefs?.GetValue(__instance) is CardSelectorPrefs { Prompt: { } text } ? text.LocEntryKey : null;
        var fromPrompt = prompt is not null ? PromptPurposes.GetValueOrDefault(prompt) : null;
        if (passThrough)
        {
            // Hand the purpose to the entry point it starts straight away; only on its first step, so a wrapper
            // resuming later cannot pass a stale purpose to an unrelated selection.
            if (starting)
            {
                _handedDown = fromPrompt ?? purpose;
            }
            return;
        }
        if (starting && _handedDown is not null)
        {
            Inherited.AddOrUpdate(__instance, _handedDown);
            _handedDown = null;
        }
        _last = fromPrompt ?? (Inherited.TryGetValue(__instance, out var inherited) ? inherited : purpose);
    }

    /// <summary>The purpose of the selection being asked for, or "other" when it came through no entry point.</summary>
    public static string Take()
    {
        var purpose = _last ?? "other";
        _last = null;
        return purpose;
    }
}
