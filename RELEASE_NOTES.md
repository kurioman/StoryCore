# Release notes: StoryCore v1.7.0 for Windows

StoryCore is the new name of Lumencia Story Desk. It is now a multi-story engine: every world is a lore pack in the
`Lorepack` folder, loaded automatically at start.

## In progress for v1.8 (not released yet)

- **New interface, with its source code** (`app/frontend/src`), now opened by default (address `/next/`). Same
  screens and behaviour; every text is ready for translation. The previous interface stays at `/old` for now.
- **Interface in French.** Settings > Appearance > Interface language (new interface): menus, buttons, help and
  messages in French. Lore and a few texts written by the engine stay in English.
- **Story language.** The narrator can write in French (Settings > Narration & context, or per story). Lore, names and
  portrait tags are unchanged.
- **Check Lore Packs.bat** reports what is wrong in a pack (invalid JSON with its line, unknown ids, portraits that
  match nobody, missing expressions, identical expression images...) without starting the app.
- **Scene analysis with LM Studio**: the analysis now asks LM Studio for its JSON in a form it accepts, so it no longer
  fails with "No JSON object found".
- Hero's Chronicle portraits recompressed (133 MB to 18 MB, same look).
- **LM Studio in one click** (new interface): Settings > Providers & models > LM Studio > Detect. StoryCore lists the
  models with their real context size; "Use this model" creates the connection with fitting settings and makes it the
  default. It warns when the model is loaded with a context too small for a story.
- **Report a problem**: Settings > Data & backups > Export a bug report makes a zip to send to the developer (versions,
  settings, recent errors, last logs). It never contains your API keys or your stories.
- Engine tests (`app/backend/tests`, `DEVONLY/run_tests.bat`).
- **New welcome page**: full screen, big logo and outlined title with a soft light behind it, the motto, a "Start your
  next adventure" button and a settings gear, over an animated starry sky: stars are born at the centre and drift out
  of the screen, twinkle and follow the mouse. On hover the button lights up, trembles and absorbs the stars that come
  near. The gear opens a small menu to switch the language on the spot or open all settings. The button opens the story
  list (`#/library`; it becomes the story library later) after a jump to light speed. Stars are born from a light in
  the middle of the screen. Footer: credits, Discord (link set in `app/frontend/src/lib/links.ts`) and the version.
  With "reduce motion" switched on in Windows, the stars stay still.
- **Night-blue dark theme** for the whole app, matching the welcome page (the light theme is unchanged).
- **Cinzel** for the StoryCore name (welcome title, sidebar, headers), bundled with the app (SIL Open Font License).
  New welcome logo (a star born from an open book); the rest of the app keeps the four-point star.
- **Recap and Report a problem buttons** always visible at the bottom of the right panel while playing. "Report a
  problem" asks what happened and puts that text in the bug report zip (`description.txt`), with the page and story
  it was made from (`context.json`: ids and counts only, never story text). A crashed screen also offers it.

## New in v1.7.0

- **Several worlds.** Hero's Chronicle (heroic fantasy) joins Lumencia Academy. Each world brings its own openings,
  stat sheet, characters, portraits, unique posts and rules. Add a world by adding a folder with a `pack.json`
  (see `LOREPACK_FORMAT.md`); restart the app and it is there.
- **Portraits right away.** The narrator tags each spoken line with the speaker and an expression
  (`[Selphina:3]`); the app hides the tag and shows the matching portrait as soon as the reply ends, instead of
  waiting for the scene analysis. Expressions: 1 neutral, 2 happy, 3 sad, 4 angry, 5 disdain, 6 love / shy.
- **Suggested replies are now off by default** (faster scene analysis); turn them on in Settings > Memory capture.
- **Narrator-only secrets.** Lore can hold hidden information the narrator knows but the player never sees in the
  app (for example a character's true allegiance). It shapes the story and is revealed only through events.
- **Automatic loading and re-loading.** Edit a pack, restart, and the world is updated. Your stories, corrections
  and notes are never touched by a re-import.
- **LM Studio** and other OpenAI-compatible local servers are documented next to Ollama and OpenRouter.
- **Developer documentation** in the `DEVONLY` folder.
- Fixes: the app started old compiled code after an update; full backups could not be verified or restored; files
  exported by Lumencia Story Desk can be imported again.

**Coming from Lumencia Story Desk or an earlier StoryCore?** Close the app and copy your `data` folder into the new
`StoryCore` folder. On the first start your old `lumencia.db` is copied to `stories.db` (the old file is kept) and the
database is updated, with a backup made first.

## Earlier: v1.6.4

- Portraits, suggested replies, relationship tracking and scene analysis on by default, each adjustable in Settings > Memory capture.
- New token defaults (context budget 10000, reserved for the reply 2000, max output tokens 3000, output length Medium).
- Thinking off for story replies by default; clearer analysis failures with a Retry button.

## What is included

**Story**
- Create and save stories with a five-step wizard; each world offers its own openings, plus Free Mode and Character Preview.
- Narrated replies through LM Studio, Ollama, OpenRouter, OpenAI, Anthropic or any OpenAI-compatible server, plus an offline Mock narrator for trying the app.
- Three editable suggestions after each reply. Nothing is sent until you press Send.
- A header on each reply with the in-story day, time, weather and place. You can correct it with the pencil or `/scene`.
- Two dialogue styles (Dialogue emphasis, with speaker labels and portraits in the text, and Classic), reading size, story font, and Light and Dark themes.
- Savepoints, branches, recaps, slash commands and per-story content preferences.

**World and characters**
- Two lore packs: Hero's Chronicle (21 characters) and Lumencia Academy (about 30 characters), with factions, locations and power systems.
- Portraits with six expressions per character, shown beside the moment a character speaks or reacts.
- Cast panel, relationships, and a journal and memory with links back to the messages they came from.

**Your data**
- Everything is stored in a local `data` folder that starts empty.
- Full backups, story export and import, and an in-app Help tour.

## Known technical limitations

- **Tested on Windows 11.** Windows 10 should work but has had little testing.
- **Not code-signed, and there is no installer.** Expect a SmartScreen warning on the first start, and possibly an antivirus warning.
- **Windows only.** The interface is in English only.
- **Keep the black window open** while you play. Run only one copy at a time.
- **The Mock narrator shows no portraits or relationship changes,** because it cannot read the story. Use a real model to see them.
- **Speaker labels:** the fix that shows someone as speaking when a reply only says "she said" could not be confirmed on real model output. Ambiguous scenes stay conservative, so a character can still be shown as "Also present". The sentence and the ⓘ figures from that reply make a very useful report.
- **Analysis can fail** on malformed model output. The app retries once, which is one extra request. If that also fails, the reply is fine but has no portraits or suggestions until you press Retry.
- **Prose quality depends on your model.** Hidden reasoning is off by default for OpenRouter narration, and this has only had limited testing.
- **Suggestions are checked for shape, not truth.** A draft can contain a small invented detail, so read it before you send it.
- **Long sessions** have had little testing with real models. Season and date details can drift.
- **A long reply can be cut off** at the output limit. It is then marked incomplete rather than silently accepted.
- **Portrait matching needs the original file names** (`<character>_1.webp` ... `_6`), so leave the image folders as they are.
- **Prices and models change.** The app reads current prices from OpenRouter, and what you pay can differ by routed provider.

## Feedback

Send feedback and bug reports to the person who shared StoryCore with you. `README.md` lists what to include. The most useful notes are what you did, what you expected, and what happened.
