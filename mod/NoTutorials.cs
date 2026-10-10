using HarmonyLib;
using Godot;
using MegaCrit.Sts2.Core.Logging;
using MegaCrit.Sts2.Core.Nodes.CommonUi;
using MegaCrit.Sts2.Core.Nodes.Ftue;

namespace SlayTheHuman;

/// <summary>
/// In run mode, tutorial popups (FTUE) never open. Nobody closes them in an unattended run, and an open popup blocks
/// every later modal (such as the confirmation an event option that gives up the run needs) and takes over as the
/// active screen, which disables buttons that check for it (such as the FakeMerchant's proceed). They inform; they
/// offer no choice.
/// </summary>
[HarmonyPatch(typeof(NModalContainer), nameof(NModalContainer.Add))]
internal static class NoTutorials
{
    private static bool Prepare() => RunMode.IsOn;

    private static bool Prefix(Node modalToCreate)
    {
        if (modalToCreate is not NFtue tutorial)
        {
            return true;
        }
        Log.Info($"[{ModEntry.Id}] skipped tutorial {tutorial.GetType().Name}");
        tutorial.QueueFree();
        return false;
    }
}
