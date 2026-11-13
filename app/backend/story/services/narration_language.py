"""Language of the story text (v1.8): English by default, French as an option.

Only what the player reads changes language: the narration and dialogue. Everything the engine parses stays as it is:
portrait tags ([Selphina:3]), character and place names as the lore writes them, and the JSON of the scene analysis.
The lore and the instructions stay in English; the model is told to write its reply in the chosen language anyway.

Setting: ``narration_language`` (app setting, default "en"); a story can override it in its settings
(``settings_json.narration_language``; None or missing = the app setting).
"""
from __future__ import annotations

from typing import Any

LANGUAGES: dict[str, str] = {"en": "English", "fr": "French"}
DEFAULT = "en"


def of(cfg: dict[str, Any], story_settings: dict[str, Any] | None) -> str:
    code = (story_settings or {}).get("narration_language") or cfg.get("narration_language") or DEFAULT
    return code if code in LANGUAGES else DEFAULT


def instruction(code: str) -> str:
    """System-prompt section for a non-English story; empty for English (the prompts are written in English)."""
    if code == DEFAULT or code not in LANGUAGES:
        return ""
    lang = LANGUAGES[code]
    extra = {
        "fr": " Use natural, literary French with correct accents, French typography for dialogue (« … » or the dash), "
              "and the formal or informal address (vous / tu) that fits each relationship.",
    }.get(code, "")
    return (f"Write the whole story text in {lang}: narration, descriptions and every line of dialogue. The lore, the notes "
            f"and these instructions are in English; that does not change the language of your reply.{extra} Keep "
            "character names, place names and titles exactly as the lore writes them (do not translate or adapt them). "
            "Keep every portrait tag exactly in its format [Name:N], with the name as the lore writes it. When an opening "
            f"asks you to reproduce an author's text, translate it faithfully into {lang}, keeping every portrait tag and "
            "the order of the lines. If the player writes in another language, still answer in "
            f"{lang}.")


def reminder(code: str) -> str:
    """Short per-turn note added after the player's message (small models follow it better than a system rule)."""
    if code == DEFAULT or code not in LANGUAGES:
        return ""
    return f" (Write your reply in {LANGUAGES[code]}.)"
