# StoryCore v1.7.0: frontend inventory

Purpose: the checklist for rebuilding the frontend from scratch with source code (roadmap step 2).
The rebuild is done when every box below is ticked and a real game plays with no visible difference.

Made on 2026-11-13 by running v1.7.0 (Mock narrator, fresh data folder) in a headless browser and reading the
compiled bundle `app/frontend/dist/assets/index-storycore-p6.js`.

Files in `DEVONLY/frontend_inventory/`:

| File | What it holds |
| --- | --- |
| `screenshots/*.png` | One capture per screen, wizard step and story panel (1440×900) |
| `elements.json` | Per route: headings, labels, buttons/tabs and inputs found on the page |
| `ui_strings.json` | ~600 human-readable strings extracted from the bundle (raw, some noise): base for `en.json` |
| `backend_routes.txt` | Every backend route (174), method + path |

---

## 1. Global shell

- [ ] Hash routing (`#/…`); any server path returns `index.html`
- [ ] Every request: JSON to `/api/...` with header `X-Story-Client: 1`
- [ ] Error JSON `{"detail","code"}`; special codes: `cloud_consent_required` (privacy notice), `no_model` (link to Settings), `provider_error` (friendly + technical details)
- [ ] Live text via `EventSource` on `/api/generations/{message_id}/stream`; cancel via `/generations/{id}/cancel`
- [ ] Images via `/api/assets/{id}/image?variant=card|full|…` and `/api/uploads/...`
- [ ] localStorage keys prefixed `lsd:` (panel sizes, last tab…) and drafts `lsd:draft:<story>:<branch>`
- [ ] Dark / Light themes, story font, reading size, dialogue style (see Settings > Appearance)
- [ ] Left sidebar (collapsible): **New story**, **Import story package**, search stories, tabs **Active / Archived / Templates**, story list (title, time, world, message count, actions menu), bottom links **Avatars, Lore library, Portraits, Commands, Settings, Help**
- [ ] Help: in-app tour (`help.png`)

## 2. Home `#/` (`home.png`)

- [ ] Title + tagline "Your local storytelling workspace…"
- [ ] **Get set up** checklist (e.g. "Connect a model" → Add provider)
- [ ] Three cards: New story, Create an avatar, Browse lore
- [ ] **Continue**: recent stories with last reply excerpt
- [ ] Status line: lore imported, portrait folders registered

## 3. New story wizard `#/new` (`new*.png`)

- [ ] Step tabs 1–5, Back / Next, Next disabled until the title is set
- [ ] 1. Story: title, story note (optional)
- [ ] 2. World & start: world select (default "No preset world (free-form)"), starting modes = the world's starters + Free Mode + Character Preview, starting location (select per world, "Let the narrator choose"), starting time
- [ ] 3. Protagonist: No avatar / pick avatar / "Create a new avatar (opens the editor)", stat sheet select ("World default…")
- [ ] 4. Tone & model: narration preset, model (Global default), tone, pacing, output length, max output tokens (+ help text), player-agency note, note on `/nsfw`
- [ ] 5. Review: summary table, **Create & preview first context**
- [ ] After create: context preview (token budget, largest sections, trimming order, sections with items) + **Open story and write the first move myself** / **Generate the opening scene** (`story_created.png`)

## 4. Story page `#/story/:id` (`story_*.png`, `panel_*.png`, `menu_more_tools.png`)

Header
- [ ] Title, branch (Main), avatar switch, model switch, preset switch, context gauge (≈used / budget), More story tools menu (**User notes**, **Savepoints**), toggle **Story / Journal & Memory**, hide status panel

Transcript
- [ ] Scene header per reply: day, calendar date, weekday, time, weather, place + pencil (correct scene, also `/scene`)
- [ ] Speaker labels + inline portraits (Dialogue emphasis style) / Classic style
- [ ] Portrait tag `[Name:N]` hidden from the text, portrait shown when the reply ends
- [ ] User message actions: Copy, Edit, Generate a new reply from here, Branch from here, Delete
- [ ] Reply actions: Copy, Edit, Context sent to the model, How this reply was generated (ⓘ), Regenerate, Branch from here, Delete; versions + restore; incomplete reply marker; analysis failure + Retry
- [ ] Suggested replies (3, off by default): fill the box only
- [ ] Scroll to latest

