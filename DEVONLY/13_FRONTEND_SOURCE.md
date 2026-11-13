# StoryCore frontend: source code (roadmap step 2)

Since November 2026 the interface has its source code, in `app/frontend/src`. Until then only the compiled file
existed (`app/frontend/dist/assets/index-storycore-p6.js`), patched by hand.

## Where things are

```
app/frontend/
  package.json, vite.config.ts, tsconfig.json, index.html   build setup (Vite + React 19 + Tailwind 4)
  src/
    main.tsx              entry: styles, i18n, then app/App
    styles.css            design tokens (dark / light colours, story typography) + Tailwind
    i18n/                 msg() and the language files (see "Languages")
    api/                  client.ts (fetch + SSE), legacy.ts (apiGet/apiPost/... used by the screens),
                          queries.ts (react-query keys, response schemas, data hooks), schema.d.ts (OpenAPI types)
    components/           ui.jsx (Button, Field, Modal, Tabs, Popover, toasts, confirm...), ErrorBoundary.tsx
    lib/                  util (cn, timeAgo...), router (hash routes), hooks, portraits
    app/App.jsx           shell: sidebar + routes
    features/
      home/  sidebar/  help/  wizard/  avatars/  commands/  lore/  portraits/
      settings/           SettingsPage + one file per tab (Providers, OllamaModels, Narration, Memory, Note, Appearance, Data)
      story/              StoryPage (the play screen), transcript, composer, header, dialogs, journal, prose, chrono,
                          panels/ (Status, Known, Relations, Cast, Items & Quests), api.js (scene/known-characters hooks)
  dist/                   v1.7.0 compiled interface (still served at /)
  dist-next/              build of src/ (served at /next/ while the two are compared)
```

## How it was rebuilt

The screens were reconstructed from the v1.7.0 compiled bundle, so they behave exactly like before (same requests,
same texts, same layout; screenshots of every route compared pixel by pixel). The tools that did it are kept in
`DEVONLY/tools/frontend_reconstruction/` for the record:

1. `tojsx.mjs` turns the compiled React calls back into JSX and names the icons (lucide-react).
2. `split.mjs` gives the top-level functions their names (`names.json`), replaces bundled libraries with real imports
   (react-query, radix-ui, zod, react-markdown...), names short local variables after the props or hooks they come
   from, wraps every interface text in `msg("...")`, and splits the code into the modules above.

From now on the source in `src/` is the reference: edit it directly, the tools are not run again.

Known limits of the reconstruction:
- Many local variables still have one-letter names (`let [a, o] = React.useState(...)`). Rename them as you touch a
  file.
- The screens are JavaScript (`.jsx`); new code is TypeScript (`.ts/.tsx`). Converting a screen to TypeScript is a
  good first step whenever it needs real changes.

## Languages (i18n)

Every interface text goes through `msg()` from `src/i18n`:

```jsx
msg("Save")
msg("In {{v0}} story(ies)", { v0: count })
```

The key is the English text itself. `src/i18n/locales/en.json` lists all keys used (base for translators);
`fr.json` is the French translation (complete: every key of en.json). The player picks the language in
Settings > Appearance > Interface language; it is kept in the browser (localStorage `lsd:language`) and the page
reloads, so labels computed when a module loads follow too.

- `msg("English text", { v0: x })` for interface texts; `msgKey(value)` for data keys from the server
  (`secret_revealed`, `power_system`, `active`...): underscores become spaces and the result is translated when the
  dictionary has it, otherwise shown as is.
- Data stays English: values sent to or stored by the server (month and weekday names in a scene, stat labels,
  categories) are never translated, only their display.
- After adding texts, refresh en.json and find untranslated keys:
  `node DEVONLY/tools/frontend_reconstruction/keys.mjs app/frontend/src app/frontend/src/i18n/locales/en.json`
  then compare with fr.json (every key of en.json must be in fr.json).
- A new language: copy fr.json to `<code>.json`, translate the values, add it to `LANGUAGES` and `resources` in
  `src/i18n/index.ts`.

Still in English in a French interface (they come from the backend or the packs, not from the interface): slash
command descriptions, narration presets and starter names, recommended-model notes, context-inspector section titles
and warnings, state-history summaries, and the lore itself.

## Commands

Node 20+ is needed only to work on the interface (players do not need it: the built files are committed).

```
cd app/frontend
npm install
npm run dev          # http://localhost:5173, live reload, /api proxied to the running StoryCore (port 8765)
npm run build        # production build to dist-next/ (served at http://127.0.0.1:8765/next/)
npm run build:debug  # same, not minified, with readable React errors
npm run typecheck
```

## Serving

`app/backend/story/main.py` serves `dist/` at `/` and, when it exists, `dist-next/` at `/next/`. When the new
interface is validated it replaces `dist/` (build with base `/`), and `/next/` is removed.
