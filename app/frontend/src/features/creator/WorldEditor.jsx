// World creator (Phase 8), one world at #/creator/<id>: a guided path in tabs, saved automatically.
// Everything is written into the world's lore pack (Lorepack/<id>_lore_pack) and the world is reloaded after each save,
// so a story started from the "Play" button always uses the saved version.
import * as React from "react";
import * as Icon from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useWorlds } from "@/api/queries";
import { errorMessage } from "@/api/client";
import { msg } from "@/i18n";
import {
  Badge, Button, Callout, ErrorCallout, Field, Input, Select, Spinner, TabPanel, Tabs, Textarea, Toggle, useUi,
} from "@/components/ui";
import { navigate } from "@/lib/router";
import { cn } from "@/lib/util";
import { creatorApi, makeId } from "./api";
import { AiSuggest, CardList, FieldInput } from "./CardList";
import { cardKinds, getPath, monthOptions } from "./fields";

const SAVE_DELAY = 1200; // ms after the last change
// lists whose cards get an id from their name (other cards and the portraits refer to it)
const WITH_IDS = [`characters`, `locations`, `groups`, `glossary`, `starters`, `posts`, `closed_groups`, `gatherings`, `places`];
// pack.json sections: a card without its name is not saved yet (it would only cause warnings)
const SECTIONS = [`stats`, `starters`, `posts`, `closed_groups`, `facts`, `gatherings`, `places`];

/** The world being edited, saved automatically: { doc, change(key, value), status, error, flush, setDoc }. */
function useAutosavedWorld(worldId) {
  let queryClient = useQueryClient(),
    [doc, setDoc] = React.useState(null),
    [loadError, setLoadError] = React.useState(null),
    [status, setStatus] = React.useState(`saved`),
    [error, setError] = React.useState(``),
    docRef = React.useRef(null),
    dirty = React.useRef(new Set()),
    timer = React.useRef(0);
  docRef.current = doc;

  React.useEffect(() => {
    creatorApi.read(worldId).then(setDoc, setLoadError);
  }, [worldId]);

  let flush = React.useCallback(async () => {
    window.clearTimeout(timer.current);
    let current = docRef.current;
    if (!current || !dirty.current.size) return;
    let keys = [...dirty.current],
      kinds = cardKinds(),
      body = {},
      withIds = { ...current };
    dirty.current.clear();
    for (let key of keys) {
      let value = current[key];
      if (WITH_IDS.includes(key)) {
        let taken = new Set((value ?? []).map((it) => it.id).filter(Boolean));
        value = (value ?? []).map((it) => {
          let name = getPath(it, kinds[key].nameKey);
          if (it.id || !name) return it;
          let id = makeId(name, taken);
          taken.add(id);
          return { id, ...it };
        });
        withIds[key] = value;
      }
      if (SECTIONS.includes(key)) value = (value ?? []).filter((it) => getPath(it, kinds[key].nameKey));
      body[key] = value;
    }
    if (WITH_IDS.some((k) => withIds[k] !== current[k])) setDoc((d) => ({ ...d, ...pick(withIds, WITH_IDS) }));
    setStatus(`saving`);
    try {
      let r = await creatorApi.save(worldId, body);
      setStatus(dirty.current.size ? `pending` : `saved`);
      setError(r.reload_error ?? ``);
      queryClient.invalidateQueries({ queryKey: [`worlds`] });
    } catch (e) {
      keys.forEach((k) => dirty.current.add(k));
      setStatus(`error`);
      setError(errorMessage(e));
    }
  }, [worldId, queryClient]);

  let change = React.useCallback(
    (key, value) => {
      setDoc((d) => ({ ...d, [key]: typeof value === `function` ? value(d[key]) : value }));
      dirty.current.add(key);
      setStatus(`pending`);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(flush, SAVE_DELAY);
    },
    [flush],
  );

  // leaving the page (or the app) never loses the last changes
  React.useEffect(() => {
    let warn = (e) => {
      if (dirty.current.size) {
        flush();
        e.preventDefault();
      }
    };
    window.addEventListener(`beforeunload`, warn);
    return () => {
      window.removeEventListener(`beforeunload`, warn);
      flush();
    };
  }, [flush]);

  /** After an image upload: the new pictures, without touching what is being typed. */
  let refreshImages = React.useCallback(async () => {
    let fresh = await creatorApi.read(worldId);
    setDoc((d) => ({ ...d, cover: fresh.cover, portraits: fresh.portraits, portrait_files: fresh.portrait_files }));
    queryClient.invalidateQueries({ queryKey: [`worlds`] });
  }, [worldId, queryClient]);

  return { doc, loadError, change, status, error, flush, refreshImages };
}

