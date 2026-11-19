# Lore Pack Format (pack.json) — version 2

A **lore pack** is a folder inside `Lorepack/` that holds one story world. It contains:

- **Lore files** (characters, factions, locations, glossary, premise...) — JSON and Markdown, imported as before.
- **One `pack.json` file at the root of the pack** — the entry point. It tells the engine what the lore files do not
  say: the world's identity, its files, the player's stats, opening scenarios, unique posts, fixed facts, and so on.

```
Lorepack/
  my_story_lore_pack/
    pack.json              <- required entry point
    pack/                  <- optional: smaller files that pack.json points to
    ai/narrative_system_prompt.md
    lore/premise.md
    characters/characters.json
    my_story_images/
```

## Basic rules

1. **Only `format_version`, `id` and `name` are required.** Every other section is optional. When a section is
   missing, the matching engine feature is simply off for that world.
2. **One main file, smaller files allowed.** Any section can be written directly in `pack.json`, or replaced by a path
   to its own JSON file, e.g. `"gatherings": "pack/classes.json"`. That file may contain the list itself, or an object
   with the section's name as its key (`{ "gatherings": [ ... ] }`).
3. **Mistakes never block the whole pack.** A broken section is skipped and the import report says why. Only a missing
   or invalid identity (`format_version`, `id`, `name`) stops the manifest from being used.
4. **The pack gives the defaults.** Corrections you make inside the app (for one world or one story) are saved
   separately and applied on top. Re-importing a pack never erases them.
5. **Character references use ids** from the lore files (e.g. `"elena_caldwin"`), not display names. After an import,
   the report lists every id the lore does not contain.

## Full example

```json
{
  "format_version": 2,
  "id": "my_story",
  "name": "My Story",
  "description": "One or two sentences shown when choosing a world.",
  "modules": ["school"],

  "files": {
    "system_prompt": "ai/narrative_system_prompt.md",
    "premise": "lore/premise.md",
    "images": "my_story_images"
  },

  "stats": [
    { "label": "HP", "type": "current_max", "value": 100, "max": 100 },
    { "label": "Rank", "type": "text", "value": "Unranked" },
    { "label": "Gold", "type": "number", "value": 10, "unit": "g" }
  ],

  "starters": [
    { "id": "arrival", "name": "Arrival", "purpose": "Start as a newcomer.",
      "blueprint": "Begin at the city gate at dusk. Present one immediate choice. Do not decide the protagonist's actions." }
  ],

  "posts": [
    { "id": "headmaster", "title": "Headmaster of the Academy", "character": "emily",
      "aliases": ["headmaster", "principal"], "mandatory": true, "note": "Optional extra guidance." }
  ],

  "closed_groups": [
    { "id": "deities", "title": "The Gods", "types": ["deity"] },
    { "id": "council", "title": "The Three Elders", "members": ["elder_a", "elder_b", "elder_c"] }
  ],

  "facts": [
    { "kind": "aunt_of", "subject": "elena", "object": "serena" },
    { "kind": "family_branch", "subject": "laris", "family": "Valenheart", "branch": "secondary branch" },
    { "kind": "other", "subject": "kai", "object": "mira", "text": "Kai owes Mira his life." }
  ],

  "gatherings": [
    { "id": "magic_y1", "kind": "class", "name": "Magic (first year)", "leader": "elena",
      "members": ["sia", "rena"], "keywords": ["magic class", "spell", "mana"] }
  ],

  "places": [
    { "id": "library", "keywords": ["library", "archives"],
      "likely": { "affiliations": ["magic_department"], "traits": ["quiet", "studious"] } },
    { "id": "throne_room", "keywords": ["throne room"], "regulars": ["queen_aria"] }
  ],

  "calendar": { "year_label": "Imperial Year", "year_start": "March" },

  "never_random": ["deity", "demon_god"]
}
```

## Sections

### Identity (required)

