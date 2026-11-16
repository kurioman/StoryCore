"""Application settings stored in ``app_settings`` with typed defaults."""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session

from ..models import AppSetting

# New-story defaults (v1.6.2). The limit is a ceiling, not a target: a hosted model is billed for what it writes, and the output
# length below is what shapes a reply. Local models keep LOCAL_MAX_OUTPUT_TOKENS: on them it comes out of a small context window.
DEFAULT_OUTPUT_LENGTH = "medium (3–4 paragraphs)"
DEFAULT_MAX_OUTPUT_TOKENS = 3000
LOCAL_MAX_OUTPUT_TOKENS = 1024
# v1.6.4: from this window a local model can afford the full ceiling; below it (or unknown) 3,000 would come out of the story
ROOMY_LOCAL_WINDOW = 16384

NARRATION_PRESETS = [
    {"id": "balanced", "name": "Balanced", "instructions": "Write vivid but economical prose (2–5 paragraphs). Balance dialogue, action and description."},
    {"id": "literary", "name": "Literary", "instructions": "Write rich, literary prose with careful imagery, interiority for NPCs, and deliberate pacing."},
    {"id": "fast", "name": "Fast", "instructions": "Keep responses short and punchy (1–2 paragraphs). Prioritise momentum and dialogue."},
    {"id": "dark_fantasy", "name": "Dark Fantasy", "instructions": "Lean into tension, dread, moral ambiguity and real danger while staying grounded in established lore."},
]

# v1.8: no generic openings any more. A story's openings come only from its lore pack (pack.json starters or its
# scenarios files), chosen by the pack's author. The setting stays (empty) so older stored values are harmless.
STARTER_PRESETS: list[dict] = []

# v1.6.4: scene analysis, suggestions, portraits and relationship tracking are all on by default and each can be changed
# afterwards. A stored value is the player's choice and is always honoured; only a missing setting takes these defaults.
ANALYSIS_MODES = ("always", "local_only", "off")  # always is shown as "Automatic"; it is the value older versions stored
RELATIONSHIP_MODES = ("auto_conservative", "review", "off")

DEFAULTS: dict[str, Any] = {
    "default_model_profile_id": None,
    "extraction_model_source": "narration",  # narration | separate | none
    "extraction_model_profile_id": None,
    "event_capture_mode": "batch",  # off | manual | batch | after_each_turn
    "event_capture_batch_turns": 3,
    "event_auto_store_status": "recorded_unverified",  # recorded_unverified | confirmed_from_transcript | candidate
    "candidate_confidence_threshold": 0.6,
    "state_change_policy": "review",  # review (always ask) | auto_minor (auto-apply scene/expression only)
    "auto_apply_expression_suggestions": True,
    # post-turn analysis (speakers/expressions, suggested replies, relationships, discovery, scene details):
    # always (shown as Automatic: every provider, hosted ones included) | local_only | off
    "turn_analysis_mode": "always",
    # relationship changes found by the post-turn analysis: auto_conservative (small, confident, evidenced changes apply at once
    # and are reversible; the rest goes to the review queue) | review (all to the queue) | off (none are evaluated or applied)
    "relationship_mode": "auto_conservative",
    # narrator prompt profile (context_builder.PROMPT_PROFILES); None = the built-in default. Stories may override it.
    "narrator_prompt_profile": None,
    "action_suggestions_enabled": False,  # v1.7: off by default (shorter scene analysis); on in Settings > Memory capture
    # v1.7 portrait tags: the narrator writes [Name:N] before a character's spoken line; the portrait shows at once
    "portrait_tags_enabled": True,
    "show_scene_portraits": True,  # above the message box
    "inline_portraits": True,  # inside the story text at their verified speaking/reaction beats
    "story_font": "sans",  # sans (v1.3 default: long-reading comfort) | serif (the earlier book style)
    "context_budget_tokens": 10000,
    # a planning figure taken out of the budget, never sent to the model: max_tokens is what limits a reply
    "reserve_output_tokens": 2000,
    "recent_messages_min": 6,
    "context_warning_ratio": 0.85,
    "auto_recap_policy": "offer",  # off | offer
    "recap_auto_replace": False,
    "enter_to_send": True,
    "theme": "dark",
    # v1.8: language of the story text (narration and dialogue): en | fr. Stories may override it (settings_json).
    "narration_language": "en",
    # in-app corrections layered over each world's pack.json (scoped by a "world" slug): post holders (services/roles.py)
    # and kinship, family branches and gatherings (services/canon.py), verified against lore at use
    "role_assignments": [],
    "canon_facts": [],
    # v1.5 reading: "emphasis" = speaker labels and a thin accent rule on dialogue paragraphs; "classic" = v1.4 styling
    "dialogue_style": "emphasis",
    # v1.6 story text size: compact (the size before v1.6) | comfortable | large
    "reading_size": "comfortable",
    "narration_presets": NARRATION_PRESETS,
    "starter_presets": STARTER_PRESETS,
    "default_system_prompt": (
        "You are the narrator and world simulator for an interactive story. The user controls the protagonist: never "
        "write the protagonist's dialogue, decisions, thoughts or feelings unless the user provided them. Treat user "
        "actions as attempts and resolve outcomes plausibly. Run NPCs with consistent motives and knowledge limits — "
        "a character only knows what they witnessed, were told, or could reasonably infer. Respect established facts, "
        "state and lore. End at a natural point for the player to act."
    ),
    "onboarding_dismissed": False,
    "last_backup_at": None,
}


def get_all(db: Session) -> dict[str, Any]:
    out = copy.deepcopy(DEFAULTS)
    for row in db.query(AppSetting).all():
        out[row.key] = row.value_json
    return out


def get(db: Session, key: str) -> Any:
    row = db.get(AppSetting, key)
    return row.value_json if row is not None else copy.deepcopy(DEFAULTS.get(key))


def set_many(db: Session, values: dict[str, Any]) -> dict[str, Any]:
    for k, v in values.items():
        row = db.get(AppSetting, k)
        if row is None:
            db.add(AppSetting(key=k, value_json=v))
        else:
            row.value_json = v
    db.flush()
    return get_all(db)
