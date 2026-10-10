using System;
using System.Threading;
using System.Threading.Tasks;
using Godot;

namespace SlayTheHuman;

/// <summary>Waiting on the game: once per frame, always with a timeout.</summary>
internal static class Wait
{
    /// <summary>Checks the condition once per frame until it holds; throws after the timeout.</summary>
    public static async Task Until(Func<bool> condition, TimeSpan timeout, string what, CancellationToken ct)
    {
        var deadline = DateTime.UtcNow + timeout;
        while (!condition())
        {
            ct.ThrowIfCancellationRequested();
            if (DateTime.UtcNow > deadline)
            {
                throw new TimeoutException($"waited {timeout.TotalSeconds:g} seconds for {what}");
            }
            await NextFrame();
        }
    }

    /// <summary>
    /// Checks the condition once per frame for up to the timeout; returns whether it held. For conditions that may
    /// legitimately not happen, such as a reward the game leaves on the screen.
    /// </summary>
    public static async Task<bool> For(Func<bool> condition, TimeSpan timeout, CancellationToken ct)
    {
        var deadline = DateTime.UtcNow + timeout;
        while (!condition())
        {
            ct.ThrowIfCancellationRequested();
            if (DateTime.UtcNow > deadline)
            {
                return false;
            }
            await NextFrame();
        }
        return true;
    }

    public static async Task NextFrame()
    {
        var tree = (SceneTree)Engine.GetMainLoop();
        await tree.ToSignal(tree, SceneTree.SignalName.ProcessFrame);
    }
}
