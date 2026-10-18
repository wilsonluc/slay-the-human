using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Threading;
using System.Threading.Tasks;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.AutoSlay;
using MegaCrit.Sts2.Core.Helpers;
using MegaCrit.Sts2.Core.Logging;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Nodes;
using MegaCrit.Sts2.Core.Nodes.Screens.MainMenu;

namespace SlayTheHuman;

/// <summary>
/// In run mode, plays runs back to back in one game process. At the first main menu it connects to the agent; then, each
/// time the game is at the main menu, it tells the agent so and starts the run the agent asks for with the game's
/// AutoSlay bot, which drives the screens while the agent makes every decision. The agent closing the connection quits
/// the game; a run that fails quits it with exit code 1.
/// </summary>
[HarmonyPatch(typeof(NMainMenu), nameof(NMainMenu._Ready))]
internal static class RunLoop
{
    private static readonly TimeSpan MainMenuTimeout = TimeSpan.FromSeconds(60);

    private static bool _started;

    /// <summary>The AutoSlayer playing the current run.</summary>
    public static AutoSlayer? Slayer { get; private set; }

    private static readonly System.Reflection.MethodInfo DrainOverlayScreens =
        HarmonyLib.AccessTools.Method(typeof(AutoSlayer), "DrainOverlayScreensAsync");

    /// <summary>
    /// Answers every screen open over the room through AutoSlay's screen loop, which dispatches to the agent's handlers
    /// (rewards, card choices). For screens a room opens partway through: an event option's rewards, a rest's.
    /// </summary>
    public static Task DrainScreensAsync(CancellationToken ct) =>
        (Task)DrainOverlayScreens.Invoke(Slayer, new object[] { ct })!;

    private static bool Prepare() => RunMode.IsOn;

    private static void Postfix()
    {
        // The main menu comes back after every run; only the first one starts the loop.
        if (_started)
        {
            return;
        }
        _started = true;
        TaskHelper.RunSafely(LoopAsync());
    }

    private static async Task LoopAsync()
    {
        try
        {
            if (!Bridge.IsOn)
            {
                throw new InvalidOperationException("run mode needs the agent: --slay-the-human-agent-port=<port>");
            }
            await Bridge.ConnectAsync(CancellationToken.None);
            RunLog.Attach();
            var root = ((SceneTree)Engine.GetMainLoop()).Root;
            while (true)
            {
                // A run takes as long as it takes; only the way back to the main menu after it should be quick.
                await Wait.Until(() => !AutoSlayer.IsActive, TimeSpan.MaxValue, "the run to end", CancellationToken.None);
                await Wait.Until(() => root.GetNodeOrNull<Control>("/root/Game/RootSceneContainer/MainMenu")?.IsVisibleInTree() ?? false,
                    MainMenuTimeout, "the main menu", CancellationToken.None);
                if (await Bridge.ReadyAsync(CancellationToken.None) is not var (seed, character))
                {
                    Log.Info($"[{ModEntry.Id}] the agent closed the connection; quitting");
                    Quit(0);
                    return;
                }
                var characters = ModelDb.AllCharacters.Select(c => c.Id.Entry).ToList();
                if (!characters.Contains(character.ToUpperInvariant()))
                {
                    throw new InvalidOperationException($"no character {character}; the game has {string.Join(", ", characters)}");
                }
                RunMode.StartRun(seed, character);
                RunLog.Reset();
                RunProfile.Reset();
                RunCounters.Reset();
                SelectionPurpose.Reset();
                RelicDrawn.Reset();
                Log.Info($"[{ModEntry.Id}] run start seed={RunMode.Seed} character={RunMode.Character}");
                Slayer = new AutoSlayer();
                Slayer.Start(RunMode.Seed);
            }
        }
        catch (Exception e)
        {
            Log.Error($"[{ModEntry.Id}] run error: {e.Message}");
            Quit(1);
        }
    }

    private static void Quit(int exitCode) => NGame.Instance?.GetTree().Quit(exitCode);
}

/// <summary>
/// In run mode, the game stays open after a run that ended normally (won or lost), back at the main menu for the next.
/// AutoSlay quits after every run; a failed run (exit code 1) still quits.
/// </summary>
[HarmonyPatch(typeof(AutoSlayer), "QuitGame")]
internal static class StayOpen
{
    private static bool Prepare() => RunMode.IsOn;

    private static bool Prefix(int exitCode) => exitCode != 0;
}

/// <summary>
/// In run mode, AutoSlay plays a run to its end. Its run loop stops at total floor 49 and abandons the run, through a
/// button this build no longer has; a run whose act 3 boss is on floor 50 was failed at the rest site before it, and
/// those are the agent's best runs (spec 015). A win and a loss end the loop on their own.
/// </summary>
[HarmonyPatch]
internal static class NoFloorLimit
{
    private const int FloorLimit = 49;

    private static bool Prepare() => RunMode.IsOn;

    private static MethodBase TargetMethod() =>
        AccessTools.AsyncMoveNext(AccessTools.Method(typeof(AutoSlayer), "PlayRunAsync"))
        ?? throw new InvalidOperationException("AutoSlayer.PlayRunAsync is no longer async");

    private static IEnumerable<CodeInstruction> Transpiler(IEnumerable<CodeInstruction> instructions)
    {
        var codes = instructions.ToList();
        var limits = codes.Where(code => code.LoadsConstant(FloorLimit)).ToList();
        if (limits.Count != 1)
        {
            throw new InvalidOperationException(
                $"found {limits.Count} loads of {FloorLimit} in AutoSlayer.PlayRunAsync, not one; the game has changed");
        }
        limits[0].opcode = OpCodes.Ldc_I4;
        limits[0].operand = int.MaxValue;
        return codes;
    }
}
