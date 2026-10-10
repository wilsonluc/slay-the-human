using System;
using System.Collections.Generic;
using System.Linq;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Localization;
using MegaCrit.Sts2.Core.Map;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.MonsterMoves.Intents;

namespace SlayTheHuman;

/// <summary>
/// Every name the game can put in the state, as CATEGORY.ENTRY keys, sent in the mod's hello so the agent can check its
/// vocabulary covers the running build: every game model (cards, relics, potions, monsters, encounters, powers, events,
/// enchantments, afflictions and the rest) by its model ID; the game enums the state sends; and the names the game keeps
/// only in its text tables (event pages and options, rest site options, card reward alternatives), and each ancient event.
/// </summary>
internal static class Vocabulary
{
    public static List<string> Keys()
    {
        var keys = new SortedSet<string>(StringComparer.Ordinal);
        var events = new List<EventModel>();
        foreach (var type in ModelDb.AllAbstractModelSubtypes)
        {
            // Abstract bases and the game's own test models never appear in a run.
            if (type.IsAbstract || type.ContainsGenericParameters || type.Namespace is not { } ns ||
                ns.Contains(".Mock") || ns.Contains(".Test"))
            {
                continue;
            }
            keys.Add(ModelDb.GetId(type).ToString());
            // Every event, including those outside the acts' lists, such as Neow.
            if (type.IsSubclassOf(typeof(EventModel)) && ModelDb.GetByIdOrNull<EventModel>(ModelDb.GetId(type)) is { } model)
            {
                events.Add(model);
            }
        }
        AddEnum<CardType>(keys, "CARD_TYPE");
        AddEnum<CardRarity>(keys, "CARD_RARITY");
        AddEnum<CardKeyword>(keys, "KEYWORD");
        AddEnum<TargetType>(keys, "TARGET");
        AddEnum<IntentType>(keys, "INTENT");
        AddEnum<MapPointType>(keys, "MAP_POINT");
        foreach (var model in events)
        {
            // An ancient (Neow and the like) keeps no page or option text, only dialogue: its options are relics, which
            // the state names. Its pages and options all go by the ancient's own key.
            if (model is AncientEventModel)
            {
                keys.Add("ANCIENT." + model.Id.Entry);
                continue;
            }
            // A page's key ends in .description; an option's text key is its keys' common stem. An option that grants a
            // relic is named after the relic at run time (<EVENT>.pages.<PAGE>.options.<RELIC>), so its page's options
            // stem stands for it, with the relic named beside it.
            var prefix = model.Id.Entry + ".pages.";
            foreach (var key in LocManager.Instance.GetTable(model.LocTable).Keys.Where(key => key.StartsWith(prefix)))
            {
                keys.Add("EVENT_TEXT." + key);
                keys.Add("EVENT_TEXT." + key[..key.LastIndexOf('.')]);
                var page = key.IndexOf('.', prefix.Length);
                if (page > 0)
                {
                    keys.Add($"EVENT_TEXT.{key[..page]}.options");
                }
            }
        }
        AddOptions(keys, "rest_site_ui", "REST_OPTION");
        AddOptions(keys, "card_reward_ui", "CARD_REWARD_ALTERNATIVE");
        return keys.ToList();
    }

    private static void AddEnum<T>(SortedSet<string> keys, string category) where T : struct, Enum
    {
        foreach (var name in Enum.GetNames<T>())
        {
            keys.Add($"{category}.{name}");
        }
    }

    /// <summary>The option IDs in a text table's OPTION_&lt;ID&gt;.* keys, upper case, as the game names its options.</summary>
    private static void AddOptions(SortedSet<string> keys, string table, string category)
    {
        foreach (var key in LocManager.Instance.GetTable(table).Keys.Where(key => key.StartsWith("OPTION_") && key.Contains('.')))
        {
            keys.Add($"{category}.{key["OPTION_".Length..key.IndexOf('.')].ToUpperInvariant()}");
        }
    }
}