Scene bar and composer
- [ ] **Scene** strip: present characters with portrait, expression, "speaking"
- [ ] Composer: "What do you do? Type / for commands", slash palette, Enter / Shift+Enter (setting), **Write your own…**, **Continue scene**, **Recap (/recap)**, **Open Journal & Memory**, Send, model line

Right panel tabs
- [ ] **Status**: player card (edit), location, stats (bars, +/−, edit), conditions, state version + Undo, proposed changes + "Suggest from last turn", state history
- [ ] **Known**, **Relations** (duplicates / merge), **Cast**, **Items**, **Quests** (quests, immediate goals, pending promises, unresolved mysteries, known clues)

Journal & Memory view
- [ ] Tabs: Timeline (search, filters by character/type/status/importance, Manual event), Review, Memories & facts, Current state, Characters, Recaps, Maintenance

## 5. Lore library `#/lore` (`lore.png`)

- [ ] World select, Re-import, Import another lore pack (zip)
- [ ] Search all lore, category chips with counts, source-confidence filter
- [ ] Record list with thumbnail + summary; record detail
- [ ] "Baseline lore is read-only" notice, Copy to local canon, last import report

## 6. Portraits `#/portraits` (`portraits.png`)

- [ ] Tabs: Characters (N), Needs mapping, Folders
- [ ] Six expressions per character, overrides, slug overrides, upload, folder scan / copy to app data

## 7. Avatars `#/avatars`, `#/avatars/:id` (`avatars*.png`)

- [ ] List, Import avatar JSON, New, export, delete
- [ ] Editor tabs: Identity, Appearance, Background & personality, Abilities, Stats & inventory, Additional info, Prompt preview; favourite; autosave ("Saved"); portrait

## 8. Commands `#/commands` (`commands.png`)

- [ ] Search, Export, Import, New command; groups Continuity, Lore, Meta, Narrative, Scene, Settings, Tools
- [ ] Per command: aliases, badges (built-in, hybrid / local action / prompt), pin, Duplicate, Reset to default, edit
- [ ] 16 built-ins: ooc, recap, story, addlore, continue, continuity, journal, lore, meanwhile, memory, nsfw, recon, savepoint, scene, state, undo

## 9. Settings `#/settings/:tab` (`settings_*.png`)

- [ ] **Providers & models**: choose how to run the AI (OpenRouter, Ollama, other presets incl. LM Studio), recommended models, OpenRouter setup (key, Refresh prices, Select), Test connection, Test model, Remove model profile, cloud consent
- [ ] **Ollama models**: quick setup, curated list, pull with progress / cancel, delete, show
- [ ] **Narration & context**: context budget, reserved for reply, keep N recent messages, warn %, Enter sends, player-agency prompt profile, default narrator prompt, narration presets (add/remove), generic starter blueprints (add/remove), Save
- [ ] **Memory capture**: automatic event capture, batch size, extraction model, event storage mode, review threshold, scene analysis, relationship changes, portrait placement, suggest three replies, auto portrait expressions, auto recap, Save
- [ ] **Global note**: enabled, text, Save, Export notes
- [ ] **Appearance**: theme, story font, reading size, dialogue presentation
- [ ] **Data & backups**: data folder paths + Open data folder, Back up now, upload / verify / restore / download backups, exports (commands, local canon JSON/MD, notes), import local canon, integrity check, recent logs, clear logs

## 10. Backend routes to double-check

These backend routes were not found as literal paths in the bundle. They may be built another way or be unused:
`/model-profiles` (POST, PATCH, DELETE), `/assets/expressions`, `/assets/rescan-all`, `/avatars/{id}/preview`,
`/avatars/{id}/portrait-from-asset`, `/generations/active`, `/lore/chunks/{id}`, `/lore/import-runs`, `/model-catalog`
(+ refresh), `/onboarding`, `/prompt-profiles`, `/stories/{id}/branches`, `/stories/{id}/search`,
`/stories/{id}/state/history/{version}`, `/worlds/{id}/roles`, `/notes/import`.

## 11. Observations for later steps (not to change during the rebuild)

- The wizard defaults to "No preset world (free-form)": the story library (step 3) fixes this.
- The context preview shown after creation is very technical for a player; candidate for the library's
  presentation page or an "advanced" toggle.
- Settings > Providers puts OpenRouter and Ollama first; LM Studio (the author's daily setup) is not one of the
  two highlighted choices. Candidate for the "model profiles in one click" item (step 5).
