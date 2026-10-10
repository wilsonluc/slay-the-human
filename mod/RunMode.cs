using MegaCrit.Sts2.Core.Helpers;

namespace SlayTheHuman;

/// <summary>
/// Run mode: the game was launched to play unattended runs, each started by the agent. Every run-mode patch class
/// checks <see cref="IsOn"/> (or <see cref="WithAgent"/>) in its Harmony Prepare(), so a normal launch applies none of
/// them.
/// </summary>
internal static class RunMode
{
    public static readonly bool IsOn = CommandLineHelper.HasArg("slay-the-human-run");

    /// <summary>Run mode with the Python agent making the decisions.</summary>
    public static bool WithAgent => IsOn && Bridge.IsOn;

    /// <summary>The current run's seed, canonicalised as the game does.</summary>
    public static string Seed { get; private set; } = "";

    /// <summary>The current run's character ID, such as IRONCLAD.</summary>
    public static string Character { get; private set; } = "";

    /// <summary>Sets the next run's seed (a new random one when null) and character.</summary>
    public static void StartRun(string? seed, string character)
    {
        Seed = seed is null ? SeedHelper.GetRandomSeed() : SeedHelper.CanonicalizeSeed(seed);
        Character = character.ToUpperInvariant();
    }
}
