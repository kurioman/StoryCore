"""Rewrite one paragraph of a reply (v0.6.2). One short request: the paragraph, the one before and the one after (so
the new text still fits), and what the player wants changed. Nothing is saved here: the screen shows the proposal and
the player keeps it (a normal edit of the message, so the edit history can bring the old text back) or drops it."""
from __future__ import annotations

import re
from typing import Any

from ..providers import ChatMessage
from . import settings_service, story_tree, usage
from .live_speakers import paragraphs

MAX_PARAGRAPH_CHARS = 4000
RULES = (
    "You rewrite ONE paragraph of an interactive story, written in {language}. Keep the same events, the same "
    "speakers and the same point of view; it must still follow the paragraph before and lead into the paragraph after. "
    "Never write the actions, words or thoughts of the protagonist ({name}) unless the original paragraph already had "
    "them. Answer with the new paragraph only: no title, no quotes around it, no comment, no notes."
)
TAG = re.compile(r"\[\s*[^\[\]\n]{1,40}?\s*:\s*\d\s*\]|\[\s*(?:music|musique|bgm)\s*:[^\]]*\]", re.IGNORECASE)


def split(text: str) -> list[str]:
    return [text[a:b] for a, b in paragraphs(text)]


def clean(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^```[a-z]*\s*|\s*```$", "", t)
    t = re.sub(r"<info>.*?(</info>|$)", "", t, flags=re.S | re.I)
    t = TAG.sub("", t)
    t = re.sub(r"^(?:here is|voici)[^\n:]{0,60}:\s*\n", "", t, flags=re.I)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


async def propose(ctx, story_id: str, message_id: str, index: int, wish: str = "") -> dict[str, Any]:
    from .narration_language import LANGUAGES, of as language_of
    from .summaries import protagonist
    from ..models import Message

    with ctx.db.session() as db:
        story = story_tree.get_story(db, story_id)
        m = db.get(Message, message_id)
        if m is None or m.story_id != story_id or m.role != "assistant" or m.status == "streaming":
            raise ValueError("This reply cannot be rewritten.")
        parts = split(m.content or "")
        if not 0 <= index < len(parts):
            raise ValueError("That paragraph does not exist.")
        if len(parts[index]) > MAX_PARAGRAPH_CHARS:
            raise ValueError("That paragraph is too long to rewrite on its own.")
        resolved = ctx.resolve(db, ctx.story_profile_id(db, story))
        usage.check_budget(db, story, resolved.adapter)
        code = language_of(settings_service.get_all(db), story.settings_json or {})
        system = RULES.format(language=LANGUAGES[code], name=protagonist(db, story))
        before = parts[index - 1] if index > 0 else "(start of the reply)"
        after = parts[index + 1] if index + 1 < len(parts) else "(end of the reply)"
        original = parts[index]
    wish = (wish or "").strip()[:500]
    prompt = (f"Paragraph before:\n{before}\n\nPARAGRAPH TO REWRITE:\n{original}\n\nParagraph after:\n{after}\n\n"
              + (f"What the player wants changed: {wish}\n" if wish else "Write it better: clearer and more vivid, "
                                                                           "same content.\n")
              + "\nThe new paragraph:")
    params = {**resolved.params, "temperature": 0.8,
              "max_tokens": min(1200, max(200, len(original) // 2))}
    text = await resolved.adapter.complete(resolved.profile.model_id, system, [ChatMessage("user", prompt)], params)
    usage.record(ctx, story_id, "rewrite", resolved.adapter)
    new = clean(text)
    if not new:
        raise ValueError("The model returned nothing usable. Try again.")
    return {"paragraph": index, "original": original, "text": new}


def replace(content: str, index: int, new: str) -> str:
    """The reply with paragraph ``index`` replaced (the blank lines between paragraphs are kept)."""
    spans = paragraphs(content)
    a, b = spans[index]
    return content[:a] + new.strip() + content[b:]
