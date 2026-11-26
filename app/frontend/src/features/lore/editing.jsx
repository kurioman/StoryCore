// Kurio (24/11/2026): the Lore page edits the pack itself, on the computer and on a paired phone.
// Click a record's name or any of its fields to change it; "Add" at the end of a list makes a new record.
// The first change to an original pack goes into a renamed copy ("Lumencia Academy V2"): the original is never
// changed and stays as the backup (server: services/lore_records.py).
import * as React from "react";
import * as Icon from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPatch, apiPost, errorMessage } from "@/api/legacy";
import { queryKeys } from "@/api/queries";
import { msg } from "@/i18n";
import { Button, Field, Input, Modal, Select, Spinner, Textarea, useUi } from "@/components/ui";
import { cn } from "@/lib/util";

// the 12 categories of a character, in their order (services/lore_templates.py)
export var CHARACTER_FIELDS = [
  [`gender`, `Gender`],
  [`appearance`, `Appearance`],
  [`power`, `Power`],
  [`role`, `Role`],
  [`personality_traits`, `Personality traits`],
  [`motivation`, `Motivation`],
  [`story_functions`, `Story functions`],
  [`faction_ids`, `Factions`],
  [`notes`, `Notes`],
  [`relationships`, `Relationships`],
  [`hidden`, `Secrets`],
  [`never`, `Never`],
];
// used by the app (rosters, encounters, groups), shown apart at the bottom of a record
export var TECHNICAL_FIELDS = new Set([`type`, `department_id`, `year`, `group`, `file`]);
var NEVER_SHOWN = new Set([`id`, `name`, `term`, `title`, `confidence`, `canon_status`, `source_ids`, `schema_version`, `_index_type`]);
var REL_KEYS = [`target_id`, `type`, `note`];

export var usePackStatus = (worldId) =>
  useQuery({
    queryKey: [`pack-edit`, worldId],
    enabled: !!worldId,
    queryFn: () => apiGet(`/worlds/${worldId}/pack-edit`),
  });

/** Runs a change; the first change to an original pack asks for the copy's name, then retries. */
export function usePackSaver(worldId, onWorldChange) {
  let queryClient = useQueryClient(),
    { toast } = useUi(),
    status = usePackStatus(worldId),
    [ask, setAsk] = React.useState(null),
    done = (res) => {
      for (let k of [[`lore`], [`world`], [`lore-entity`], [`lore-raw`], [`pack-edit`], queryKeys.worlds])
        queryClient.invalidateQueries({ queryKey: k });
      if (res?.copied) {
        toast(msg("New pack “{{v0}}” created: the original stays untouched.", { v0: res.world_name }));
        onWorldChange?.(res.world_id);
      }
      return res;
    },
    run = async (fn) => {
      try {
        return done(await fn(``));
      } catch (e) {
        if (e?.status !== 409) throw e;
        let name = await new Promise((resolve) => setAsk({ resolve }));
        if (!name) return null;
        return done(await fn(name));
      }
    },
    dialog = (
      <CopyNameDialog
        open={!!ask}
        suggested={status.data?.suggested_name ?? ``}
        original={status.data?.name ?? ``}
        onDone={(name) => {
          (ask?.resolve(name), setAsk(null));
        }}
      />
    );
  return { run, dialog, status };
}

function CopyNameDialog({ open, suggested, original, onDone }) {
  let [name, setName] = React.useState(suggested);
  React.useEffect(() => {
    if (open) setName(suggested);
  }, [open, suggested]);
  return (
    <Modal
      open={open}
      onOpenChange={(o) => !o && onDone(null)}
      title={msg("First change to this pack")}
      footer={
        <>
          <Button variant="ghost" onClick={() => onDone(null)}>
            {msg("Cancel")}
          </Button>
          <Button disabled={!name.trim()} onClick={() => onDone(name.trim())}>
            {msg("Create the copy")}
          </Button>
        </>
      }
    >
      <p className="mb-3 text-sm text-muted">
        {msg(
          "“{{v0}}” is never changed: your changes go into a copy of the whole pack (portraits included), under a new name. The original stays as the backup, and the stories played in it keep it.",
          { v0: original },
        )}
      </p>
      <Field label={msg("Name of the modified pack")}>
        <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
      </Field>
    </Modal>
  );
}

