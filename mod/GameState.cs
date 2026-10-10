using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using HarmonyLib;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Context;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Localization.DynamicVars;
using MegaCrit.Sts2.Core.Map;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.MonsterMoves.Intents;
using MegaCrit.Sts2.Core.Rooms;
using MegaCrit.Sts2.Core.Runs;
using MegaCrit.Sts2.Core.Saves.Managers;

namespace SlayTheHuman;

/// <summary>
/// What a player can look up, as docs/protocol.md shapes it: the run, the map, the combat, and one card object for
/// every card wherever it appears.
/// </summary>
internal static class GameState
{
    public static Player Me() => LocalContext.GetMe(RunManager.Instance.DebugOnlyGetState())
        ?? throw new InvalidOperationException("no local player in the run");

    private static RunState CurrentRun() =>
        RunManager.Instance.DebugOnlyGetState() ?? throw new InvalidOperationException("no run in progress");

    /// <summary>
    /// A card: what it is, its numbers now (so a card that grew is seen grown), keywords, enchantment and affliction. In
    /// hand, also what it costs, whether it can be played, and its numbers after modifiers as the card in hand shows them.
    /// </summary>
    public static JsonObject Card(CardModel card, bool inHand = false)
    {
        var result = new JsonObject
        {
            ["id"] = card.Id.Entry, ["type"] = card.Type.ToString(), ["rarity"] = card.Rarity.ToString(),
            ["upgrade"] = card.CurrentUpgradeLevel,
            ["vars"] = Vars(card.DynamicVars.Values, v => v.BaseValue),
            ["keywords"] = new JsonArray(card.Keywords.Select(keyword => keyword.ToString())
                .OrderBy(name => name, StringComparer.Ordinal).Select(name => (JsonNode)name).ToArray()),
            ["enchantment"] = card.Enchantment is { } enchantment
                ? new JsonObject { ["id"] = enchantment.Id.Entry, ["amount"] = enchantment.Amount }
                : null,
            ["affliction"] = card.Affliction is { } affliction
                ? new JsonObject { ["id"] = affliction.Id.Entry, ["amount"] = affliction.Amount }
                : null,
        };
        if (inHand)
        {
            result["cost"] = card.EnergyCost.GetWithModifiers(CostModifiers.All);
            result["costs_x"] = card.EnergyCost.CostsX;
            result["star_cost"] = card.GetStarCostWithModifiers();
            result["target"] = card.TargetType.ToString();
            result["playable"] = card.CanPlay(out _, out _);
            // The game's own preview for a card in hand with no target, as its card UI computes it.
            card.DynamicVars.ClearPreview();
            card.UpdateDynamicVarPreview(CardPreviewMode.Normal, null, card.DynamicVars);
            result["preview"] = Vars(card.DynamicVars.Values, v => v.PreviewValue);
        }
        return result;
    }

    private static JsonObject Vars(IEnumerable<DynamicVar> vars, Func<DynamicVar, decimal> value)
    {
        var result = new JsonObject();
        foreach (var dynamicVar in vars)
        {
            result[dynamicVar.Name] = value(dynamicVar);
        }
        return result;
    }

    /// <summary>The run: the player, the deck, relics, potions, the act's boss, and the combats and kills so far.</summary>
    public static JsonObject Run()
    {
        var run = CurrentRun();
        var me = Me();
        return new JsonObject
        {
            ["character"] = me.Character.Id.Entry,
            ["hp"] = me.Creature.CurrentHp, ["max_hp"] = me.Creature.MaxHp, ["gold"] = me.Gold,
            ["ascension"] = run.AscensionLevel,
            ["act"] = run.CurrentActIndex + 1, ["floor"] = run.TotalFloor,
            ["boss"] = run.Act.BossEncounter?.Id.Entry, ["second_boss"] = run.Act.SecondBossEncounter?.Id.Entry,
            ["combats_won"] = RunCounters.CombatsWon, ["elites_killed"] = RunCounters.ElitesKilled,
            ["bosses_killed"] = RunCounters.BossesKilled,
            ["deck"] = new JsonArray(me.Deck.Cards.Select(card => (JsonNode)Card(card)).ToArray()),
            ["relics"] = new JsonArray(me.Relics
                .Select(relic => (JsonNode)new JsonObject
                {
                    ["id"] = relic.Id.Entry, ["counter"] = relic.ShowCounter ? relic.DisplayAmount : null,
                })
                .ToArray()),
            ["potions"] = new JsonArray(me.PotionSlots.Select(potion => potion is null
                ? null
                : (JsonNode)new JsonObject { ["id"] = potion.Id.Entry, ["target"] = potion.TargetType.ToString() })
                .ToArray()),
        };
    }

