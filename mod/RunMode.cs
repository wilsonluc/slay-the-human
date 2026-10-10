using MegaCrit.Sts2.Core.Helpers;

namespace SlayTheHuman;

/// <summary>
/// Run mode: the game was launched by tools/run.sh to play one unattended run. Every run-mode patch class checks
/// <see cref="IsOn"/> in its Harmony Prepare(), so a normal launch applies none of them.
/// </summary>
internal static class RunMode
{
    public static readonly bool IsOn = CommandLineHelper.HasArg("slay-the-human-run");

    /// <summary>The run's seed: --slay-the-human-seed=&lt;seed&gt; when given, else a new random one.</summary>
    public static readonly string Seed = CommandLineHelper.GetValue("slay-the-human-seed") is { Length: > 0 } seed
        ? SeedHelper.CanonicalizeSeed(seed)
        : SeedHelper.GetRandomSeed();
}
