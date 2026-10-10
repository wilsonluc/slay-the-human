using System;
using System.Linq;
using System.Text.Json.Nodes;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Entities.Potions;
using MegaCrit.Sts2.Core.GameActions;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Runs;

namespace SlayTheHuman;

/// <summary>
/// A combat decision (docs/protocol.md): the combat state (<see cref="GameState.Combat"/>), the legal actions, and how
/// to carry out each the way the game's own UI does.
/// </summary>
internal static class CombatSnapshot
{
    public static Decision Take(Player player)
    {
        var combat = player.PlayerCombatState ?? throw new InvalidOperationException("the player is not in combat");
        var me = player.Creature;
        var enemies = me.CombatState?.Enemies ?? throw new InvalidOperationException("no combat state");
        var hand = combat.Hand.Cards;
        var decision = new Decision("combat", GameState.Combat() ?? throw new InvalidOperationException("no combat in progress"));

        for (var i = 0; i < hand.Count; i++)
        {
            var card = hand[i];
            var cardIndex = i;
            if (card.TargetType == TargetType.AnyEnemy)
            {
                for (var e = 0; e < enemies.Count; e++)
                {
                    var target = enemies[e];
                    if (card.CanPlayTargeting(target))
                    {
                        decision.Add(new JsonObject { ["kind"] = "play", ["card"] = cardIndex, ["target"] = e },
                            () => Play(card, target));
                    }
                }
            }
            else if (card.TargetType != TargetType.AnyAlly && card.CanPlayTargeting(null))
            {
                // Every other target type is played with no target; an ally target needs another player.
                decision.Add(new JsonObject { ["kind"] = "play", ["card"] = cardIndex, ["target"] = null },
                    () => Play(card, null));
            }
        }

        for (var slot = 0; slot < player.PotionSlots.Count; slot++)
        {
            var potion = player.PotionSlots[slot];
            var slotIndex = slot;
            if (potion is null || !CanUse(potion, player))
            {
                continue;
            }
            if (potion.TargetType == TargetType.AnyEnemy)
            {
                for (var e = 0; e < enemies.Count; e++)
                {
                    var target = enemies[e];
                    if (potion.IsValidTarget(target))
                    {
                        decision.Add(new JsonObject { ["kind"] = "potion", ["slot"] = slotIndex, ["target"] = e },
                            () => potion.EnqueueManualUse(target));
                    }
                }
            }
            else if (potion.IsValidTarget(null) || potion.IsValidTarget(me))
            {
                // With no target, the game fills in the player for potions aimed at themself.
                decision.Add(new JsonObject { ["kind"] = "potion", ["slot"] = slotIndex, ["target"] = null },
                    () => potion.EnqueueManualUse(null));
            }
        }

        var turn = combat.TurnNumber;
        decision.Add(new JsonObject { ["kind"] = "end_turn" },
            () => RunManager.Instance.ActionQueueSynchronizer.RequestEnqueue(new EndPlayerTurnAction(player, turn)));
        return decision;
    }

    private static void Play(CardModel card, Creature? target)
    {
        if (!card.TryManualPlay(target))
        {
            throw new BridgeException($"the game refused to play {card.Id.Entry}");
        }
    }

    /// <summary>The checks the game's potion popup makes before it enables the use button.</summary>
    private static bool CanUse(PotionModel potion, Player player)
    {
        if (potion.IsQueued || !player.Creature.IsAlive || potion.Usage == PotionUsage.Automatic ||
            !player.CanRemovePotions || !potion.PassesCustomUsabilityCheck)
        {
            return false;
        }
        return potion.Usage != PotionUsage.CombatOnly ||
            (CombatManager.Instance.IsInProgress &&
             player.Creature.CombatState?.CurrentSide == player.Creature.Side &&
             !CombatManager.Instance.PlayerActionsDisabled);
    }

}
