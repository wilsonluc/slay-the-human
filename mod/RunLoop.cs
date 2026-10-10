using System;
using System.Linq;
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
                await Wait.Until(() => !AutoSlayer.IsActive &&
                    (root.GetNodeOrNull<Control>("/root/Game/RootSceneContainer/MainMenu")?.IsVisibleInTree() ?? false),
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
                SelectionPurpose.Reset();
                Log.Info($"[{ModEntry.Id}] run start seed={RunMode.Seed} character={RunMode.Character}");
                new AutoSlayer().Start(RunMode.Seed);
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
