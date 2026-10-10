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
using MegaCrit.Sts2.Core.Events.Custom.CrystalSphereEvent;
using MegaCrit.Sts2.Core.Nodes.CommonUi;
using MegaCrit.Sts2.Core.Nodes.Events;
using MegaCrit.Sts2.Core.Nodes.Events.Custom.CrystalSphere;
using MegaCrit.Sts2.Core.Nodes.GodotExtensions;
using MegaCrit.Sts2.Core.Nodes.Screens.Map;
using MegaCrit.Sts2.Core.Nodes.Screens.Overlays;

namespace SlayTheHuman;

/// <summary>
/// In run mode with an agent, the agent plays the Crystal Sphere: which cell to reveal next, and which divination
/// (big or small) to use. AutoSlay clicks random cells. The agent sees which cells are hidden, never what is under them.
/// </summary>
[HarmonyPatch(typeof(CrystalSphereScreenHandler), nameof(CrystalSphereScreenHandler.HandleAsync))]
internal static class AgentCrystalSphere
{
    private const int MaxChoices = 200;
    private static readonly TimeSpan StepTimeout = TimeSpan.FromSeconds(10);
    private static readonly TimeSpan FinishTimeout = TimeSpan.FromSeconds(30);

    private static readonly AccessTools.FieldRef<NCrystalSphereScreen, CrystalSphereMinigame> Minigame =
        AccessTools.FieldRefAccess<NCrystalSphereScreen, CrystalSphereMinigame>("_entity");

    private static bool Prepare() => RunMode.WithAgent;

    private static bool Prefix(CancellationToken ct, ref Task __result)
    {
        __result = PlayAsync(AutoSlayer.GetCurrentScreen<NCrystalSphereScreen>(), ct);
        return false;
    }

    private static async Task PlayAsync(NCrystalSphereScreen screen, CancellationToken ct)
    {
        var game = Minigame(screen);
        for (var choices = 0; choices < MaxChoices && !game.IsFinished; choices++)
        {
            ct.ThrowIfCancellationRequested();
            if (!Alive(screen) || OtherScreenOnTop(screen) || Proceed(screen) is { IsEnabled: true })
            {
                break;
            }
            var hidden = UiHelper.FindAll<NCrystalSphereCell>(screen.GetNode<Control>("%Cells"))
                .Where(cell => cell.Visible && cell.Entity.IsHidden).ToList();
            if (hidden.Count == 0)
            {
                break;
            }
            var decision = new Decision("crystal_sphere");
            decision.State["width"] = game.GridSize.X;
            decision.State["height"] = game.GridSize.Y;
            decision.State["hidden"] = new JsonArray(hidden
                .Select(cell => (JsonNode)new JsonArray(cell.Entity.X, cell.Entity.Y)).ToArray());
            decision.State["divinations"] = game.DivinationCount;
            decision.State["tool"] = game.CrystalSphereTool.ToString();
            var count = game.DivinationCount;
            foreach (var cell in hidden)
            {
                decision.Add(new JsonObject { ["kind"] = "reveal", ["x"] = cell.Entity.X, ["y"] = cell.Entity.Y }, async () =>
                {
                    cell.EmitSignal(NClickableControl.SignalName.Released, cell);
                    await Wait.Until(() => game.DivinationCount < count || !Alive(screen) || OtherScreenOnTop(screen),
                        StepTimeout, "the Crystal Sphere to reveal a cell", ct);
                });
            }
            var other = game.CrystalSphereTool == CrystalSphereMinigame.CrystalSphereToolType.Small
                ? CrystalSphereMinigame.CrystalSphereToolType.Big
                : CrystalSphereMinigame.CrystalSphereToolType.Small;
            decision.Add(new JsonObject { ["kind"] = "tool", ["tool"] = other.ToString() }, async () =>
            {
                var button = screen.GetNode<NDivinationButton>(other == CrystalSphereMinigame.CrystalSphereToolType.Big
                    ? "%BigDivinationButton" : "%SmallDivinationButton");
                await UiHelper.Click(button);
                await Wait.Until(() => game.CrystalSphereTool == other, StepTimeout, "the Crystal Sphere's tool to change", ct);
            });
            await decision.RunAsync(ct);
        }

        // No choice from here: the rewards screen (left to AutoSlay's screen loop), then proceed.
        await Wait.Until(() => !Alive(screen) || OtherScreenOnTop(screen) || Proceed(screen) is { IsEnabled: true },
            FinishTimeout, "the Crystal Sphere to finish", ct);
        if (!Alive(screen) || OtherScreenOnTop(screen))
        {
            return;
        }
        await UiHelper.Click(Proceed(screen)!);
        await Wait.Until(() => !Alive(screen) || (NMapScreen.Instance?.IsVisibleInTree() ?? false), StepTimeout,
            "the Crystal Sphere to close", ct);
        if (Alive(screen) && (NMapScreen.Instance?.IsVisibleInTree() ?? false))
        {
            // The game can leave the screen on the overlay stack under the map; AutoSlay removes it the same way.
            NOverlayStack.Instance?.Remove(screen);
        }
    }

    private static NProceedButton? Proceed(NCrystalSphereScreen screen) => screen.GetNodeOrNull<NProceedButton>("%ProceedButton");

    private static bool OtherScreenOnTop(NCrystalSphereScreen screen) =>
        NOverlayStack.Instance?.Peek() is { } top && top != screen;

    private static bool Alive(NCrystalSphereScreen screen) => GodotObject.IsInstanceValid(screen) && screen.IsVisibleInTree();
}
