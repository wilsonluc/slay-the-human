using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.Assets;
using MegaCrit.Sts2.Core.Logging;

namespace SlayTheHuman;

/// <summary>
/// In run mode, every resource the game loads stays loaded until the game exits. The game frees a scene once nothing
/// holds it and loads it again when next needed, and each reload of a C# script has the engine rebuild the script's
/// class information by reflection: about two thirds of the main thread's time, before this (spec 012). Memory then
/// grows only with the distinct resources the runs touch, which the game's own assets bound.
/// </summary>
[HarmonyPatch]
internal static class KeepResources
{
    private const int LogEvery = 500;

    // Loads come from background threads too (LoadThreadedGet); the lock covers the set.
    private static readonly HashSet<Resource> Kept = new();

    private static bool Prepare() => RunMode.IsOn;

    private static IEnumerable<MethodBase> TargetMethods()
    {
        // The non-generic overloads: Load<T> goes through Load.
        var methods = typeof(ResourceLoader).GetMethods(BindingFlags.Public | BindingFlags.Static)
            .Where(method => !method.IsGenericMethodDefinition).ToList();
        yield return methods.Single(method => method.Name == nameof(ResourceLoader.Load) &&
            method.GetParameters().Select(p => p.ParameterType)
                .SequenceEqual(new[] { typeof(string), typeof(string), typeof(ResourceLoader.CacheMode) }));
        yield return methods.Single(method => method.Name == nameof(ResourceLoader.LoadThreadedGet));
    }

    private static void Postfix(Resource? __result)
    {
        if (__result is null)
        {
            return;
        }
        lock (Kept)
        {
            if (Kept.Add(__result) && Kept.Count % LogEvery == 0)
            {
                Log.Info($"[{ModEntry.Id}] keeping {Kept.Count} loaded resources");
            }
        }
    }
}

/// <summary>In run mode, the game's asset cache unloads nothing (<see cref="KeepResources"/>).</summary>
[HarmonyPatch(typeof(AssetCache))]
internal static class NoAssetUnloading
{
    private static bool Prepare() => RunMode.IsOn;

    [HarmonyPrefix, HarmonyPatch(nameof(AssetCache.UnloadAssets))]
    private static bool UnloadAssets() => false;

    [HarmonyPrefix, HarmonyPatch(nameof(AssetCache.UnloadMissedCacheAssets))]
    private static bool UnloadMissedCacheAssets() => false;
}
