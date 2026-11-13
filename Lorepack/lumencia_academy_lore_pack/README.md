# Lumencia Academy — Structured Lore Pack

**Language:** English  
**Pack version:** 1.0.0  
**Research snapshot:** 2026-10-29

This repository-style pack organizes publicly researched Lumencia Academy information into modular Markdown and JSON files for software, retrieval-augmented generation (RAG), local LLMs, and narrative simulations.

## Important canon boundary

This is a **research-based reference pack**, not an official dump of OOC's private story prompt. The official OOC listing was discoverable, but the complete private prompt and exact original starting introductions were not reliably extractable. Much of the detailed structured material comes from a public DreamRunner adaptation and community references. Therefore, each data record carries source IDs and a confidence/status label.

Do not treat these categories as equivalent:
- `recurring_reference`: information repeated in the public adaptation and/or character reference discussions.
- `community_reconstruction`: useful details compiled by players, especially calendar and power-system expansions.
- `playthrough_dependent`: events, relationships, or secrets observed in one user's generated story.
- `unknown`: a detail that should not be invented as established canon.

## Directory map

```text
ai/
  narrative_system_prompt.md     Rules for a story-running AI
  retrieval_and_continuity.md    How to use this dataset without canon drift
lore/
  premise.md                     High-level world premise and canon boundaries
  world.json                     Realm, continent, political context
  locations.json                 Regions and cities
  power_systems.json             Aura, circles, Divinity, Miasma, spirit magic
academy/
  academy.json                   Departments, campus governance, clubs, student life
  academic_calendar.json         Proposed calendar; explicitly community reconstructed
factions/
  factions.json                  Institutions, noble houses, states, religious/demonic groups
  relationships.json             Typed links between major factions
characters/
  index.json                     Entity index for retrieval/code
  students.json                  Student profiles
  faculty_and_celestials.json    Faculty and the Four Celestials, without duplicate records
  relationships.json             Known relationship graph
antagonists/
  demon_cult.json                Cult hierarchy, Apostles and Sin Bishops
  deities.json                   Lily and Delphirem
scenarios/
  starting_scenarios.json        Summary of the three reported OOC start modes
  intro_blueprints.md            Original-text-safe, reusable intro scaffolds (not official quotes)
story/
  plot_hooks.json                Optional story arcs, all marked as hooks rather than fixed canon
  glossary.json                  Normalized terms and alternate spellings
tools/
  validate_pack.py               Basic JSON/source-reference validator
reference/
  sources.json                   Source registry and research policy
schemas/
  character.schema.json          JSON Schema for character records
```

## Data conventions

- IDs are stable lowercase `snake_case` identifiers. Use IDs in code; do not use display names as primary keys.
- Cross-references use IDs, e.g. `faction_ids: ["valenheart_duchy"]`.
- `source_ids` refer to entries in `reference/sources.json`.
- `confidence` is one of `high`, `medium`, `low`.
- `canon_status` indicates the evidential status, not how important a fact is.
- Unknown values are omitted or set to `null`; they should not be filled with guesses automatically.
- The same named entity should have a single canonical ID. Alternate spellings belong in `aliases`.
- The pack describes a **sandbox setting**, not a mandatory campaign order. Plot hooks are optional and should be activated through play or user instruction.

## Validate the pack

Run `python tools/validate_pack.py` from the extracted pack to check JSON syntax, duplicate entity IDs and source references.

## Quick start

### Python

```python
import json
from pathlib import Path

root = Path("lumencia_academy_lore_pack")
students = json.loads((root / "characters/students.json").read_text(encoding="utf-8"))
by_id = {character["id"]: character for character in students["characters"]}
lilia = by_id["lilia_valenheart"]
print(lilia["appearance"])
```

### For an LLM

1. Load `ai/narrative_system_prompt.md` as the system or developer prompt.
2. Inject `lore/premise.md`, the relevant JSON files, and `ai/retrieval_and_continuity.md` as context.
3. Retrieve individual character/faction/location records by ID as needed instead of loading every file into each prompt.
4. Keep session-specific facts in a separate save-state file. Do not write generated outcomes back into the baseline lore files unless the user explicitly promotes them to local-canon facts.

## Suggested extension model

Keep these layers separate:
- `baseline_lore/`: stable reference facts from this pack.
- `session_state/`: protagonist stats, current date, location, inventory, discovered facts, relationships and active quests.
- `local_canon/`: facts established in a particular campaign, with timestamps and evidence.

That separation prevents one generated playthrough from rewriting the base setting for all future sessions.
