// The recommended-models card texts are written by the server (services/model_catalog.py, in English). They are listed
// here so the key tool puts them in en.json and the interface can show them translated; an unknown text (a newer
// server, a new model) is shown as it is. Built when shown: msg() needs the chosen language.
import { msg } from "@/i18n";

function catalogTexts() {
  return {
    "Tested with StoryCore": msg("Tested with StoryCore"),
    "Budget candidate": msg("Budget candidate"),
    "Low-cost candidate": msg("Low-cost candidate"),
    "Premium comparison": msg("Premium comparison"),
    "Used by this project's owner over hundreds of story turns": msg(
      "Used by this project's owner over hundreds of story turns",
    ),
    "Checked here for canon, structured scene analysis and dialogue": msg(
      "Checked here for canon, structured scene analysis and dialogue",
    ),
    "Strong hosted model without needing a powerful PC": msg("Strong hosted model without needing a powerful PC"),
    "Not perfect: time and weather can drift, and long sessions need watching": msg(
      "Not perfect: time and weather can drift, and long sessions need watching",
    ),
    "Reasoning and output limits can affect replies": msg("Reasoning and output limits can affect replies"),
    "Low listed token price": msg("Low listed token price"),
    "Large context window": msg("Large context window"),
    "Not yet tested in StoryCore: tone, formatting and scene analysis may differ": msg(
      "Not yet tested in StoryCore: tone, formatting and scene analysis may differ",
    ),
    "Availability and routing can change": msg("Availability and routing can change"),
    "Very low listed token price": msg("Very low listed token price"),
    "Useful for cheap experiments": msg("Useful for cheap experiments"),
    "Not yet tested in StoryCore for long roleplay": msg("Not yet tested in StoryCore for long roleplay"),
    "Endpoint availability can depend on your region": msg("Endpoint availability can depend on your region"),
    "A premium option for people who value it over price": msg("A premium option for people who value it over price"),
    "Much more expensive per token": msg("Much more expensive per token"),
    "Not verified as better for StoryCore storytelling": msg("Not verified as better for StoryCore storytelling"),
    "Not listed in OpenRouter's catalog right now.": msg("Not listed in OpenRouter's catalog right now."),
  };
}

/** A recommended-model text from the server, translated when it is one of the known ones. */
export function catalogText(text) {
  if (!text) return text;
  return catalogTexts()[text] ?? text;
}
