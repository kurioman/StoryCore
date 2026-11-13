# Retrieval and Continuity Protocol

Use this file when implementing a lore retriever, a local LLM agent or a narrative memory system.

## Retrieval order

1. Retrieve the protagonist's current campaign state.
2. Retrieve the current location and scene-relevant faction(s).
3. Retrieve only the characters physically present or likely to be referenced.
4. Retrieve the relevant power-system entry if a spell, duel, healing effect or Miasma event occurs.
5. Retrieve relevant source notes only when the user asks about lore accuracy or when an ambiguity could change a consequential decision.

## Authority model

Suggested precedence:

1. User-confirmed facts for the active campaign.
2. The active campaign's event log and save state.
3. High-confidence recurring reference data in this pack.
4. Medium-confidence public-adaptation details.
5. Community reconstructions and low-confidence details.
6. Newly generated speculation, which must remain explicitly provisional until established by play.

This order allows the user to intentionally diverge from baseline lore without corrupting the baseline for other sessions.

## Evidence object

For facts learned in play, store something like:

```json
{
  "fact_id": "local_fact_0001",
  "subject_id": "isabel",
  "predicate": "used_eye_of_insight",
  "value": "detected an abnormal mana signature",
  "status": "observed",
  "observed_by": ["protagonist"],
  "source_event_id": "scene_0017",
  "timestamp": "imperial-year/date if known",
  "confidence": 0.95,
  "scope": "current_campaign_only"
}
```

Do not convert a character's speculation into objective truth. Keep `status` values such as `confirmed`, `observed`, `reported`, `rumour`, `hypothesis`, and `disproved` separate.

## Stable entities and relationships

- Use the `id` field as the primary key.
- Keep aliases such as `Isabela`, `Maribel`, and `Delpirem` for search, but normalize them to canonical IDs.
- Represent relationships as directed, typed edges with a confidence and provenance.
- Never assume two people are allies solely because they share a faction.
- If a character's year, rank or role changes during play, record the change in campaign state with a timestamp rather than mutating baseline data.

## Plot hook discipline

- `story/plot_hooks.json` is an idea bank, not a quest queue.
- Only activate a hook when it emerges naturally, the user requests it, or the campaign establishes a relevant trigger.
- Record an active hook's trigger, progress, clues, involved characters, consequences and resolution state in the save file.
- Do not force a fixed sequence of events onto the user.
