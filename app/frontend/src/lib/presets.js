// v0.6: names of the built-in narration presets, translated when shown. A preset the player created or renamed keeps
// the name they typed. (msg() is called inside the function, never when the file loads: the language can change.)
import { msg } from "@/i18n";

export const DEFAULT_PRESET_ID = `cinematic`;

export function presetName(preset) {
  if (!preset) return ``;
  let builtIn = {
    balanced: [`Balanced`, msg("Balanced")],
    literary: [`Literary`, msg("Literary")],
    fast: [`Fast`, msg("Fast")],
    dark_fantasy: [`Dark Fantasy`, msg("Dark Fantasy")],
    cinematic: [`Cinematic`, msg("Cinematic")],
  }[preset.id];
  return builtIn && preset.name === builtIn[0] ? builtIn[1] : preset.name;
}
