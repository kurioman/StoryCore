# Release notes: StoryCore v1.7.0 for Windows

StoryCore is the new name of Lumencia Story Desk. It is now a multi-story engine: every world is a lore pack in the
`Lorepack` folder, loaded automatically at start.

## In progress for v1.8 (not released yet)

- **New interface, with its source code** (`app/frontend/src`). Same screens and behaviour; every text is ready for
  translation. It replaces the v1.7 interface, which is removed (old bookmarks to `/next/` or `/old` still work).
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
- **Fixed: portraits mixed up between worlds.** Hero's Chronicle and Lumencia Academy both have a Lily and a
  Beelzebub; a story could show the other world's picture. Each pack's portraits now belong to its world (the next start
  sorts existing data out by itself). The pack checker notes characters whose id exists in several packs.
- **Lore pack format 2** (`pack.json`): a library card with a short summary, tags and a cover image, each text
  optionally per language. Format 1 packs still load. Both shipped packs have their summary and tags (cover to come).
- **Openings reworked.** Hero's Chronicle: two openings, both starting with the prologue before the Heavenly God Lily
  (1 March 1301), then arriving either in the summoning hall of Avalon (the royal palace of Grandel) or before the
  Demon King Beelzebub. Lumencia Academy: one opening, the new student arriving on 1 March. The other openings of the
  packs are removed. Both packs now have their cover image.
- **No more generic openings** (Free Mode, Character Preview and the Settings editor for them): a story's openings
  come only from its lore pack. The pack's first opening is selected by default. Opening names and descriptions can be
  written per language (Hero's Chronicle: "Début alternatif : le Roi Démon").
- Hero's Chronicle lore: Avalon added; Beelzebub is a woman who bears the title Demon King (narrator notes fixed).
- **Codex**: a "Codex" button on the play screen opens an encyclopedia of the characters and places discovered in the
  story (follows branches). Characters: heard of, met or known, with portrait, details, the expressions already seen
  and the first meeting. Places: heard of when the story names them, visited when a scene takes place there.
  Undiscovered entries are "???" cards with a progress counter, never their name. Packs can switch it off
  (`"codex": false`) or leave a record out.
- **Story library** (where "Start your next adventure" leads): "Resume" with your last game in a big card and your
  other games in progress, then one card per lore pack with its cover, tags and summary. A card opens the story sheet:
  choose an opening, "New game" (the wizard opens with the world and opening chosen) and your games in that world.
  "Resume my last adventure" on the welcome page now opens your latest game.
- **Music**: one music library for the whole app (`Music` folder, new **Music** page): add .mp3 files, listen,
  rename, tag them (about 60 tags in four families: mood, action, places, moments, plus your own). During a story the
  narrator marks mood and place changes with a hidden music tag; otherwise the scene's place chooses. A player at the
  bottom of the right panel: play / pause, clickable progress bar, another track, volume, mute, crossfade between
  tracks; volume remembered. Packs can switch music off or pick tracks per tag (`pack.json` "music").
- **Night-blue dark theme** for the whole app, matching the welcome page (the light theme is unchanged).
- **Cinzel** for the StoryCore name (welcome title, sidebar, headers), bundled with the app (SIL Open Font License).
  New welcome logo (a star born from an open book); the rest of the app keeps the four-point star.
- **Recap and Report a problem buttons** always visible at the bottom of the right panel while playing. "Report a
  problem" asks what happened and puts that text in the bug report zip (`description.txt`), with the page and story
  it was made from (`context.json`: ids and counts only, never story text). A crashed screen also offers it.
- **First-run assistant** (`#/setup`): the first click on the welcome page opens it (afterwards it goes straight to
  the library; it can be reopened from the gear menu). Language, then where the AI runs: on your computer (graphics card
  detected for NVIDIA cards, otherwise you pick its video memory; recommends TheDrummer's Rocinante 12B v1.1 with the
  right file and context length for your card, and explains that a model bigger than your video memory works but is
  much slower) or online through OpenRouter (Claude for the best writing but the highest price, DeepSeek, Gemini,
  Mistral for French). Ends with a short tour of the library, Codex, Music, Recap and Report. "Skip" at every step.
- The new-story wizard no longer shows the opening blueprint (it stays hidden from the player).
- **Play on a phone** (gear menu, sidebar, or Settings > Play on a phone): switch on "Allow a phone to connect", then
  scan the QR code with the phone (same Wi-Fi), or type the address shown and the 6-digit code. The story still runs
  on the computer; the phone shows it and plays. The code works once and for 10 minutes (a new one is ready at once);
  the list of connected phones has Disconnect buttons. The option switches itself off when StoryCore closes, and
  every phone is then disconnected. A phone cannot open the computer-only areas (models and keys, backups, imports,
  logs, folders). The first time, Windows may ask to let StoryCore use the network: tick "Private networks". The link
  is not encrypted: use it on your home Wi-Fi only. The welcome page and the library fit phone screens.
- **Automatic summaries (long games).** While you play, short summaries of the story are written and sent to the AI
  in place of the messages that no longer fit, so it keeps the thread of long games. With automatic event capture
  (the default) they come in the same request, at no extra cost; otherwise, and for games started before, a short
  request after a reply catches up, oldest messages first. Editing or regenerating a message rewrites its summary.
  Switch: Settings > Memory capture > Automatic summaries.
  The memory works in layers: older scenes are merged into chapters, older chapters into a "story so far", so it
  stays the same size however long the game. Each summary also remembers what happened with each character (sent
  when that character is in the scene again) and the promises, quests and mysteries still open; the detail of an old
  scene comes back when its names or places are mentioned again.
- **A better Recap.** The golden Recap button now writes a recap for you, in the story's language ("Previously…" and
  what is still pending), from the AI's memory: one short request instead of re-reading the whole story, and shown
  again at once while nothing new has happened. A long story opened again after a few hours offers it above the
  message box. The Journal has a new "AI memory" tab: the story so far, chapters and scenes (correct one, or pin it as a
  permanent memory), the open threads (mark one settled), what each character remembers, "Summarise now" and "Close the
  chapter here". The /chapter command (/chapitre) closes a chapter with an optional title.
- **Continuity checks at no cost.** StoryCore spots the phrases the narrator keeps reusing and asks it to vary them
  (Settings > Narration & context > Fight repetitions). A notice appears under a reply when a character the journal
  records as dead speaks, when the time of day goes back on the same day, or when the scene analysis finds that the
  reply contradicts a pinned memory. The reply is never changed: regenerate or edit it if needed.
- **Token counter.** Next to the context meter, a gauge shows what the latest turn sent to the AI (and how much came
  from the provider's cache); click it for the whole story: narrator, scene analysis, memory, summaries, recaps, and
  the cost when the provider reports it. The provider's real figures also correct StoryCore's own estimate for each
  story, so a story in French no longer overflows a small model window. A short reply with nobody in the scene no
  longer triggers a scene analysis request.
- **Faster and cheaper requests.** What changes every turn (scene, lore found, memories, narration rules) now travels
  with your message, and older messages leave the request in steps rather than one by one: the beginning of the
  request stays the same for several turns. LM Studio reuses what it already read (replies start sooner); DeepSeek and
  Gemini bill repeated input less, and Claude gets cache markers. A character's full lore entry is sent when they
  arrive, then only their short line while they stay. Both can be switched off in Settings > Narration & context.
- The recommended-models cards (Settings > Providers & models) are translated too ("Tested with StoryCore", pros
  and cons...).

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
