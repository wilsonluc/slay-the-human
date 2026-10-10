using System;
using System.Linq;
using HarmonyLib;
using MegaCrit.Sts2.Core.Logging;
using MegaCrit.Sts2.Core.Modding;

namespace SlayTheHuman;

/// <summary>The mod's entry point. The game calls <see cref="Init"/> once at startup, before the main menu.</summary>
[ModInitializer(nameof(Init))]
public static class ModEntry
{
    /// <summary>The mod ID, as in SlayTheHuman.json. It prefixes every line the mod logs.</summary>
    public const string Id = "SlayTheHuman";

    public static void Init()
    {
        var harmony = new Harmony(Id);
        var patches = typeof(ModEntry).Assembly.GetTypes().Where(t => t.IsDefined(typeof(HarmonyPatch), false)).ToList();
        var applied = 0;
        foreach (var patch in patches)
        {
            try
            {
                // Patch() returns nothing for a class whose Prepare() turned it off, such as run-mode patches.
                if (harmony.CreateClassProcessor(patch).Patch() is { Count: > 0 })
                {
                    applied++;
                }
            }
            catch (Exception e)
            {
                // A half-patched game is worse than none: undo every patch and stop the mod. Rethrowing makes the game
                // mark the mod as failed.
                harmony.UnpatchAll(harmony.Id);
                Log.Error($"[{Id}] patch {patch.Name} failed to apply; mod stopped: {e}");
                throw;
            }
        }
        Log.Info($"[{Id}] applied {applied} of {patches.Count} patch classes");
    }
}
