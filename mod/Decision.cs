using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using MegaCrit.Sts2.Core.Context;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Runs;

namespace SlayTheHuman;

/// <summary>
/// One choice for the agent (docs/protocol.md): its kind, the kind's state, the legal actions, and how to carry out
/// each. Adds the run state, asks the agent, and carries out the answer; with only one legal action it does not ask.
/// </summary>
internal sealed class Decision(string kind)
{
    private readonly JsonArray _actions = new();
    private readonly List<Func<Task>> _execute = new();

    /// <summary>The kind's own state, sent as state.&lt;kind&gt;.</summary>
    public JsonObject State { get; } = new();

    public void Add(JsonObject action, Func<Task> execute)
    {
        _actions.Add(action);
        _execute.Add(execute);
    }

    public void Add(JsonObject action, Action execute) => Add(action, () =>
    {
        execute();
        return Task.CompletedTask;
    });

    public async Task RunAsync(CancellationToken ct)
    {
        if (_actions.Count == 0)
        {
            throw new InvalidOperationException($"no legal action for a {kind} decision");
        }
        var index = _actions.Count == 1 ? 0 : await Bridge.AskIndexAsync(kind, WithRun(kind, State), _actions, ct);
        await _execute[index]();
    }

    /// <summary>The full state: the run state plus the kind's state.</summary>
    public static JsonObject WithRun(string kind, JsonObject state) =>
        new() { ["run"] = RunState(), [kind] = state };

    public static Player Me() => LocalContext.GetMe(RunManager.Instance.DebugOnlyGetState())
        ?? throw new InvalidOperationException("no local player in the run");

    public static JsonObject Card(CardModel card) => new()
    {
        ["id"] = card.Id.Entry, ["upgraded"] = card.IsUpgraded, ["type"] = card.Type.ToString(),
        ["rarity"] = card.Rarity.ToString(),
    };

    private static JsonObject RunState()
    {
        var run = RunManager.Instance.DebugOnlyGetState() ?? throw new InvalidOperationException("no run in progress");
        var me = Me();
        return new JsonObject
        {
            ["character"] = me.Character.Id.Entry,
            ["hp"] = me.Creature.CurrentHp, ["max_hp"] = me.Creature.MaxHp, ["gold"] = me.Gold,
            ["ascension"] = run.AscensionLevel,
            ["act"] = run.CurrentActIndex + 1, ["floor"] = run.TotalFloor,
            ["deck"] = new JsonArray(me.Deck.Cards
                .Select(card => (JsonNode)new JsonObject { ["id"] = card.Id.Entry, ["upgraded"] = card.IsUpgraded })
                .ToArray()),
            ["relics"] = new JsonArray(me.Relics
                .Select(relic => (JsonNode)new JsonObject
                {
                    ["id"] = relic.Id.Entry, ["counter"] = relic.ShowCounter ? relic.DisplayAmount : null,
                })
                .ToArray()),
            ["potions"] = new JsonArray(me.PotionSlots.Select(potion => potion is null
                ? null
                : (JsonNode)new JsonObject { ["id"] = potion.Id.Entry, ["target"] = potion.TargetType.ToString() })
                .ToArray()),
        };
    }
}
