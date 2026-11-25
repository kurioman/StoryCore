// The recommended-models card texts are written by the server (services/model_catalog.py, in English). They are listed
// here so the key tool puts them in en.json and the interface can show them translated; an unknown text (a newer
// server, a new model) is shown as it is. Built when shown: msg() needs the chosen language.
import { msg } from "@/i18n";

function catalogTexts() {
  return {
    "Recommended": msg("Recommended"),
    "Low price, high quality": msg("Low price, high quality"),
    "Best quality": msg("Best quality"),
    "For French roleplay": msg("For French roleplay"),
    "Low price": msg("Low price"),
    "Very, very low price for high quality": msg("Very, very low price for high quality"),
    "Tested and recommended with StoryCore": msg("Tested and recommended with StoryCore"),
    "Follows the latest version of the model, so it can change over time": msg("Follows the latest version of the model, so it can change over time"),
    "Low price for high quality": msg("Low price for high quality"),
    "Not yet tested in StoryCore": msg("Not yet tested in StoryCore"),
    "Best writing quality": msg("Best writing quality"),
    "High price": msg("High price"),
    "A good choice to play in French": msg("A good choice to play in French"),
    "Not listed in OpenRouter's catalog right now.": msg("Not listed in OpenRouter's catalog right now."),
  };
}

/** A recommended-model text from the server, translated when it is one of the known ones. */
export function catalogText(text) {
  if (!text) return text;
  return catalogTexts()[text] ?? text;
}