function pick(obj, keys) {
  return Object.fromEntries(keys.filter((k) => k in obj).map((k) => [k, obj[k]]));
}

function SaveStatus({ status }) {
  let shown = {
    saved: [`ok`, msg("Saved")],
    pending: [`neutral`, msg("Changes not saved yet…")],
    saving: [`neutral`, msg("Saving…")],
    error: [`danger`, msg("Not saved")],
  }[status];
  return <Badge tone={shown[0]}>{shown[1]}</Badge>;
}

export function WorldEditor({ worldId }) {
  let { doc, loadError, change, status, error, flush, refreshImages } = useAutosavedWorld(worldId),
    { confirm, toast } = useUi(),
    worlds = useWorlds(),
    [tab, setTab] = React.useState(`identity`),
    [imageVersion, setImageVersion] = React.useState(0);

  if (loadError)
    return (
      <div className="mx-auto max-w-3xl p-6">
        <ErrorCallout error={loadError} />
        <Button className="mt-3" onClick={() => navigate(`/creator`)}>
          <Icon.ArrowLeft className="size-4" /> {msg("World creator")}
        </Button>
      </div>
    );
  if (!doc)
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    );

  let kinds = cardKinds(),
    characters = (doc.characters ?? []).filter((c) => c.id).map((c) => ({ id: c.id, name: c.name || c.id })),
    world = (worlds.data ?? []).find((w) => w.slug === doc.id),
    images = { version: imageVersion, bump: () => setImageVersion((v) => v + 1), refresh: refreshImages },
    common = { worldId, characters };

  async function play() {
    await flush();
    if (world) navigate(`/new?world=${encodeURIComponent(world.id)}`);
  }

  async function removeWorld() {
    let ok = await confirm({
      title: msg("Delete the world “{{v0}}”?", { v0: doc.name }),
      body: msg("Its folder is deleted from your computer, with its pictures. This cannot be undone. Export it first if you want to keep a copy."),
      confirmLabel: msg("Delete"),
      danger: true,
    });
    if (!ok) return;
    try {
      await creatorApi.remove(worldId);
      navigate(`/creator`);
    } catch (e) {
      toast(errorMessage(e), `danger`);
    }
  }

  let tabs = [
    { value: `identity`, label: msg("1. Identity") },
    { value: `world`, label: msg("2. The world") },
    { value: `characters`, label: msg("3. Characters"), badge: <Count n={doc.characters?.length} /> },
    { value: `locations`, label: msg("4. Places"), badge: <Count n={doc.locations?.length} /> },
    { value: `groups`, label: msg("5. Groups"), badge: <Count n={doc.groups?.length} /> },
    { value: `glossary`, label: msg("6. Glossary"), badge: <Count n={doc.glossary?.length} /> },
    { value: `starters`, label: msg("7. Beginnings"), badge: <Count n={doc.starters?.length} /> },
    { value: `player`, label: msg("8. The player") },
    { value: `rules`, label: msg("9. Fixed rules") },
    { value: `check`, label: msg("10. Check and play") },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <Button size="sm" variant="ghost" onClick={() => navigate(`/creator`)} aria-label={msg("World creator")}>
          <Icon.ArrowLeft className="size-4" />
        </Button>
        <h1 className="min-w-0 truncate text-[15px] font-semibold">{doc.name || msg("(no name)")}</h1>
        <SaveStatus status={status} />
        <div className="ml-auto flex flex-wrap gap-1.5">
          <Button size="sm" variant="primary" onClick={play} disabled={!world}>
            <Icon.Play className="size-3.5" /> {msg("Play in this world")}
          </Button>
          <a href={creatorApi.exportUrl(worldId)} download onClick={() => flush()}>
            <Button size="sm" tabIndex={-1}>
              <Icon.Download className="size-3.5" /> {msg("Export (.zip)")}
            </Button>
          </a>
          <Button size="sm" variant="danger" onClick={removeWorld}>
            <Icon.Trash2 className="size-3.5" /> {msg("Delete")}
          </Button>
        </div>
      </header>
      {error && (
        <Callout tone="danger" className="mx-4 mt-2">
          {error}
        </Callout>
      )}
      <Tabs value={tab} onValueChange={setTab} tabs={tabs} className="min-h-0 flex-1">
        <TabPanel value="identity" className="p-4">
          <IdentityTab doc={doc} change={change} images={images} />
        </TabPanel>
        <TabPanel value="world" className="p-4">
          <WorldTab doc={doc} change={change} />
        </TabPanel>
        {[`characters`, `locations`, `groups`, `glossary`, `starters`].map((key) => (
          <TabPanel value={key} className="p-4" key={key}>
            <CardList
              {...common}
              kind={kinds[key]}
              items={doc[key]}
              onChange={(v) => change(key, v)}
              intro={intros()[key]}
              extra={key === `characters` ? (c) => <PortraitSlots doc={doc} character={c} images={images} /> : undefined}
              onRemove={
                key === `characters`
                  ? (c) => c.id && doc.portraits?.[c.id] && creatorApi.removePortraits(worldId, c.id).then(images.refresh)
                  : undefined
              }
            />
          </TabPanel>
        ))}
        <TabPanel value="player" className="p-4">
          <CardList {...common} kind={kinds.stats} items={doc.stats} onChange={(v) => change(`stats`, v)} intro={intros().stats} />
        </TabPanel>
        <TabPanel value="rules" className="p-4">
          <RulesTab doc={doc} change={change} common={common} kinds={kinds} />
        </TabPanel>
        <TabPanel value="check" className="p-4">
          <CheckTab worldId={worldId} flush={flush} play={play} canPlay={!!world} />
        </TabPanel>
      </Tabs>
    </div>
  );
}

