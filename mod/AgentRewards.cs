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
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Nodes.CommonUi;
using MegaCrit.Sts2.Core.Nodes.Rewards;
using MegaCrit.Sts2.Core.Nodes.Screens;
using MegaCrit.Sts2.Core.Nodes.Screens.CardSelection;
using MegaCrit.Sts2.Core.Nodes.Screens.Map;
using MegaCrit.Sts2.Core.Nodes.Screens.Overlays;
using MegaCrit.Sts2.Core.Rewards;

namespace SlayTheHuman;

/// <summary>
/// In run mode with an agent, the agent takes rewards one at a time and chooses when to move on. AutoSlay takes them
/// all in screen order. A card reward's own screen is answered by <see cref="AgentCardReward"/>.
/// </summary>
[HarmonyPatch(typeof(RewardsScreenHandler), nameof(RewardsScreenHandler.HandleAsync))]
internal static class AgentRewards
{
    private static readonly TimeSpan ClaimTimeout = TimeSpan.FromSeconds(10);
    private static readonly TimeSpan ChildTimeout = TimeSpan.FromSeconds(60);
    private static readonly TimeSpan CloseTimeout = TimeSpan.FromSeconds(10);

    private static readonly AccessTools.FieldRef<SpecialCardReward, CardModel?> SpecialCard =
        AccessTools.FieldRefAccess<SpecialCardReward, CardModel?>("_card");

    private static bool Prepare() => RunMode.WithAgent;

    private static bool Prefix(CancellationToken ct, ref Task __result)
    {
        __result = ChooseAsync(AutoSlayer.GetCurrentScreen<NRewardsScreen>(), ct);
        return false;
    }

    /// <summary>Takes rewards from the screen until the agent proceeds. Also used when a purchase opens one.</summary>
    public static async Task ChooseAsync(NRewardsScreen screen, CancellationToken ct)
    {
        var done = false;
        while (!done)
        {
            ct.ThrowIfCancellationRequested();
            // After a reward is taken the screen can briefly offer nothing; wait until it closes or offers a choice.
            await Wait.Until(() => !Alive(screen) || Takeable(screen).Any() ||
                UiHelper.FindFirst<NProceedButton>(screen) is { IsEnabled: true }, CloseTimeout,
                "the rewards screen to offer a reward or proceed", ct);
            if (!Alive(screen))
            {
                return;
            }
            var buttons = UiHelper.FindAll<NRewardButton>(screen)
                .Where(button => button.Reward is not null && button.IsVisibleInTree()).ToList();
            var takeable = Takeable(screen).ToHashSet();
            var sets = UiHelper.FindAll<NLinkedRewardSet>(screen);
            var decision = new Decision("reward");
            decision.State["rewards"] = new JsonArray(buttons.Select(button => (JsonNode)Describe(button, sets)).ToArray());
            for (var i = 0; i < buttons.Count; i++)
            {
                var button = buttons[i];
                if (takeable.Contains(button))
                {
                    decision.Add(new JsonObject { ["kind"] = "take", ["reward"] = i }, () => TakeAsync(screen, button, ct));
                }
            }
            if (UiHelper.FindFirst<NProceedButton>(screen) is { IsEnabled: true } proceed)
            {
                decision.Add(new JsonObject { ["kind"] = "proceed" }, async () =>
                {
                    done = true;
                    await UiHelper.Click(proceed);
                    await Wait.Until(() => !GodotObject.IsInstanceValid(screen) || NOverlayStack.Instance?.Peek() != screen ||
                        (NMapScreen.Instance?.IsOpen ?? false), CloseTimeout, "the rewards screen to close", ct);
                });
            }
            await decision.RunAsync(ct);
        }
    }

    /// <summary>Takes a reward. A card reward opens its own screen, which is waited out here.</summary>
    private static async Task TakeAsync(NRewardsScreen screen, NRewardButton button, CancellationToken ct)
    {
        // The button says when the reward is settled: claimed, or given back (a card reward whose cards were skipped).
        var settled = false;
        void OnSettled(NRewardButton _) => settled = true;
        button.RewardClaimed += OnSettled;
        button.RewardSkipped += OnSettled;
        try
        {
            await UiHelper.Click(button);
            await Wait.Until(() => settled || NOverlayStack.Instance?.Peek() != screen, ClaimTimeout,
                "the reward to be claimed or open its screen", ct);
            if (NOverlayStack.Instance?.Peek() is NCardRewardSelectionScreen cardScreen)
            {
                await Wait.Until(() => !GodotObject.IsInstanceValid(cardScreen) || !cardScreen.IsVisibleInTree(),
                    ChildTimeout, "the card reward screen to close", ct);
            }
            else if (!settled && Alive(screen) && NOverlayStack.Instance?.Peek() is { } other && other != screen)
            {
                throw new InvalidOperationException($"a reward opened a screen the agent cannot answer: {other.GetType().Name}");
            }
            await Wait.Until(() => settled, ClaimTimeout, "the reward to be claimed or given back", ct);
        }
        finally
        {
            if (GodotObject.IsInstanceValid(button))
            {
                button.RewardClaimed -= OnSettled;
                button.RewardSkipped -= OnSettled;
            }
        }
    }

    /// <summary>The rewards that can be taken now: enabled, and a potion only with a free potion slot.</summary>
    private static System.Collections.Generic.IEnumerable<NRewardButton> Takeable(NRewardsScreen screen)
    {
        var hasPotionSlot = Decision.Me().HasOpenPotionSlots;
        return UiHelper.FindAll<NRewardButton>(screen).Where(button => button.Reward is not null &&
            button.IsVisibleInTree() && button.IsEnabled && (button.Reward is not PotionReward || hasPotionSlot));
    }

    private static bool Alive(NRewardsScreen screen) => GodotObject.IsInstanceValid(screen) && screen.IsVisibleInTree();

    private static JsonObject Describe(NRewardButton button, System.Collections.Generic.List<NLinkedRewardSet> sets)
    {
        var reward = button.Reward!;
        var group = sets.FindIndex(set => set.IsAncestorOf(button));
        var (type, id, amount) = reward switch
        {
            GoldReward gold => ("gold", null, (int?)gold.Amount),
            PotionReward potion => ("potion", potion.Potion?.Id.Entry, null),
            RelicReward relic => ("relic", relic.Relic?.Id.Entry, null),
            SpecialCardReward special => ("special_card", SpecialCard(special)?.Id.Entry, null),
            CardReward => ("card", null, null),
            CardRemovalReward => ("card_removal", null, null),
            _ => ("other", (string?)null, (int?)null),
        };
        return new JsonObject
        {
            ["type"] = type, ["id"] = id, ["amount"] = amount, ["group"] = group >= 0 ? group : null,
        };
    }
}
