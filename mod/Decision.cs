using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using MegaCrit.Sts2.Core.Entities.Players;

namespace SlayTheHuman;

/// <summary>
/// One choice for the agent (docs/protocol.md): its kind, the kind's state, the legal actions, and how to carry out
/// each. Adds the run state, asks the agent, and carries out the answer; with only one legal action it does not ask.
/// </summary>
internal sealed class Decision(string kind, JsonObject? state = null)
{
    private readonly JsonArray _actions = new();
    private readonly List<Func<Task>> _execute = new();

    /// <summary>The kind's own state, sent as state.&lt;kind&gt;.</summary>
    public JsonObject State { get; } = state ?? new();

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

    /// <summary>
    /// The full state: the run, the map, the kind's state, and the combat whenever one is in progress (for a combat
    /// decision, the combat is the kind's state).
    /// </summary>
    public static JsonObject WithRun(string kind, JsonObject state)
    {
        var full = new JsonObject { ["run"] = GameState.Run(), ["map"] = GameState.Map() };
        if (kind != "combat" && GameState.Combat() is { } combat)
        {
            full["combat"] = combat;
        }
        // A map decision's own state is the map, which every decision carries already.
        if (kind != "map")
        {
            full[kind] = state;
        }
        return full;
    }

    public static Player Me() => GameState.Me();
}