function Count({ n }) {
  return n ? <span className="ml-1 rounded-full bg-panel-2 px-1.5 text-[11px] text-faint">{n}</span> : null;
}

function intros() {
  return {
    characters: msg("The people of your world. The narrator plays them. Only the name is needed; every other field helps the narrator play them well."),
    locations: msg("The places of your world. The narrator describes them and keeps them consistent."),
    groups: msg("Nations, guilds, families, gangs, orders… whatever organises your world."),
    glossary: msg("Words that only exist in your world, with their meaning."),
    starters: msg("The ways a story can begin. The player chooses one when starting a new story."),
    stats: msg("What the player's sheet shows at the start (life, money, reputation…). The narrator updates it during the story."),
  };
}

function Section({ title, children, help }) {
  return (
    <section className="mb-6 max-w-4xl">
      <h2 className="text-sm font-semibold text-fg">{title}</h2>
      {help && <p className="mb-2 mt-0.5 text-xs leading-relaxed text-muted">{help}</p>}
      <div className={help ? `` : `mt-2`}>{children}</div>
    </section>
  );
}

function IdentityTab({ doc, change, images }) {
  let { toast } = useUi(),
    input = React.useRef(null),
    [busy, setBusy] = React.useState(false);

  async function upload(file) {
    if (!file) return;
    setBusy(true);
    try {
      await creatorApi.uploadCover(doc.id, file);
      images.bump();
      await images.refresh();
    } catch (e) {
      toast(errorMessage(e), `danger`);
    } finally {
      setBusy(false);
    }
  }

  async function removeCover() {
    await creatorApi.removeCover(doc.id);
    await images.refresh();
  }

  return (
    <div className="max-w-4xl">
      <Section title={msg("Name and library card")} help={msg("How your world appears in the story library.")}>
        <div className="grid gap-3 md:grid-cols-[1fr_220px]">
          <div className="flex flex-col gap-3">
            <Field label={msg("Name of the world")}>
              <Input value={doc.name ?? ``} onChange={(e) => change(`name`, e.target.value)} />
            </Field>
            <Field
              label={msg("Pitch")}
              hint={msg("2 or 3 sentences that make people want to play ({{v0}}/600 characters).", { v0: (doc.summary ?? ``).length })}
            >
              <Textarea rows={4} maxLength={600} value={doc.summary ?? ``} onChange={(e) => change(`summary`, e.target.value)} />
            </Field>
            <Field label={msg("Genres")} hint={msg("A few words, separated by commas (e.g. Fantasy, Mystery).")}>
              <FieldInput spec={{ key: `tags`, type: `list` }} item={doc} onChange={(d) => change(`tags`, d.tags ?? [])} />
            </Field>
          </div>
          <Field label={msg("Cover")}>
            <div className="flex flex-col gap-2">
              <button
                onClick={() => input.current?.click()}
                className="flex aspect-[3/4] items-center justify-center overflow-hidden rounded-md border border-dashed border-line bg-panel-2 text-xs text-faint hover:border-accent/60"
              >
                {busy ? (
                  <Spinner />
                ) : doc.cover ? (
                  <img src={creatorApi.imageUrl(doc.id, doc.cover, images.version)} alt="" className="size-full object-cover" />
                ) : (
                  <span className="px-3 text-center">{msg("Click to choose a picture (portrait format works best)")}</span>
                )}
              </button>
              <input ref={input} type="file" accept="image/*" hidden onChange={(e) => upload(e.target.files?.[0])} />
              {doc.cover && (
                <Button size="sm" variant="ghost" onClick={removeCover}>
                  {msg("Remove the cover")}
                </Button>
              )}
            </div>
          </Field>
        </div>
      </Section>
    </div>
  );
}

