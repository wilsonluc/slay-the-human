using System;
using System.Threading;
using System.Threading.Tasks;
using Godot;
using MegaCrit.Sts2.Core.Logging;

namespace SlayTheHuman;

/// <summary>
/// Waiting on the game, once per frame. In run mode no in-game time limit ends a run: a busy machine slows the game,
/// and the agent may take as long as it likes. Hangs are caught by the agent, which sees no decision arrive.
/// </summary>
internal static class Wait
{
    /// <summary>
    /// Checks the condition once per frame until it holds. Past the given time it logs once what it is waiting for, so a
    /// hang's log names the state it stopped in, and keeps waiting.
    /// </summary>
    public static async Task Until(Func<bool> condition, TimeSpan logAfter, string what, CancellationToken ct)
    {
        var started = DateTime.UtcNow;
        var logged = false;
        while (!condition())
        {
            ct.ThrowIfCancellationRequested();
            if (!logged && DateTime.UtcNow - started > logAfter)
            {
                logged = true;
                Log.Info($"[{ModEntry.Id}] still waiting {logAfter.TotalSeconds:g} s for {what}");
            }
            await NextFrame();
        }
    }

    public static async Task NextFrame()
    {
        var tree = (SceneTree)Engine.GetMainLoop();
        await tree.ToSignal(tree, SceneTree.SignalName.ProcessFrame);
    }
}
