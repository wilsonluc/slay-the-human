using System;
using System.Linq;
using HarmonyLib;
using MegaCrit.Sts2.Core.Nodes.Screens.CharacterSelect;

namespace SlayTheHuman;

/// <summary>
/// In run mode, selects the character the agent asked for (<see cref="RunMode.Character"/>) whenever a character
/// button is selected, instead of the one AutoSlay drew at random.
/// </summary>
[HarmonyPatch(typeof(NCharacterSelectButton), nameof(NCharacterSelectButton.Select))]
internal static class ChooseCharacter
{
    private static bool Prepare() => RunMode.IsOn;

    private static bool Prefix(NCharacterSelectButton __instance)
    {
        if (__instance.Character?.Id.Entry == RunMode.Character)
        {
            return true;
        }
        var buttons = __instance.GetParent().GetChildren().OfType<NCharacterSelectButton>().ToList();
        var wanted = buttons.FirstOrDefault(button => button.Character?.Id.Entry == RunMode.Character)
            ?? throw new InvalidOperationException(
                $"no character {RunMode.Character}; the game offers " +
                string.Join(", ", buttons.Select(button => button.Character?.Id.Entry).OfType<string>()));
        if (wanted.IsLocked)
        {
            throw new InvalidOperationException($"character {RunMode.Character} is locked");
        }
        wanted.Select();
        return false;
    }
}
