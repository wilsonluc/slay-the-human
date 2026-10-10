using System;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.AutoSlay.Handlers.Rooms;
using MegaCrit.Sts2.Core.AutoSlay.Helpers;
using MegaCrit.Sts2.Core.Entities.Merchant;
using MegaCrit.Sts2.Core.Nodes.CommonUi;
using MegaCrit.Sts2.Core.Nodes.Events.Custom;
using MegaCrit.Sts2.Core.Nodes.Rooms;
using MegaCrit.Sts2.Core.Nodes.Screens;
using MegaCrit.Sts2.Core.Nodes.Screens.Map;
using MegaCrit.Sts2.Core.Nodes.Screens.Overlays;
using MegaCrit.Sts2.Core.Nodes.Screens.Shops;

namespace SlayTheHuman;

/// <summary>
/// In run mode with an agent, the agent shops: it buys what it chooses, one item at a time, and leaves when it
/// chooses. AutoSlay buys at random until its gold runs out and never removes a card.
/// </summary>
[HarmonyPatch(typeof(ShopRoomHandler), nameof(ShopRoomHandler.HandleAsync))]
internal static class AgentShop
{
    private static readonly TimeSpan OpenTimeout = TimeSpan.FromSeconds(10);
    private static readonly TimeSpan ResultTimeout = TimeSpan.FromSeconds(60);
    private static readonly TimeSpan RelicTimeout = TimeSpan.FromSeconds(60);

    private static readonly AccessTools.FieldRef<NMerchantInventory, bool> InputBlocked =
        AccessTools.FieldRefAccess<NMerchantInventory, bool>("_isInputBlocked");

    private static bool Prepare() => RunMode.WithAgent;

    private static bool Prefix(CancellationToken ct, ref Task __result)
    {
        __result = ShopAsync(ct);
        return false;
    }

    private static async Task ShopAsync(CancellationToken ct)
    {
        var root = ((SceneTree)Engine.GetMainLoop()).Root;
        NMerchantRoom? room = null;
        await Wait.Until(() => (room = root.GetNodeOrNull<NMerchantRoom>("/root/Game/RootSceneContainer/Run/RoomContainer/MerchantRoom"))
            is not null && room.IsVisibleInTree(), OpenTimeout, "the shop", ct);
        room!.OpenInventory();
        await Wait.Until(() => room.Inventory.IsOpen, OpenTimeout, "the shop's inventory to open", ct);
        // A relic can shop first: Lord's Parasol buys everything on entry, with the shop's input blocked and travel
        // off until it is done. A player can do nothing meanwhile, so neither can the agent.
        await Wait.NextFrame();
        await Wait.Until(() => !InputBlocked(room.Inventory) && (NMapScreen.Instance?.IsTravelEnabled ?? false),
            RelicTimeout, "the shop to accept input", ct);
        await ChooseAsync(room.Inventory, room, room.ProceedButton, ct);
    }

    /// <summary>
    /// The shop decision, for the shop and for the FakeMerchant event's shop: buy any stocked item the player can
    /// afford, or leave through the back button and the given proceed button.
    /// </summary>
    public static async Task ChooseAsync(NMerchantInventory inventory, Node owner, NProceedButton proceed,
        CancellationToken ct)
    {
        var left = false;
        while (!left)
        {
            ct.ThrowIfCancellationRequested();
            var slots = inventory.GetAllSlots().ToList();
            var hasPotionSlot = Decision.Me().HasOpenPotionSlots;
            var decision = new Decision("shop");
            decision.State["items"] = new JsonArray(slots.Select(slot => (JsonNode)Describe(slot.Entry)).ToArray());
            for (var i = 0; i < slots.Count; i++)
            {
                var entry = slots[i].Entry;
                if (entry.IsStocked && entry.EnoughGold && (entry is not MerchantPotionEntry || hasPotionSlot))
                {
                    decision.Add(new JsonObject { ["kind"] = "buy", ["item"] = i }, () => BuyAsync(inventory, entry, ct));
                }
            }
            decision.Add(new JsonObject { ["kind"] = "leave" }, async () =>
            {
                left = true;
                if (UiHelper.FindFirst<NBackButton>(owner) is { } back && inventory.IsOpen)
                {
                    await UiHelper.Click(back);
                }
                // A forced click: the FakeMerchant's button can read as disabled while its screen is not the active one.
                await UiHelper.Click(proceed);
                await Wait.Until(() => NMapScreen.Instance?.IsOpen ?? false, OpenTimeout, "the map after leaving the shop", ct);
            });
            await decision.RunAsync(ct);
        }
    }