var isScalar = (v) => v == null || typeof v != `object`;
var isTextList = (v) => Array.isArray(v) && v.every((x) => isScalar(x));
var isFlatObject = (v) =>
  v && typeof v == `object` && !Array.isArray(v) && Object.values(v).every((x) => isScalar(x) || isTextList(x));
var isRowList = (v) => Array.isArray(v) && v.length > 0 && v.every((x) => x && typeof x == `object` && !Array.isArray(x) && Object.values(x).every(isScalar));
var lines = (s) => s.split(`\n`).map((x) => x.trim()).filter(Boolean);

/** One field of a record, shown as text; a click opens its editor. */
export function EditableField({ label, field, value, onSave, characters, secret, children }) {
  let [editing, setEditing] = React.useState(false),
    [shown, setShown] = React.useState(!secret);
  return (
    <div className="group">
      <h3 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-faint">
        {label}
        {secret && (
          <button className="font-normal normal-case tracking-normal text-accent underline" onClick={() => setShown(!shown)}>
            {shown ? msg("hide") : msg("show (narrator only)")}
          </button>
        )}
      </h3>
      {editing ? (
        <FieldEditor
          field={field}
          value={value}
          characters={characters}
          onCancel={() => setEditing(false)}
          onSave={async (v) => {
            let ok = await onSave(field, v);
            if (ok) setEditing(false);
          }}
        />
      ) : (
        <button
          className="relative -mx-1.5 block w-[calc(100%+0.75rem)] rounded px-1.5 py-0.5 text-left hover:bg-panel-2"
          onClick={() => (shown ? setEditing(true) : setShown(true))}
          title={msg("Modify")}
        >
          {shown ? children : <p className="text-sm text-faint blur-[3px] select-none">{msg("Hidden from the player")}</p>}
          <Icon.Pencil className="absolute right-1.5 top-1.5 size-3.5 text-faint opacity-0 group-hover:opacity-100 max-md:opacity-60" />
        </button>
      )}
    </div>
  );
}

