// World creator: a list of cards (characters, places, beginnings...) with the selected card's form beside it.
// What a card contains comes from fields.js; the same component serves every list of the creator.
import * as React from "react";
import * as Icon from "lucide-react";
import { msg, shownLanguage } from "@/i18n";
import { Button, Callout, Field, Input, Select, Textarea, useUi } from "@/components/ui";
import { cn } from "@/lib/util";
import { creatorApi, makeId } from "./api";
import { getPath, setPath } from "./fields";

/** One field of a card. `characters` is the world's character list (for the character pickers); `refs` holds the
 * world's planned events and player choices (v0.6, for the event cards). */
export function FieldInput({ spec, item, onChange, characters = [], refs = {}, onNameBlur, id }) {
  let value = getPath(item, spec.key),
    set = (v) => onChange(setPath(item, spec.key, v));

  switch (spec.type) {
    case `textarea`:
      return <Textarea id={id} rows={spec.rows ?? 3} value={value ?? ``} onChange={(e) => set(e.target.value)} placeholder={spec.placeholder} />;
    case `list`:
      return <ListInput id={id} value={value} onChange={set} placeholder={spec.placeholder} />;
    case `lines`:
      return (
        <Textarea
          id={id}
          rows={3}
          value={(Array.isArray(value) ? value : value ? [value] : []).join(`\n`)}
          onChange={(e) => set(e.target.value.split(`\n`))}
          onBlur={(e) => set(e.target.value.split(`\n`).map((s) => s.trim()).filter(Boolean))}
        />
      );
    case `select`:
      return (
        <Select id={id} value={value ?? ``} onChange={(e) => set(e.target.value)}>
          {spec.options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
      );
    case `number`:
      return <Input id={id} type="number" value={value ?? ``} onChange={(e) => set(e.target.value === `` ? `` : Number(e.target.value))} />;
    case `stat_value`:
      return item.type === `text` ? (
        <Input id={id} value={value ?? ``} onChange={(e) => set(e.target.value)} />
      ) : (
        <Input id={id} type="number" value={value ?? ``} onChange={(e) => set(e.target.value === `` ? `` : Number(e.target.value))} />
      );
    case `character`:
      return (
        <Select id={id} value={value ?? ``} onChange={(e) => set(e.target.value)}>
          <option value="">{msg("(nobody)")}</option>
          {characters.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
          {value && !characters.some((c) => c.id === value) && <option value={value}>{value}</option>}
        </Select>
      );
    case `characters`:
      return <CharacterChips value={value ?? []} onChange={set} characters={characters} />;
    case `options`:
      return <OptionsInput value={value ?? []} onChange={set} />;
    case `events`:
      return (
        <Chips
          value={value ?? []}
          onChange={set}
          items={(refs.events ?? []).filter((e) => e.id && e.id !== item.id).map((e) => ({ id: e.id, name: e.title || e.id }))}
          empty={msg("No other event yet.")}
        />
      );
    case `choice`:
      return (
        <Select id={id} value={value ?? ``} onChange={(e) => set(e.target.value)}>
          <option value="">{msg("(none)")}</option>
          {(refs.choices ?? [])
            .filter((c) => c.id)
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.name || c.id}
              </option>
            ))}
          {value && !(refs.choices ?? []).some((c) => c.id === value) && <option value={value}>{value}</option>}
        </Select>
      );
    case `variants`:
      return <VariantsInput value={value ?? {}} onChange={set} choices={refs.choices ?? []} wanted={item.needs_choice} />;
    default:
      return (
        <Input
          id={id}
          value={value ?? ``}
          onChange={(e) => set(e.target.value)}
          onBlur={onNameBlur}
          placeholder={spec.placeholder}
        />
      );
  }
}