function WorldTab({ doc, change }) {
  let { confirm } = useUi();

  async function applyDraft(key, text) {
    if ((doc[key] ?? ``).trim().length > 40) {
      let ok = await confirm({
        title: msg("Replace your text with the AI's draft?"),
        body: msg("Your current text will be replaced. You can still edit the draft afterwards."),
        confirmLabel: msg("Replace"),
      });
      if (!ok) return;
    }
    change(key, text);
  }

  return (
    <div className="max-w-4xl">
      <Section
        title={msg("Presentation of the world")}
        help={msg("Everything the narrator should know about the world in general: its history, geography, powers or technology, society. Write it like an encyclopedia page, with ## titles for the parts.")}
      >
        <Textarea rows={16} className="font-mono text-[13px]" value={doc.premise ?? ``} onChange={(e) => change(`premise`, e.target.value)} />
        <div className="mt-2">
          <AiSuggest worldId={doc.id} kind="premise" onDraft={(t) => applyDraft(`premise`, t)} placeholder={msg("Describe your world in a few words (genre, era, mood…)")} />
        </div>
      </Section>
      <Section
        title={msg("Narrator rules")}
        help={msg("How the narrator must tell stories in this world: tone, what to respect, what to avoid. Short bullet points work best.")}
      >
        <Textarea rows={12} className="font-mono text-[13px]" value={doc.narrator ?? ``} onChange={(e) => change(`narrator`, e.target.value)} />
        <div className="mt-2">
          <AiSuggest worldId={doc.id} kind="narrator" onDraft={(t) => applyDraft(`narrator`, t)} placeholder={msg("The tone you want (dark, funny, epic…)")} />
        </div>
      </Section>
    </div>
  );
}