function FieldEditor({ field, value, onSave, onCancel, characters }) {
  let [busy, setBusy] = React.useState(false),
    [error, setError] = React.useState(``),
    // an empty category ({}, [], "" or nothing) is filled in as plain text: before, {} showed no input at all
    blank =
      value == null ||
      value === `` ||
      (Array.isArray(value) && value.length === 0) ||
      (typeof value == `object` && !Array.isArray(value) && Object.keys(value).length === 0),
    kind = blank && field !== `relationships`
      ? `text`
      : field === `relationships` || (isRowList(value) && Object.keys(value[0]).includes(`target_id`))
        ? `relations`
        : typeof value == `number`
          ? `number`
          : isScalar(value)
            ? `text`
            : isTextList(value)
              ? `list`
              : isFlatObject(value)
                ? `object`
                : isRowList(value)
                  ? `rows`
                  : `json`,
    [draft, setDraft] = React.useState(() =>
      kind === `list`
        ? (value ?? []).join(`\n`)
        : kind === `object`
          ? Object.fromEntries(Object.entries(value).map(([k, v]) => [k, Array.isArray(v) ? v.join(`\n`) : (v ?? ``)]))
          : kind === `relations` || kind === `rows`
            ? (Array.isArray(value) ? value : []).map((r) => ({ ...r }))
            : kind === `json`
              ? JSON.stringify(value, null, 2)
              : blank
                ? ``
                : (value ?? ``),
    ),
    result = () => {
      if (kind === `list`) return lines(draft);
      if (kind === `number`) return draft === `` ? null : Number(draft);
      if (kind === `object`)
        return Object.fromEntries(
          Object.entries(draft).map(([k, v]) => [k, Array.isArray(value[k]) ? lines(v) : typeof value[k] == `number` ? Number(v) : v]),
        );
      if (kind === `relations`)
        return draft
          .filter((r) => r.target_id)
          .map((r) => Object.fromEntries(Object.entries(r).filter(([k, v]) => k === `target_id` || k === `type` || v)));
      if (kind === `rows`) return draft.filter((r) => Object.values(r).some((v) => v !== `` && v != null));
      if (kind === `json`) return JSON.parse(draft);
      return draft;
    },
    rowKeys = kind === `rows` ? Object.keys(value[0]) : REL_KEYS;
  return (
    <div className="space-y-2 rounded-md border border-line bg-panel-2 p-2">
      {kind === `text` && (
        <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={Math.min(8, Math.max(2, String(draft).length / 70 + 1))} autoFocus />
      )}
      {kind === `number` && <Input type="number" value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus />}
      {kind === `list` && (
        <>
          <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={Math.min(10, Math.max(3, draft.split(`\n`).length + 1))} autoFocus />
          <p className="text-[11px] text-faint">{msg("One item per line.")}</p>
        </>
      )}
      {kind === `object` &&
        Object.entries(draft).map(([k, v]) => (
          <Field label={k.replace(/_/g, ` `)} key={k} hint={Array.isArray(value[k]) ? msg("One item per line.") : undefined}>
            {Array.isArray(value[k]) ? (
              <Textarea value={v} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} rows={3} />
            ) : (
              <Input value={v} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
            )}
          </Field>
        ))}
      {(kind === `relations` || kind === `rows`) && (
        <div className="space-y-1.5">
          {draft.map((r, i) => (
            <div className="flex flex-wrap items-center gap-1.5 rounded border border-line p-1.5" key={i}>
              {rowKeys.map((k) =>
                kind === `relations` && k === `target_id` ? (
                  <Select
                    key={k}
                    value={r[k] ?? ``}
                    onChange={(e) => setDraft(draft.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)))}
                    className="h-8 min-w-36 flex-1 text-xs"
                    aria-label={msg("Character")}
                  >
                    <option value="">{msg("Character…")}</option>
                    {(characters ?? []).map((c) => (
                      <option value={c.entity_id} key={c.entity_id}>
                        {c.name}
                      </option>
                    ))}
                  </Select>
                ) : (
                  <Input
                    key={k}
                    value={r[k] ?? ``}
                    placeholder={k.replace(/_/g, ` `)}
                    onChange={(e) => setDraft(draft.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)))}
                    className="h-8 min-w-36 flex-1 text-xs"
                  />
                ),
              )}
              <Button size="sm" variant="ghost" onClick={() => setDraft(draft.filter((_, j) => j !== i))} aria-label={msg("Remove")}>
                <Icon.Trash2 className="size-3.5" />
              </Button>
            </div>
          ))}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setDraft([...draft, Object.fromEntries(rowKeys.map((k) => [k, ``]))])}
          >
            <Icon.Plus className="size-3.5" /> {kind === `relations` ? msg("Add a relationship") : msg("Add a line")}
          </Button>
        </div>
      )}
      {kind === `json` && (
        <>
          <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={12} className="font-mono text-xs" autoFocus />
          <p className="text-[11px] text-faint">{msg("This field has nested parts: it is edited as JSON.")}</p>
        </>
      )}
      {error && <p className="text-xs text-danger">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onCancel}>
          {msg("Cancel")}
        </Button>
        <Button
          size="sm"
          loading={busy}
          onClick={async () => {
            let v;
            try {
              v = result();
            } catch {
              return setError(msg("This is not valid JSON."));
            }
            (setBusy(true), setError(``));
            try {
              await onSave(v);
            } finally {
              setBusy(false);
            }
          }}
        >
          <Icon.Check className="size-3.5" /> {msg("Save")}
        </Button>
      </div>
    </div>
  );
}