| Field | Meaning |
|---|---|
| `format_version` | `2` (v0.5: adds the library card below). Packs with `1` still load unchanged. |
| `id` | Permanent identifier: lowercase letters, digits and `_` (e.g. `lumencia_academy`). Stories are linked to it, so **never change it** once stories exist. |
| `name` | Title shown in the app. Can be changed at any time. |
| `description` | Optional short text for the world list. Without it, the first section of the premise is used. |
| `canon_note` | Optional notice shown when this world is chosen for a new story (e.g. how reliable the lore is). |

### Library card (format 2, optional)

What the story library shows for the pack. Texts can be given once, or per interface language (`en`, `fr`...); the
library uses the player's language, then English, then the first one given.

| Key | Meaning |
|---|---|
| `summary` | Short pitch, 2-3 sentences (under 600 characters). `"..."` or `{"en": "...", "fr": "..."}`. |
| `tags` | A few genre labels. `["Fantasy", "Action"]` or `{"en": [...], "fr": [...]}`. |
| `cover` | Cover image inside the pack, e.g. `"cover.webp"` (webp, png, jpg, avif). Served at `/api/worlds/<id>/cover`. |

```json
"summary": {"en": "You arrive as a new student...", "fr": "Vous arrivez comme nouvel élève..."},
"tags": {"en": ["Academy", "Fantasy"], "fr": ["Académie", "Fantasy"]},
"cover": "cover.webp"
```

### Codex (optional)

The codex is the in-story encyclopedia of characters and places the player has discovered. It is on by default.

| Key | Meaning |
|---|---|
| `codex` | `false` switches the codex off for this pack. |
| `"codex": false` on a lore record | Leaves that character or place out of the codex (a secret character, a hidden place). |

What it shows comes only from public lore (never the narrator-only `hidden` notes): name and type once the player has
heard of someone or something; summary, portrait and details once they have met the character or visited the place.

### Music (optional)

Packs never ship music: the app has one music library (`Music/`, page Music in the app) where every track has tags.
During a story the narrator writes a hidden `[Music:tag]` when the mood or place changes; otherwise the scene's place
chooses. A pack may only adjust this:

```json
"music": {"default": "calm", "choices": {"combat": ["steel_rain"], "tavern": ["warm_hearth", "jolly_mug"]}}
```

| Key | Meaning |
|---|---|
| `"music": false` | No music in this world. |
| `default` | Tag used when nothing else suggests one (start of the story, unknown place). |
| `choices` | For a tag, the library tracks (ids) this world plays; other tags: a random track with that tag. |

### `modules`
List of genre names, e.g. `["school"]`. A module switches on genre-specific engine behaviour. Unknown names are kept
(with a note in the report) so a pack can be tagged before the engine supports that genre.

| Module | Engine behaviour |
|---|---|
| `school` | Lesson detection, start-of-year date suggestion, first-year students offered as early encounters, student/class wording. |
| *others* (`isekai`, `heroic_fantasy`, `cyberpunk`...) | Planned; accepted and stored, no behaviour yet. |

### `files`
Where the pack's special files are, relative to the pack folder. Every entry is optional.

| Entry | Default |
|---|---|
| `system_prompt` | `ai/narrative_system_prompt.md` |
| `premise` | `lore/premise.md` |
| `images` | The single sub-folder named `images` or ending in `_images` |

### `stats`
The player's starting stats. Each stat: `label` (required), `type` = `current_max` (with `max`), `number` or `text`,
`value`, optional `unit`.

### `starters`
Opening scenarios offered when creating a story: `id`, `name`, `blueprint` (the instructions for the opening scene,
required), optional `purpose`. They are listed first and replace any lore scenario with the same id
(`scenarios/starting_scenarios.json` still works).

Optional `scene`: where and when the story starts, set before the first reply (the player's own choices in the
wizard win). Keys: `location`, `time` (e.g. `"09:00"`), `weather`, `weekday`, `day`, `month` (name or number), `year`,
`present` (character ids). A dated opening starts on story day D1.

```json
{ "id": "the_hero_summoned", "name": "The Summoned Hero", "blueprint": "...",
  "scene": { "location": "Pure White Space", "time": "09:00", "day": 1, "month": 3, "year": 1301, "present": ["lily"] } }
```

