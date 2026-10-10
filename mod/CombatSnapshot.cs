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
using MegaCrit.Sts2.Core.MonsterMoves.Intents;
using MegaCrit.Sts2.Core.Runs;

namespace SlayTheHuman;

/// <summary>
/// A combat decision (docs/protocol.md): the combat state, the legal actions, and how to carry out each the way the
/// game's own UI does.
/// </summary>
internal static class CombatSnapshot
{
    public static Decision Take(Player player)
    {
        var combat = player.PlayerCombatState ?? throw new InvalidOperationException("the player is not in combat");
        var me = player.Creature;
        var enemies = me.CombatState?.Enemies ?? throw new InvalidOperationException("no combat state");
        var hand = combat.Hand.Cards;
        var decision = new Decision("combat");

        decision.State["turn"] = combat.TurnNumber;
        decision.State["player"] = new JsonObject
        {
            ["hp"] = me.CurrentHp, ["max_hp"] = me.MaxHp, ["block"] = me.Block,
            ["energy"] = combat.Energy, ["max_energy"] = combat.MaxEnergy, ["stars"] = combat.Stars,
            ["powers"] = Powers(me),
        };
        decision.State["hand"] = new JsonArray(hand.Select(card => (JsonNode)new JsonObject
        {
            ["id"] = card.Id.Entry,
            ["upgraded"] = card.IsUpgraded,
            ["cost"] = card.EnergyCost.GetWithModifiers(CostModifiers.All),
            ["costs_x"] = card.EnergyCost.CostsX,
            ["star_cost"] = card.GetStarCostWithModifiers(),
            ["type"] = card.Type.ToString(),
            ["target"] = card.TargetType.ToString(),
            ["playable"] = card.CanPlay(out _, out _),
        }).ToArray());
        decision.State["draw"] = combat.DrawPile.Cards.Count;
        decision.State["discard"] = combat.DiscardPile.Cards.Count;
        decision.State["exhaust"] = combat.ExhaustPile.Cards.Count;
        decision.State["enemies"] = new JsonArray(enemies.Select(enemy => (JsonNode)new JsonObject
        {
            ["id"] = enemy.Monster?.Id.Entry,
            ["alive"] = enemy.IsAlive,
            ["hp"] = enemy.CurrentHp, ["max_hp"] = enemy.MaxHp, ["block"] = enemy.Block,
            ["powers"] = Powers(enemy),
            ["intents"] = Intents(enemy),
        }).ToArray());

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

    private static JsonArray Powers(Creature creature) => new(creature.Powers
        .Where(power => power.IsVisible)
        .Select(power => (JsonNode)new JsonObject { ["id"] = power.Id.Entry, ["amount"] = power.Amount })
        .ToArray());

    private static JsonArray Intents(Creature enemy)
    {
        if (!enemy.IsAlive || enemy.Monster is null)
        {
            return new JsonArray();
        }
        return new JsonArray(enemy.Monster.NextMove.Intents.Select(intent => (JsonNode)(intent switch
        {
            // A hidden intent shows the player nothing, so it gives the agent nothing either.
            HiddenIntent => new JsonObject { ["type"] = "Hidden", ["damage"] = null, ["hits"] = null },
            AttackIntent attack => new JsonObject
            {
                ["type"] = attack.IntentType.ToString(),
                ["damage"] = attack.GetSingleDamage(Array.Empty<Creature>(), enemy),
                ["hits"] = attack.Repeats,
            },
            _ => new JsonObject { ["type"] = intent.IntentType.ToString(), ["damage"] = null, ["hits"] = null },
        })).ToArray());
    }
}