function expressionNames() {
  return [msg("Neutral"), msg("Happy"), msg("Sad"), msg("Angry"), msg("Disdain"), msg("Love / shy")];
}

function PortraitSlots({ doc, character, images }) {
  let { toast } = useUi(),
    files = doc.portrait_files?.[character.id] ?? {},
    [busy, setBusy] = React.useState(0),
    input = React.useRef(null),
    target = React.useRef(1);

  if (!character.id)
    return <p className="mb-4 text-xs text-faint">{msg("Give the character a name to add portraits.")}</p>;

  async function upload(file) {
    if (!file) return;
    let n = target.current;
    setBusy(n);
    try {
      await creatorApi.uploadPortrait(doc.id, character.id, n, file);
      images.bump();
      await images.refresh();
    } catch (e) {
      toast(errorMessage(e), `danger`);
    } finally {
      setBusy(0);
    }
  }

  async function remove(n) {
    await creatorApi.removePortraits(doc.id, character.id, n);
    await images.refresh();
  }

  return (
    <div className="mb-5">
      <p className="text-xs font-medium text-muted">{msg("Portraits")}</p>
      <p className="mb-2 text-xs text-faint">
        {msg("One picture per expression. The first one (neutral) is enough: the others are used when the character shows that emotion.")}
      </p>
      <div className="grid max-w-lg grid-cols-3 gap-2 sm:grid-cols-6">
        {expressionNames().map((label, i) => {
          let n = i + 1,
            path = files[n];
          return (
            <div key={n} className="flex flex-col gap-1">
              <button
                onClick={() => {
                  target.current = n;
                  input.current?.click();
                }}
                className={cn(
                  `relative flex aspect-[3/4] items-center justify-center overflow-hidden rounded-md border bg-panel-2 text-faint`,
                  path ? `border-line` : `border-dashed border-line hover:border-accent/60`,
                )}
                title={msg("Choose a picture")}
              >
                {busy === n ? (
                  <Spinner />
                ) : path ? (
                  <img src={creatorApi.imageUrl(doc.id, path, images.version)} alt="" className="size-full object-cover" />
                ) : (
                  <Icon.ImagePlus className="size-5" />
                )}
              </button>
              <div className="flex items-center justify-between gap-1">
                <span className="truncate text-[11px] text-muted">{label}</span>
                {path && (
                  <button className="text-faint hover:text-danger" onClick={() => remove(n)} aria-label={msg("Remove")}>
                    <Icon.X className="size-3" />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <input ref={input} type="file" accept="image/*" hidden onChange={(e) => (upload(e.target.files?.[0]), (e.target.value = ``))} />
    </div>
  );
}

function RulesTab({ doc, change, common, kinds }) {
  let music = doc.music,
    calendar = doc.calendar ?? {};
  return (
    <div className="max-w-5xl">
      <Callout tone="info" className="mb-5">
        {msg("Everything here is optional. These rules help the narrator stay consistent in a big world.")}
      </Callout>
      {[
        [`posts`, msg("Unique posts")],
        [`closed_groups`, msg("Closed groups")],
        [`facts`, msg("Fixed facts")],
        [`gatherings`, msg("Gatherings")],
        [`places`, msg("Meeting places")],
      ].map(([key, title]) => (
        <details key={key} className="mb-3 rounded-lg border border-line bg-panel px-3 py-2" open={!!doc[key]?.length}>
          <summary className="cursor-pointer text-sm font-semibold">
            {title} <Count n={doc[key]?.length} />
          </summary>
          <div className="mt-3">
            <CardList {...common} kind={kinds[key]} items={doc[key]} onChange={(v) => change(key, v)} intro={kinds[key].empty} />
          </div>
        </details>
      ))}

      <Section title={msg("Calendar")} help={msg("The calendar has 12 months and 7-day weeks. You can name the years and choose the month the year starts.")}>
        <div className="grid gap-3 md:grid-cols-2">
          <Field label={msg("Name of the years")}>
            <Input
              value={calendar.year_label ?? ``}
              placeholder={msg("Year")}
              onChange={(e) => change(`calendar`, { ...calendar, year_label: e.target.value })}
            />
          </Field>
          <Field label={msg("The year starts in")}>
            <Select value={calendar.year_start ?? `January`} onChange={(e) => change(`calendar`, { ...calendar, year_start: e.target.value })}>
              {monthOptions().map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </Section>

      <Section title={msg("Other settings")}>
        <div className="flex flex-col gap-3">
          <Toggle
            checked={doc.codex !== false}
            onChange={(v) => change(`codex`, v)}
            label={msg("Codex")}
            description={msg("The in-story encyclopedia of the characters and places the player has met.")}
          />
          <Toggle
            checked={music !== false}
            onChange={(v) => change(`music`, v ? null : false)}
            label={msg("Music")}
            description={msg("Plays music from your music library, chosen by the mood of the scene.")}
          />
          {music !== false && (
            <Field label={msg("Default music tag")} hint={msg("Used at the start of a story and in unknown places (e.g. calm).")}>
              <Input
                value={music?.default ?? ``}
                onChange={(e) => change(`music`, e.target.value ? { ...(music || {}), default: e.target.value } : null)}
              />
            </Field>
          )}
          <Field label={msg("Never met by chance")} hint={msg("Roles of characters the app never suggests as a random encounter (gods, kings…). Separated by commas.")}>
            <FieldInput spec={{ key: `never_random`, type: `list` }} item={doc} onChange={(d) => change(`never_random`, d.never_random ?? [])} />
          </Field>
          <Field label={msg("Note shown when choosing this world")} hint={msg("Optional (e.g. a content warning).")}>
            <Textarea rows={2} value={doc.canon_note ?? ``} onChange={(e) => change(`canon_note`, e.target.value)} />
          </Field>
        </div>
      </Section>

      {doc.other_files?.length > 0 && (
        <Section
          title={msg("Other lore files")}
          help={msg("Files copied from the original world that the creator does not edit. They are kept and still read by the narrator.")}
        >
          <ul className="list-inside list-disc text-xs text-muted">
            {doc.other_files.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function CheckTab({ worldId, flush, play, canPlay }) {
  let [report, setReport] = React.useState(null),
    [busy, setBusy] = React.useState(false),
    [error, setError] = React.useState(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      await flush();
      setReport(await creatorApi.check(worldId));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  React.useEffect(() => {
    run();
  }, []);

  return (
    <div className="max-w-4xl">
      <Section
        title={msg("Check the world")}
        help={msg("The app loads your world as it will be played and lists what could go wrong. Errors must be fixed; warnings and tips are only advice. The messages are in English.")}
      >
        <Button size="sm" onClick={run} loading={busy}>
          <Icon.RefreshCw className="size-3.5" /> {msg("Check again")}
        </Button>
      </Section>
      {error && <ErrorCallout error={error} />}
      {report && (
        <div className="flex flex-col gap-3">
          {report.ok && !report.warnings.length && (
            <Callout tone="ok">{msg("Everything is fine: your world is ready to be played.")}</Callout>
          )}
          <Problems tone="danger" title={msg("Errors")} items={report.errors} />
          <Problems tone="warn" title={msg("Warnings")} items={report.warnings} />
          <Problems tone="info" title={msg("Tips")} items={report.info} />
          <div className="mt-2 flex gap-2">
            <Button variant="primary" onClick={play} disabled={!canPlay || !report.ok}>
              <Icon.Play className="size-4" /> {msg("Play in this world")}
            </Button>
            <a href={creatorApi.exportUrl(worldId)} download>
              <Button tabIndex={-1}>
                <Icon.Share2 className="size-4" /> {msg("Export to share (.zip)")}
              </Button>
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

function Problems({ tone, title, items }) {
  if (!items?.length) return null;
  return (
    <Callout tone={tone} title={`${title} (${items.length})`}>
      <ul className="list-inside list-disc">
        {items.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>
    </Callout>
  );
}