Format 2: `name` and `purpose` may be given per interface language, like the library card:
`"name": {"en": "Alternative start: The Demon King", "fr": "Début alternatif : le Roi Démon"}`. The blueprint stays one
text (it is written for the narrator). Since v0.5 the app has no generic openings: a pack without `starters` (or lore
scenarios) leaves the narrator to improvise the first scene, and the checker warns about it.

### `posts`
Unique positions held by exactly one character. The narrator always uses that character for the post and never invents
a second holder. Fields: `id`, `title`, `character`, optional `aliases` (other words for the post), `note`,
`mandatory`.

### `closed_groups`
Fixed sets the narrator must never add members to (a pantheon, a council). Give `members` (character ids), `types`
(every character of those types), or both.

### `facts`
Fixed facts about who people are (not how they feel). `kind` is one of:

| Kind | Fields |
|---|---|
| `aunt_of`, `sibling_of`, `parent_of`, `spouse_of` | `subject`, `object` (subject is the aunt / parent...) |
| `family_branch` | `subject`, `family`, optional `branch` |
| `other` | `subject`, `text`, optional `object` |

All kinds accept an optional `note`.

### `gatherings`
People who regularly meet as a group: a class, a guild meeting, a war council. When the scene matches the `keywords`,
the `leader` and `members` are treated as normally present. Fields: `id`, `name`, `keywords` (required), optional
`kind` (e.g. `class`), `leader`, `members`, `note`.

### `places`
Helps the engine suggest who might plausibly be met somewhere. Fields: `id`, `keywords` (required), optional
`regulars` (character ids usually found there) and `likely` → `affiliations` (department/faction ids from the lore) and
`traits` (personality words).

### `calendar`
`year_label` (e.g. `Imperial Calendar`, default `Year`; the narrator reads dates as "1 March, Imperial Calendar 1301")
and `year_start` (the month the year begins, default `January`).

The calendar **format** is fixed for every world: 12 months and 7-day weeks (the engine validates dates, rolls days and weekdays forward with it). A world may use its own year label and start month. The month and weekday names are the standard ones (January..December, Monday..Sunday); only names could ever differ between worlds, never the format.

### `never_random`
Character types the engine never suggests as a chance encounter (gods, demon lords...).

### `events` and `choices` (v0.6, optional)
**Planned events**: scenes you decide in advance (a ceremony, an exam, a tournament), played by the narrator its own way.
Before each reply the app picks at most **one** due event (no model call) and gives it to the narrator in the turn's
context: what must happen, never how. The narrator writes a hidden `[Event:id]` in the reply where it happens (removed
before the player reads, like the music tags). An event asked for `firm_after` times (default 2) is asked for firmly
("start it now, adapted to where the protagonist is"); after `give_up_after` reminders (default 6) without its mark it
counts as played, so no event is asked for forever. The player sees the played events in the Journal (Current state),
never the ones to come.

Each event: `id`, `title` (text or `{"en": ..., "fr": ...}`), `brief` (**required**: what must happen, for the
narrator; English works best), and optionally:

- `characters`: character ids involved;
- `after`: ids of events that must be played (or skipped) first; `delay_turns`: player turns to wait after them;
- `from_turn`: not before the player's turn number N (the opening scene is turn 0);
- `from_story_day`: not before day N of the story (D1 = first day); `from_date`: `{"month": "December", "day": 20}`,
  not before this date of the story's year (the year starts on `calendar.year_start`); an unknown date never triggers it;
- `needs_choice`: waits until this player choice is known; `skip_if_choice`: skipped when it is already known;
- `variants`: `{"option id": "what changes for this option"}`, added to the brief once the choice is known;
- `firm_after`, `give_up_after`: numbers of reminders (see above).

**Player choices** (`choices`) are what events can depend on, e.g. the academy wing: `id`, `name`, and at least two
`options`, each with `id`, `name` and `keywords` (words that show the player chose it, in every language you expect).
The narrator marks a choice with a hidden `[Choice:wing=knight]` when it becomes clear; otherwise the player's own words
settle it when exactly one option's keywords appear in a message.