/** The record as written in the pack, secrets included, with every field editable. */
export function EditableRecord({ worldId, sel, header, onWorldChange }) {
  let { toast } = useUi(),
    saver = usePackSaver(worldId, onWorldChange),
    raw = useQuery({
      queryKey: [`lore-raw`, worldId, sel.category, sel.entityId],
      queryFn: () => apiGet(`/worlds/${worldId}/records/${encodeURIComponent(sel.category)}/${encodeURIComponent(sel.entityId)}/raw`),
    }),
    characters = useQuery({
      queryKey: [`lore`, worldId, `character`, ``],
      queryFn: () => apiGet(`/worlds/${worldId}/entities?category=character`).then((e) => e.entities),
    }),
    save = async (field, value) => {
      try {
        await saver.run((newName) =>
          apiPatch(`/worlds/${worldId}/records/${encodeURIComponent(sel.category)}/${encodeURIComponent(sel.entityId)}`, {
            field,
            value,
            new_name: newName,
          }),
        );
        return true;
      } catch (e) {
        toast(errorMessage(e), `danger`);
        return false;
      }
    };
  if (raw.isLoading) return <Spinner />;
  if (raw.isError) return <p className="text-sm text-danger">{errorMessage(raw.error)}</p>;
  let rec = raw.data.record,
    isChar = sel.category === `character`,
    nameKey = `name` in rec ? `name` : `term` in rec ? `term` : `title` in rec ? `title` : `name`,
    ordered = isChar
      ? [
          ...CHARACTER_FIELDS.map(([k, l]) => [k, msg(l), rec[k] ?? (k === `appearance` || k === `power` ? {} : [])]),
          ...Object.entries(rec)
            .filter(([k]) => !NEVER_SHOWN.has(k) && !TECHNICAL_FIELDS.has(k) && !CHARACTER_FIELDS.some(([c]) => c === k) && k !== `aliases`)
            .map(([k, v]) => [k, k.replace(/_/g, ` `), v]),
        ]
      : Object.entries(rec)
          .filter(([k]) => !NEVER_SHOWN.has(k) && k !== `aliases`)
          .map(([k, v]) => [k, k.replace(/_/g, ` `), v]),
    technical = isChar ? Object.entries(rec).filter(([k]) => TECHNICAL_FIELDS.has(k) && k !== `file`) : [],
    shown = (v) => <ValueView v={v} characters={characters.data} />;
  return (
    <>
      {saver.dialog}
      {header({
        name: (
          <EditableField label={null} field={nameKey} value={rec[nameKey] ?? ``} onSave={save}>
            <span className="text-xl font-semibold">{rec[nameKey] || sel.entityId}</span>
          </EditableField>
        ),
        aliases: (
          <EditableField label={msg("Also known as")} field="aliases" value={rec.aliases ?? []} onSave={save}>
            <ValueView v={rec.aliases ?? []} optional />
          </EditableField>
        ),
        file: raw.data.file,
      })}
      <div className="space-y-3">
        {ordered.map(([k, label, v]) => (
          <EditableField key={k} label={label} field={k} value={v} onSave={save} characters={characters.data} secret={k === `hidden`}>
            {shown(v)}
          </EditableField>
        ))}
      </div>
      {technical.length > 0 && (
        <details className="mt-6 rounded border border-line p-2">
          <summary className="cursor-pointer text-xs text-muted">{msg("App settings (used by the app, not sent to the narrator)")}</summary>
          <div className="mt-2 space-y-2">
            {technical.map(([k, v]) => (
              <EditableField key={k} label={k.replace(/_/g, ` `)} field={k} value={v} onSave={save}>
                {shown(v)}
              </EditableField>
            ))}
          </div>
        </details>
      )}
    </>
  );
}

function fmt(v) {
  let s = v == null || v === `` ? `—` : String(v);
  return /^[a-z0-9_]+$/.test(s) ? s.replace(/_/g, ` `) : s; // ids ("imperial_family") read as words
}