    /// <summary>Every point of the act's map, in the order the map's points and travel actions index: the start, the grid, the boss (or bosses).</summary>
    public static List<MapPoint> MapPoints(ActMap map)
    {
        var points = new List<MapPoint> { map.StartingMapPoint };
        points.AddRange(map.GetAllMapPoints());
        points.Add(map.BossMapPoint);
        if (map.SecondBossMapPoint is { } second)
        {
            points.Add(second);
        }
        return points.DistinctBy(point => point.coord).ToList();
    }

    /// <summary>The act's map: its points, the edges between them, and where the player is.</summary>
    public static JsonObject Map()
    {
        var run = CurrentRun();
        var points = MapPoints(run.Map);
        var index = points.Select((point, i) => (point.coord, i)).ToDictionary(pair => pair.coord, pair => pair.i);
        return new JsonObject
        {
            ["points"] = new JsonArray(points.Select(point => (JsonNode)new JsonObject
            {
                ["col"] = point.coord.col, ["row"] = point.coord.row, ["type"] = point.PointType.ToString(),
            }).ToArray()),
            ["edges"] = new JsonArray(points.SelectMany(point => point.Children
                    .Where(child => index.ContainsKey(child.coord))
                    .Select(child => (JsonNode)new JsonArray(index[point.coord], index[child.coord])))
                .ToArray()),
            ["current"] = run.CurrentMapCoord is { } here && index.TryGetValue(here, out var at) ? at : null,
        };
    }

    /// <summary>
    /// The combat, or null when none is in progress: the encounter, the turn, the player, the hand, the piles (as sets of
    /// cards, sorted so the draw pile's hidden order never shows) and the enemies.
    /// </summary>
    public static JsonObject? Combat()
    {
        var player = Me();
        if (!CombatManager.Instance.IsInProgress || player.PlayerCombatState is not { } combat ||
            player.Creature.CombatState is not { } combatState)
        {
            return null;
        }
        var me = player.Creature;
        return new JsonObject
        {
            ["encounter"] = combatState.Encounter?.Id.Entry,
            ["turn"] = combat.TurnNumber,
            ["player"] = new JsonObject
            {
                ["hp"] = me.CurrentHp, ["max_hp"] = me.MaxHp, ["block"] = me.Block,
                ["energy"] = combat.Energy, ["max_energy"] = combat.MaxEnergy, ["stars"] = combat.Stars,
                ["powers"] = Powers(me),
            },
            ["hand"] = new JsonArray(combat.Hand.Cards.Select(card => (JsonNode)Card(card, inHand: true)).ToArray()),
            ["draw"] = Pile(combat.DrawPile.Cards),
            ["discard"] = Pile(combat.DiscardPile.Cards),
            ["exhaust"] = Pile(combat.ExhaustPile.Cards),
            ["enemies"] = new JsonArray(combatState.Enemies.Select(enemy => (JsonNode)new JsonObject
            {
                ["id"] = enemy.Monster?.Id.Entry,
                ["combat_id"] = enemy.CombatId,
                ["alive"] = enemy.IsAlive,
                ["hp"] = enemy.CurrentHp, ["max_hp"] = enemy.MaxHp, ["block"] = enemy.Block,
                ["powers"] = Powers(enemy),
                ["intents"] = Intents(enemy),
            }).ToArray()),
        };
    }

    private static JsonArray Pile(IEnumerable<CardModel> cards) => new(cards
        .Select(card => Card(card))
        .OrderBy(card => card.ToJsonString(), StringComparer.Ordinal)
        .Select(card => (JsonNode)card)
        .ToArray());

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

/// <summary>The combats won and the elites and bosses killed this run, for the run state.</summary>
[HarmonyPatch(typeof(ProgressSaveManager), nameof(ProgressSaveManager.UpdateAfterCombatWon))]
internal static class RunCounters
{
    public static int CombatsWon { get; private set; }
    public static int ElitesKilled { get; private set; }
    public static int BossesKilled { get; private set; }

    private static bool Prepare() => RunMode.IsOn;

    /// <summary>At each run's start.</summary>
    public static void Reset() => CombatsWon = ElitesKilled = BossesKilled = 0;

    private static void Postfix(CombatRoom room)
    {
        CombatsWon++;
        if (room.RoomType == RoomType.Elite)
        {
            ElitesKilled++;
        }
        else if (room.RoomType == RoomType.Boss)
        {
            BossesKilled++;
        }
    }
}