    /// <summary>Buys an item the way its slot does. A relic that opens a rewards screen on pickup is answered here.</summary>
    private static async Task BuyAsync(NMerchantInventory inventory, MerchantEntry entry, CancellationToken ct)
    {
        var item = Describe(entry).ToJsonString();
        MegaCrit.Sts2.Core.Logging.Log.Info($"[{ModEntry.Id}] buying {item}");
        if (!entry.IsStocked || !entry.EnoughGold)
        {
            throw new InvalidOperationException($"the shop item is no longer for sale: {item}");
        }
        if (entry is MerchantCardRemovalEntry removal)
        {
            // The removal slot's own overload; the card choice reaches the agent through the card selector.
            await removal.OnTryPurchaseWrapper(inventory.Inventory);
        }
        else
        {
            await entry.OnTryPurchaseWrapper(inventory.Inventory);
        }
        if (NOverlayStack.Instance?.Peek() is NRewardsScreen rewards)
        {
            await AgentRewards.ChooseAsync(rewards, ct);
            await Wait.Until(() => (NOverlayStack.Instance?.ScreenCount ?? 0) == 0 || NOverlayStack.Instance?.Peek() != rewards,
                ResultTimeout, "the rewards screen from a purchase to close", ct);
        }
        else if (NOverlayStack.Instance?.Peek() is { } other)
        {
            throw new InvalidOperationException($"a purchase opened a screen the agent cannot answer: {other.GetType().Name}");
        }
    }

    private static JsonObject Describe(MerchantEntry entry)
    {
        var (type, id, onSale) = entry switch
        {
            MerchantCardEntry card => ("card", card.CreationResult?.Card.Id.Entry, card.IsOnSale),
            MerchantRelicEntry relic => ("relic", relic.Model?.Id.Entry, false),
            MerchantPotionEntry potion => ("potion", potion.Model?.Id.Entry, false),
            MerchantCardRemovalEntry => ("card_removal", null, false),
            _ => ("other", (string?)null, false),
        };
        return new JsonObject
        {
            ["type"] = type, ["id"] = id, ["cost"] = entry.Cost, ["on_sale"] = onSale, ["stocked"] = entry.IsStocked,
            ["card"] = entry is MerchantCardEntry { CreationResult.Card: { } model } ? GameState.Card(model) : null,
        };
    }
}

/// <summary>
/// In run mode with an agent, the FakeMerchant event's shop of fake relics goes through the shop decision. AutoSlay
/// only waits for its proceed button, which the game disables while that screen is not the active one, so it times out.
/// </summary>
[HarmonyPatch(typeof(EventRoomHandler), "HandleFakeMerchantEvent")]
internal static class AgentFakeMerchant
{
    private static readonly TimeSpan OpenTimeout = TimeSpan.FromSeconds(10);

    private static bool Prepare() => RunMode.WithAgent;

    private static bool Prefix(NFakeMerchant fakeMerchant, CancellationToken ct, ref Task __result)
    {
        __result = ShopAsync(fakeMerchant, ct);
        return false;
    }

    private static async Task ShopAsync(NFakeMerchant merchant, CancellationToken ct)
    {
        await UiHelper.Click(merchant.MerchantButton);
        await Wait.Until(() => merchant.Inventory.IsOpen, OpenTimeout, "the FakeMerchant's inventory to open", ct);
        var proceed = merchant.GetNodeOrNull<NProceedButton>("%ProceedButton")
            ?? throw new InvalidOperationException("the FakeMerchant has no proceed button");
        await AgentShop.ChooseAsync(merchant.Inventory, merchant, proceed, ct);
    }
}