function ValueView({ v, characters, optional }) {
  let nameOf = (id) => characters?.find((c) => c.entity_id === id)?.name ?? id;
  if (v == null || v === `` || (Array.isArray(v) && v.length === 0) || (typeof v == `object` && !Array.isArray(v) && !Object.values(v).some((x) => x !== `` && x != null && !(Array.isArray(x) && !x.length))))
    return optional ? <p className="text-sm text-faint">—</p> : <p className="text-sm italic text-warn/80">{msg("— to fill in —")}</p>;
  if (isScalar(v)) return <p className="whitespace-pre-wrap text-sm text-fg/90">{fmt(v)}</p>;
  if (isTextList(v))
    return v.some((x) => String(x).length > 40) ? (
      <ul className="list-disc space-y-0.5 pl-4 text-sm text-fg/90">
        {v.map((x, i) => (
          <li key={i}>{fmt(x)}</li>
        ))}
      </ul>
    ) : (
      <p className="text-sm text-fg/90">{v.map(fmt).join(` · `)}</p>
    );
  if (Array.isArray(v))
    return (
      <ul className="space-y-1">
        {v.map((x, i) => (
          <li className="rounded border border-line px-2 py-1 text-xs text-muted" key={i}>
            {x && typeof x == `object` && `target_id` in x ? (
              <>
                <b className="text-fg">{nameOf(x.target_id)}</b> — {x.type}
                {x.note ? ` (${x.note})` : ``}
              </>
            ) : x && typeof x == `object` ? (
              Object.entries(x).map(([k, y]) => (
                <span className="mr-2" key={k}>
                  <span className="text-faint">{k.replace(/_/g, ` `)}:</span> {typeof y == `object` ? JSON.stringify(y) : fmt(y)}
                </span>
              ))
            ) : (
              fmt(x)
            )}
          </li>
        ))}
      </ul>
    );
  return (
    <dl className="grid grid-cols-[minmax(6rem,10rem)_1fr] gap-x-2 text-sm">
      {Object.entries(v).map(([k, x]) => (
        <div className="contents" key={k}>
          <dt className="text-faint">{k.replace(/_/g, ` `)}</dt>
          <dd className="text-fg/90">
            {Array.isArray(x) ? (x.length ? x.map((y) => (typeof y == `object` ? JSON.stringify(y) : fmt(y))).join(` · `) : `—`) : typeof x == `object` && x ? JSON.stringify(x) : fmt(x)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** The dashed "Add" box at the end of a list. */
export function AddRecordCard({ worldId, cats, onAdded, onWorldChange }) {
  let [open, setOpen] = React.useState(false),
    [name, setName] = React.useState(``),
    [cat, setCat] = React.useState(cats[0]),
    [file, setFile] = React.useState(``),
    [type, setType] = React.useState(``),
    [busy, setBusy] = React.useState(false),
    { toast } = useUi(),
    saver = usePackSaver(worldId, onWorldChange),
    files = saver.status.data?.character_files ?? [],
    label = (c) => msg(c.replace(/_/g, ` `));
  React.useEffect(() => setCat(cats[0]), [cats.join(`,`)]);
  React.useEffect(() => {
    if (cat === `character` && files.length && !file) (setFile(files[files.length - 1].file), setType(files[files.length - 1].type));
  }, [cat, files.length]);
  if (saver.status.data && !saver.status.data.editable) return null;
  return (
    <>
      {saver.dialog}
      <button
        onClick={() => (setName(``), setOpen(true))}
        className="mt-1 flex w-full items-center justify-center gap-1.5 rounded-md border border-dashed border-line p-3 text-xs text-muted hover:border-accent hover:text-accent"
      >
        <Icon.Plus className="size-4" />
        {cats.length === 1 ? msg("Add: {{v0}}", { v0: label(cats[0]) }) : msg("Add a record")}
      </button>
      <Modal
        open={open}
        onOpenChange={setOpen}
        title={msg("New record")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              {msg("Cancel")}
            </Button>
            <Button
              loading={busy}
              disabled={!name.trim()}
              onClick={async () => {
                setBusy(true);
                try {
                  let res = await saver.run((newName) =>
                    apiPost(`/worlds/${worldId}/records`, { category: cat, name: name.trim(), file, type, new_name: newName }),
                  );
                  if (res) (setOpen(false), onAdded?.(res));
                } catch (e) {
                  toast(errorMessage(e), `danger`);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {msg("Create")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {cats.length > 1 && (
            <Field label={msg("Kind of record")}>
              <Select value={cat} onChange={(e) => setCat(e.target.value)}>
                {cats.map((c) => (
                  <option value={c} key={c}>
                    {label(c)}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <Field label={msg("Name")}>
            <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </Field>
          {cat === `character` && (
            <>
              <Field label={msg("File of the pack")} hint={msg("Where the character is written (with the others of her kind).")}>
                <Select
                  value={file}
                  onChange={(e) => {
                    setFile(e.target.value);
                    setType(files.find((f) => f.file === e.target.value)?.type ?? ``);
                  }}
                >
                  {files.map((f) => (
                    <option value={f.file} key={f.file}>
                      {f.file}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label={msg("Type")} hint={msg("Used by the app (student, faculty, apostle...).")}>
                <Input value={type} onChange={(e) => setType(e.target.value)} />
              </Field>
            </>
          )}
          <p className="text-xs text-muted">
            {cat === `character`
              ? msg("The new character starts with the 12 empty categories: fill them in on her record.")
              : msg("The new record starts with the same fields as the others of its kind, empty.")}
          </p>
        </div>
      </Modal>
    </>
  );
}