/** Words separated by commas, kept as typed while the field has the focus. */
function ListInput({ id, value, onChange, placeholder }) {
  let joined = (value ?? []).join(`, `),
    [text, setText] = React.useState(joined);
  React.useEffect(() => setText((t) => (split(t).join(`, `) === joined ? t : joined)), [joined]);
  return (
    <Input
      id={id}
      value={text}
      placeholder={placeholder}
      onChange={(e) => {
        setText(e.target.value);
        onChange(split(e.target.value));
      }}
    />
  );
}

function split(text) {
  return text.split(`,`).map((s) => s.trim()).filter(Boolean);
}

function CharacterChips({ value, onChange, characters }) {
  return <Chips value={value} onChange={onChange} items={characters} empty={msg("Add characters first.")} />;
}

/** Pick several items ({id, name}) by clicking them. */
function Chips({ value, onChange, items, empty }) {
  if (!items.length) return <p className="text-xs text-faint">{empty}</p>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((c) => {
        let on = value.includes(c.id);
        return (
          <button
            type="button"
            key={c.id}
            onClick={() => onChange(on ? value.filter((v) => v !== c.id) : [...value, c.id])}
            className={cn(
              `rounded-full border px-2.5 py-0.5 text-xs`,
              on ? `border-accent bg-accent-soft text-accent` : `border-line text-muted hover:text-fg`,
            )}
          >
            {c.name}
          </button>
        );
      })}
    </div>
  );
}

/** v0.6: the options of a player choice: a name and the words that show the player picked it. */
function OptionsInput({ value, onChange }) {
  let options = Array.isArray(value) ? value : [],
    update = (i, option) => onChange(options.map((o, j) => (j === i ? option : o))),
    giveId = (i) => {
      let option = options[i];
      if (option.id || !option.name) return;
      let taken = new Set(options.map((o) => o.id).filter(Boolean));
      update(i, { id: makeId(option.name, taken), ...option });
    };
  return (
    <div className="flex flex-col gap-2">
      {options.map((option, i) => (
        <div key={i} className="grid gap-2 rounded-md border border-line p-2 sm:grid-cols-[12rem_1fr_auto]">
          <Input
            value={option.name ?? ``}
            placeholder={msg("Option")}
            aria-label={msg("Option")}
            onChange={(e) => update(i, { ...option, name: e.target.value })}
            onBlur={() => giveId(i)}
          />
          <ListInput
            value={option.keywords ?? []}
            placeholder={msg("Words that show this choice")}
            onChange={(keywords) => update(i, { ...option, keywords })}
          />
          <Button size="sm" variant="ghost" aria-label={msg("Remove")} onClick={() => onChange(options.filter((_, j) => j !== i))}>
            <Icon.X className="size-3.5" />
          </Button>
        </div>
      ))}
      <div>
        <Button size="sm" onClick={() => onChange([...options, {}])}>
          <Icon.Plus className="size-3.5" /> {msg("Add an option")}
        </Button>
      </div>
    </div>
  );
}

/** v0.6: one text per option ("variants" of an event), for the choice the event waits for (or every choice). */
function VariantsInput({ value, onChange, choices, wanted }) {
  let shown = choices.filter((c) => c.id && (!wanted || c.id === wanted));
  if (!shown.length) return <p className="text-xs text-faint">{msg("Add a player choice first (section below).")}</p>;
  return (
    <div className="flex flex-col gap-3">
      {shown.map((c) => (
        <div key={c.id} className="flex flex-col gap-2">
          {!wanted && <p className="text-xs font-medium text-muted">{c.name || c.id}</p>}
          {(c.options ?? [])
            .filter((o) => o.id)
            .map((o) => (
              <Field key={o.id} label={o.name || o.id}>
                <Textarea
                  rows={3}
                  value={value[o.id] ?? ``}
                  onChange={(e) => {
                    let next = { ...value };
                    if (e.target.value) next[o.id] = e.target.value;
                    else delete next[o.id];
                    onChange(next);
                  }}
                />
              </Field>
            ))}
        </div>
      ))}
    </div>
  );
}

