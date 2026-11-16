# Project Architecture: StoryCore

## Project Overview
StoryCore is an AI-powered narrative engine designed to generate deep, intense textual roleplay. Each story world is a
**Lore Pack**: a folder of structured lore files plus one `pack.json` that tells the engine everything the lore does not
say. The engine contains no story-specific data; any number of worlds can live side by side.

## Tech Stack
- **Backend:** Python 3.12 (FastAPI / SQLAlchemy / Alembic), bundled Windows Python in `app/python`
- **Frontend:** React/Vite, source in `app/frontend/src`, shipped built in `app/frontend/dist`
- **Database:** SQLite, `data/stories.db` (copied from the older `lumencia.db` on first start)
- **AI Integration:** Multi-provider support (Ollama, OpenRouter / OpenAI-compatible, Anthropic, a mock narrator)

## Directory Structure & Component Mapping
- `Lorepack/<pack folder>/`: one folder per world. `pack.json` is the entry point (format: `LOREPACK_FORMAT.md`).
- `app/backend/story/`: the engine.
    - `models.py`: database schema.
        - `World`: one imported Lore Pack (slug = the pack's `id`, system prompt, `data_json` with the pack settings
          under `"pack"`, the openings under `"starters"`, and import fingerprints).
        - `Story`: one playthrough, linked to a `World`.
        - `LoreDocument` / `LoreEntity` / `LoreChunk`: the pack's lore, a read-only snapshot per import.
        - `Message` / `MessageBranch`: narrative history and branches. `StoryState`: stats, scene, cast, clock.
    - `bundled.py`: at every start, imports new packs from `Lorepack/`, re-imports packs whose files changed, scans
      their portrait folders, and re-points stored paths after the project folder moves.
    - `services/`:
        - `pack_manifest.py`: reads and validates `pack.json` (sections may point to smaller files; a broken section is
          skipped and reported, never fatal).
        - `world_pack.py`: the one place the engine reads a world's pack settings from.
        - `lore_import.py`: imports a pack's lore; tolerant of other layouts (ids generated from names, unknown lists
          categorised by file name, object-shaped files).
        - `context_builder.py`: the "brain"; assembles the narrator context each turn.
        - `roles.py`: unique posts and closed groups (lore + pack `posts` / `closed_groups` + in-app corrections).
        - `canon.py`: fixed facts and recurring gatherings (pack `facts` / `gatherings` + in-app corrections + lore).
        - `encounters.py`: optional chance-encounter hints (pack `places`, `never_random`).
        - `scene_cast.py`: who is in the scene; a gathering's roster during a lesson or meeting.
        - `world_state.py`: in-story clock and calendar (pack `calendar`).
        - `identity.py`: resolves "the Headmaster", "Lucia's sister"... to characters.
        - `settings_service.py`: app settings, including the in-app corrections layered on packs.
    - `routers/`: REST API for the frontend. `migrations/`: database schema history.
- `data/`: database, uploads, backups, logs (the player's data; never touched by pack imports).

## Layering of world data (lowest to highest priority)
1. **Lore files** of the pack (structured fields such as a department's head).
2. **`pack.json`** of the pack (posts, facts, gatherings, places, stats, openings, calendar, modules...).
3. **In-app corrections** (settings `role_assignments`, `canon_facts`, scoped to a world slug) and per-story edits.

A pack never overrides a correction, and re-importing a pack never erases one.

## Genre modules
A pack lists genre modules in `pack.json` → `modules`. A module switches on genre-specific behaviour:
- `school`: lesson detection, start-of-year date suggestion, first-year students as early encounters, student wording.
- Others (`isekai`, `heroic_fantasy`, `cyberpunk`...) are accepted and stored; their behaviour is planned.
Without a module the engine uses neutral wording (a gathering's leader and members, townsfolk and passers-by).

## Narrative Flow
1. **World Selection:** the player picks a World (one per Lore Pack) and an opening when creating a story; the
   "World default" stat sheet comes from the pack.
2. **Context Construction:** each turn, `context_builder.py` assembles the world prompt, posts and groups, canon facts,
   the scene and cast, relevant lore, memories and recent messages, within the model's budget.
3. **Generation:** the context is sent to the selected AI provider.
4. **State Update:** the reply is analysed to update the scene, cast, clock, relationships and journal.

## Adding a new world
1. Create `Lorepack/<my_world>_lore_pack/` with your lore files (any reasonable JSON/Markdown layout).
2. Add `pack.json` with at least `format_version`, `id`, `name` (see `LOREPACK_FORMAT.md`).
3. Start the app: the world is imported automatically. Edit files and restart to re-import.

## Hidden information
Any lore record may carry a `"hidden"` field: narrator-only secrets, removed from everything the player can see and
given to the narrator only when that record is in play (`lore_import.strip_hidden`, `context_builder` section 8b).

## Developer documentation
The `DEVONLY` folder documents everything in detail (start with `DEVONLY/00_READ_FIRST.txt`).

## History
The multi-story refactor (November 2026) is recorded step by step in `REFACTOR_LOG.md`.
