using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Threading;
using System.Threading.Tasks;
using HarmonyLib;
using MegaCrit.Sts2.Core.AutoSlay;
using MegaCrit.Sts2.Core.AutoSlay.Helpers;
using MegaCrit.Sts2.Core.Logging;

namespace SlayTheHuman;

/// <summary>
/// In run mode, AutoSlay neither times out nor sleeps. Its timeouts (each handler's, the run's, every wait's) would fail a
/// run whenever the agent thinks for long or the machine is busy; hangs are caught by the agent instead. Its fixed sleeps
/// (after rooms, between clicks, while polling) cost real time each run and do nothing a frame does not.
///
/// The timeouts are static readonly fields, which the JIT treats as constants, so this rewrites the code that uses them,
/// in every method of AutoSlay's namespaces, including the state machines of its async methods: each sleep becomes one
/// frame; in WaitHelper.WithTimeout the deadline never comes; each call to WaitHelper.Until or WaitHelper.ForTask goes to
/// a version here that checks once per frame with no timeout. (Those two cannot be rewritten in place: their exception
/// filters defeat the rewrite. Rewriting their callers also holds where the JIT inlined them.)
/// </summary>
[HarmonyPatch]
internal static class RunTiming
{
    private static readonly MethodInfo[] Sleeps =
    {
        AccessTools.Method(typeof(Task), nameof(Task.Delay), new[] { typeof(int) }),
        AccessTools.Method(typeof(Task), nameof(Task.Delay), new[] { typeof(int), typeof(CancellationToken) }),
        AccessTools.Method(typeof(Task), nameof(Task.Delay), new[] { typeof(TimeSpan) }),
        AccessTools.Method(typeof(Task), nameof(Task.Delay), new[] { typeof(TimeSpan), typeof(CancellationToken) }),
    };

    private static readonly Dictionary<MethodInfo, MethodInfo> Waits = new()
    {
        [AccessTools.Method(typeof(WaitHelper), nameof(WaitHelper.Until))] = AccessTools.Method(typeof(RunTiming), nameof(Until)),
        [AccessTools.Method(typeof(WaitHelper), nameof(WaitHelper.ForTask))] = AccessTools.Method(typeof(RunTiming), nameof(ForTask)),
    };

    private static readonly TimeSpan LogAfter = TimeSpan.FromSeconds(30);

    private static int _methods;
    private static int _calls;

    private static bool Prepare() => RunMode.IsOn;

    private static IEnumerable<MethodBase> TargetMethods()
    {
        var targets = typeof(AutoSlayer).Assembly.GetTypes()
            .Where(type => type.Namespace?.StartsWith("MegaCrit.Sts2.Core.AutoSlay") == true && !type.ContainsGenericParameters &&
                !typeof(Delegate).IsAssignableFrom(type))
            .SelectMany(type => AccessTools.GetDeclaredMethods(type).Cast<MethodBase>())
            .Where(method => !method.IsAbstract && !IsReplacedWait(method) && method.GetMethodBody() is not null &&
                Instructions(method).Any(IsTarget))
            .ToList();
        if (targets.Count == 0)
        {
            throw new InvalidOperationException("found no AutoSlay code that sleeps or waits; the game has changed");
        }
        return targets;
    }

    /// <summary>The state machines of WaitHelper.Until and ForTask, which no AutoSlay code reaches any more.</summary>
    private static bool IsReplacedWait(MethodBase method) =>
        method.DeclaringType?.DeclaringType == typeof(WaitHelper) &&
        Waits.Keys.Any(wait => method.DeclaringType.Name.StartsWith($"<{wait.Name}>"));

    private static IEnumerable<CodeInstruction> Instructions(MethodBase method)
    {
        try
        {
            return PatchProcessor.GetOriginalInstructions(method);
        }
        catch (NotSupportedException)
        {
            // Methods the runtime implements itself have no IL to read.
            return Enumerable.Empty<CodeInstruction>();
        }
    }

    private static bool IsTarget(CodeInstruction instruction) =>
        instruction.opcode == OpCodes.Call && instruction.operand is MethodInfo method &&
        (Sleeps.Contains(method) || Waits.ContainsKey(method));

    private static IEnumerable<CodeInstruction> Transpiler(IEnumerable<CodeInstruction> instructions, MethodBase original)
    {
        // The state machine of WaitHelper.WithTimeout is a nested type named after it.
        var deadline = original.DeclaringType?.DeclaringType == typeof(WaitHelper) &&
            original.DeclaringType.Name.StartsWith($"<{nameof(WaitHelper.WithTimeout)}>");
        _methods++;
        foreach (var instruction in instructions)
        {
            if (instruction.opcode == OpCodes.Call && instruction.operand is MethodInfo method)
            {
                if (Sleeps.Contains(method))
                {
                    var parameters = method.GetParameters().Select(p => p.ParameterType).ToArray();
                    instruction.operand = AccessTools.Method(typeof(RunTiming), deadline ? nameof(Never) : nameof(Frame), parameters);
                    _calls++;
                }
                else if (Waits.TryGetValue(method, out var replacement))
                {
                    instruction.operand = replacement;
                    _calls++;
                }
            }
            yield return instruction;
        }
    }

    /// <summary>Harmony calls this once per patched method and once at the end, with no method.</summary>
    private static void Cleanup(MethodBase? original)
    {
        if (original is null)
        {
            Log.Info($"[{ModEntry.Id}] AutoSlay timing: {_calls} sleeps and waits replaced in {_methods} methods");
        }
    }

    public static Task Frame(int milliseconds) => FrameAsync(CancellationToken.None);
    public static Task Frame(int milliseconds, CancellationToken ct) => FrameAsync(ct);
    public static Task Frame(TimeSpan delay) => FrameAsync(CancellationToken.None);
    public static Task Frame(TimeSpan delay, CancellationToken ct) => FrameAsync(ct);

    private static async Task FrameAsync(CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        await Wait.NextFrame();
        ct.ThrowIfCancellationRequested();
    }

    public static Task Never(int milliseconds) => Task.Delay(Timeout.Infinite);
    public static Task Never(int milliseconds, CancellationToken ct) => Task.Delay(Timeout.Infinite, ct);
    public static Task Never(TimeSpan delay) => Task.Delay(Timeout.Infinite);
    public static Task Never(TimeSpan delay, CancellationToken ct) => Task.Delay(Timeout.Infinite, ct);

    /// <summary>Stands in for WaitHelper.Until: the same wait, checked once per frame, with no timeout.</summary>
    public static Task Until(Func<bool> condition, CancellationToken ct, TimeSpan? timeout = null, string? timeoutMessage = null) =>
        Wait.Until(condition, LogAfter, timeoutMessage ?? "an AutoSlay condition", ct);

    /// <summary>Stands in for WaitHelper.ForTask: waits for the task, checking once per frame, with no timeout.</summary>
    public static async Task ForTask(Task task, CancellationToken ct, TimeSpan? timeout = null, string? timeoutMessage = null)
    {
        await Wait.Until(() => task.IsCompleted, LogAfter, timeoutMessage ?? "an AutoSlay task", ct);
        await task;
    }
}

/// <summary>
/// In run mode, AutoSlay's watchdog, which fails a run after 30 seconds without what it counts as progress (such as
/// while the agent thinks), never fires.
/// </summary>
[HarmonyPatch(typeof(Watchdog), nameof(Watchdog.Check))]
internal static class NoWatchdog
{
    private static bool Prepare() => RunMode.IsOn;

    private static bool Prefix() => false;
}