```json
"choices": [{"id": "wing", "name": {"en": "academy wing", "fr": "aile de l'Académie"}, "options": [
  {"id": "knight", "name": "Knight wing", "keywords": ["knight wing", "aile des chevaliers"]},
  {"id": "magic", "name": "Magic wing", "keywords": ["magic wing", "aile de magie"]}]}],
"events": [
  {"id": "entrance_ceremony", "title": {"en": "Entrance ceremony", "fr": "Cérémonie d'entrée"},
   "brief": "The entrance ceremony on the first day: the headmaster presents the academy, its rules and the instructors.",
   "characters": ["emily"], "from_turn": 1},
  {"id": "wing_exam", "title": "Wing entrance exam", "brief": "The entrance evaluation of the chosen wing.",
   "after": ["entrance_ceremony"], "delay_turns": 1, "needs_choice": "wing",
   "variants": {"knight": "A duel against the instructor.", "magic": "A mana detection crystal."}}
]
```

Progress is read from the replies of the story's current path, so another branch or a regenerated reply has its own.
In the app: World creator, tab **8. Events**. Lumencia Academy uses this for its first days (ceremony, optional
orientation exam, wing exam, start-of-year event) and its end-of-year exam.

## Hidden information (narrator-only secrets)

Any record in the lore files (a character, a faction, a place, even an entry nested inside another record) can have a
`"hidden"` field: one text, or a list of texts. Hidden notes are **known to the narrator but never shown to the player**:

- they are removed from everything the player can see: the lore library (records and raw files), lore search and the
  world details;
- when the record is relevant to the scene (a character present or mentioned, its lore retrieved), its hidden notes are
  given to the narrator in a separate "narrator-only" section, with the rule to never state them outright, to let them
  shape motives and behaviour, and to reveal them only through events, clues or a character's own choice;
- the "preview first context" screen shows a placeholder instead of the notes.

```json
{
  "id": "kriemhild",
  "name": "Kriemhild",
  "type": "Sword Saint (Human)",
  "notes": "A hidden ally who trains the hero.",
  "hidden": [
    "She was defeated once, by the Demon King, who soul-bound and enslaved her.",
    "Through the soul-bond she became the commander of the 4th Legion."
  ]
}
```

A note inside a nested entry is labelled with that entry's name (for example `[4th Legion (Unknown)] ...`). Hidden notes
are only read from JSON files, not from Markdown. The import report gives their number, never their text.

## Making a pack in the app (v0.6)

The easiest way: **World creator** (sidebar, or **Create a world** in the library). It writes a real pack in
`Lorepack/<id>_lore_pack` with the layout below, reloads the world after every change, and exports it as one `.zip`
(**Import a world (.zip)** in the library loads a shared one; a world whose id is already used gets a new id).

```
pack.json                       identity, library card and every section above
lore/premise.md                 presentation of the world
ai/narrative_system_prompt.md   narrator rules
characters/characters.json      {"characters": [...]}
lore/locations.json             {"locations": [...]}
factions/factions.json          {"factions": [...]}   (every kind of group)
story/glossary.json             {"terms": [{"id", "term", "definition"}]}
images/                         cover.webp is at the root; portraits <character id>_<1..6>.webp (converted to WebP)
```

The creator only edits packs whose `pack.json` has a `"_creator"` object (it adds it). Other packs (the bundled ones,
packs written by hand) are copied first: their records are sorted into the files above with the importer's own rules,
narrator-only notes included; files the creator does not manage are kept unchanged and still read. The original is never
changed. In the creator, `summary`, `tags` and starter names are written in one language.

## Checking a pack

Import or re-import the pack in the app. The import report has a **pack** part listing:

- **errors** — a section that could not be used at all (bad JSON, missing file, wrong identity);
- **warnings** — skipped entries, unknown section names, character ids missing from the lore.

A pack with no `pack.json` still imports the old way (name guessed from the folder, every optional feature off), with a
warning saying so.