/** "Suggest with AI": a short idea, sent to the player's model; the draft comes back to `onDraft`. */
export function AiSuggest({ worldId, kind, onDraft, placeholder }) {
  let [open, setOpen] = React.useState(false),
    [idea, setIdea] = React.useState(``),
    [busy, setBusy] = React.useState(false),
    [error, setError] = React.useState(``);

  async function run() {
    setBusy(true);
    setError(``);
    try {
      let r = await creatorApi.assist(worldId, kind, idea, shownLanguage());
      onDraft(r.draft ?? r.text);
      setIdea(``);
      setOpen(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!open)
    return (
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        <Icon.Sparkles className="size-3.5" /> {msg("Suggest with AI")}
      </Button>
    );
  return (
    <div className="flex w-full flex-col gap-2 rounded-md border border-accent/40 bg-accent-soft/30 p-2.5">
      <div className="flex gap-2">
        <Input
          autoFocus
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          onKeyDown={(e) => e.key === `Enter` && !busy && run()}
          placeholder={placeholder ?? msg("Your idea in a few words (or leave empty to be surprised)")}
          className="flex-1"
        />
        <Button size="sm" variant="primary" loading={busy} onClick={run}>
          {msg("Suggest")}
        </Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => setOpen(false)}>
          {msg("Cancel")}
        </Button>
      </div>
      {busy && <p className="text-xs text-muted">{msg("The AI is writing a draft. With a local model this can take a minute.")}</p>}
      {error && <Callout tone="danger">{error}</Callout>}
    </div>
  );
}

// fields kept but never shown: the lore pack's own bookkeeping
const TECHNICAL = [`id`, `confidence`, `canon_status`, `source_ids`, `schema_version`];

function humanize(key) {
  let t = key.replace(/_/g, ` `);
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Fields the form does not know (a world copied from a pack written by hand): shown and kept, never lost. */
function OtherFields({ item, known, onChange }) {
  let keys = Object.keys(item).filter((k) => !known.includes(k) && !TECHNICAL.includes(k));
  if (!keys.length) return null;
  return (
    <details className="mt-4 rounded-md border border-line px-3 py-2" open>
      <summary className="cursor-pointer text-xs font-medium text-muted">
        {msg("Other information ({{v0}})", { v0: keys.length })}
      </summary>
      <p className="mt-1 text-xs text-faint">{msg("Information from the original world. The narrator reads it too.")}</p>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {keys.map((k) => {
          let v = item[k],
            simple = typeof v === `string` || typeof v === `number` || typeof v === `boolean`,
            words = Array.isArray(v) && v.every((x) => typeof x === `string`);
          return (
            <Field key={k} label={humanize(k)} className={simple && String(v).length < 60 ? `` : `md:col-span-2`}>
              {simple ? (
                <Textarea rows={String(v).length < 60 ? 1 : 3} value={String(v)} onChange={(e) => onChange({ ...item, [k]: e.target.value })} />
              ) : words ? (
                <ListInput value={v} onChange={(list) => onChange({ ...item, [k]: list })} />
              ) : (
                <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-md bg-panel-2 p-2 text-[11px] text-muted">
                  {JSON.stringify(v, null, 2)}
                </pre>
              )}
            </Field>
          );
        })}
      </div>
    </details>
  );
}

/**
 * The list of cards on the left, the selected card's form on the right.
 * kind: an entry of cardKinds(); items: the cards; onChange(items); extra(item, update): more content under the form
 * (the portraits of a character); onRemove(item): called before a card is removed.
 */
export function CardList({ kind, items, onChange, worldId, characters, refs, extra, onRemove, intro }) {
  let { confirm } = useUi(),
    [selected, setSelected] = React.useState(0),
    list = items ?? [],
    index = Math.min(selected, list.length - 1),
    item = index >= 0 ? list[index] : null,
    title = (it) => getPath(it, kind.nameKey) || msg("(no name)");

  function update(next) {
    onChange(list.map((it, i) => (i === index ? next : it)));
  }

  /** A card gets its permanent id from its first name (portraits and other cards refer to it). */
  function giveId() {
    if (!item || item.id || !getPath(item, kind.nameKey)) return;
    let taken = new Set(list.map((it) => it.id).filter(Boolean));
    update({ id: makeId(getPath(item, kind.nameKey), taken), ...item });
  }

  function add(card = kind.blank?.() ?? {}) {
    let next = [...list, card];
    if (card.id === undefined && getPath(card, kind.nameKey) && kind.nameKey !== `label` && kind.nameKey !== `subject`) {
      let taken = new Set(list.map((it) => it.id).filter(Boolean));
      next[next.length - 1] = { id: makeId(getPath(card, kind.nameKey), taken), ...card };
    }
    onChange(next);
    setSelected(next.length - 1);
  }

  async function remove() {
    let ok = await confirm({
      title: msg("Remove “{{v0}}”?", { v0: title(item) }),
      body: msg("It is removed from the world when the change is saved."),
      confirmLabel: msg("Remove"),
      danger: true,
    });
    if (!ok) return;
    await onRemove?.(item);
    onChange(list.filter((_, i) => i !== index));
    setSelected(Math.max(0, index - 1));
  }

  return (
    <div className="flex min-h-0 flex-col gap-3 lg:flex-row">
      <div className="flex shrink-0 flex-col gap-2 lg:w-64">
        {intro && <p className="text-xs leading-relaxed text-muted">{intro}</p>}
        <div className="flex flex-wrap gap-1.5">
          <Button size="sm" variant="primary" onClick={() => add()}>
            <Icon.Plus className="size-3.5" /> {kind.add}
          </Button>
          {kind.ai && (
            <AiSuggest worldId={worldId} kind={kind.ai} onDraft={(draft) => typeof draft === `object` && add(draft)} />
          )}
        </div>
        {!list.length && <p className="text-sm text-faint">{kind.empty}</p>}
        <ul className="flex max-h-[60vh] flex-col gap-1 overflow-y-auto">
          {list.map((it, i) => (
            <li key={i}>
              <button
                onClick={() => setSelected(i)}
                className={cn(
                  `w-full rounded-md border px-2.5 py-1.5 text-left`,
                  i === index ? `border-accent/60 bg-accent-soft/40` : `border-line hover:border-line-strong`,
                )}
              >
                <p className="truncate text-sm text-fg">{title(it)}</p>
                {kind.subtitle?.(it) && <p className="truncate text-xs text-faint">{String(kind.subtitle(it))}</p>}
              </button>
            </li>
          ))}
        </ul>
      </div>

      {item && (
        <div className="min-w-0 flex-1 rounded-lg border border-line bg-panel p-4">
          {extra?.(item, update)}
          <div className="grid gap-3 md:grid-cols-2">
            {kind.fields
              .filter((f) => !f.when || f.when(item))
              .map((f) => (
                <Field
                  key={f.key}
                  label={f.label}
                  hint={f.hint}
                  className={[`textarea`, `lines`, `characters`, `options`, `events`, `variants`].includes(f.type) ? `md:col-span-2` : ``}
                >
                  <FieldInput
                    spec={f}
                    item={item}
                    onChange={update}
                    characters={characters}
                    refs={refs}
                    onNameBlur={f.key === kind.nameKey ? giveId : undefined}
                  />
                </Field>
              ))}
          </div>
          <OtherFields item={item} known={kind.fields.map((f) => f.key.split(`.`)[0])} onChange={update} />
          <div className="mt-4 flex justify-end">
            <Button size="sm" variant="danger" onClick={remove}>
              <Icon.Trash2 className="size-3.5" /> {msg("Remove")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
