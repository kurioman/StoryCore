// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import * as React from "react";
import * as Icon from "lucide-react";
import { useInvalidateStory } from "@/api/queries";
import { useQuery, useMutation } from "@tanstack/react-query";
import { apiGet, apiPost, errorMessage } from "@/api/legacy";
import { msg } from "@/i18n";
import {
  Badge,
  Button,
  Callout,
  IconButton,
  Input,
  Modal,
  Portrait,
  SectionTitle,
  Spinner,
  Textarea,
  useUi,
} from "@/components/ui";
import { PickCharacterDialog } from "@/features/story/panels/CastPanel";
import { cn, shortId, timeAgo } from "@/lib/util";
import { portraitSlot, usePortraitMap } from "@/lib/portraits";
import { useStateEditor } from "@/features/lore/schemas";

export function ListEditor({ items, placeholder, onAdd, onRemove, onToggle }) {
  let [a, o] = React.useState(``);
  return (
    <div className="space-y-1">
      {items.map((e) => (
        <div className="group flex items-start gap-2 text-xs" key={e.id}>
          {onToggle && (
            <input
              type="checkbox"
              checked={!!e.done}
              onChange={() => onToggle(e.id)}
              className="mt-0.5 accent-[var(--c-accent)]"
              aria-label={msg("Resolve {{v0}}", {
                v0: e.text,
              })}
            />
          )}
          <div className={cn(`min-w-0 flex-1`, e.done && `text-faint line-through`)}>
            {e.text}
            {e.sub && <span className="block text-[11px] text-faint">{e.sub}</span>}
          </div>
          <IconButton
            label={msg("Remove {{v0}}", {
              v0: e.text,
            })}
            className="size-5 opacity-0 group-hover:opacity-100"
            onClick={() => onRemove(e.id)}
          >
            <Icon.X className="size-3" />
          </IconButton>
        </div>
      ))}
      <form
        onSubmit={(e) => {
          (e.preventDefault(), a.trim() && onAdd(a.trim()), o(``));
        }}
      >
        <Input
          value={a}
          onChange={(e) => o(e.target.value)}
          placeholder={placeholder}
          className="h-7 text-xs"
          aria-label={placeholder}
        />
      </form>
    </div>
  );
}

export function RelationsPanel({ storyId, worldId, onOpenCharacter }) {
  let stateEditor = useStateEditor(storyId),
    portraitMap = usePortraitMap(),
    [a, o] = React.useState(null),
    [s, c] = React.useState(false);
  if (!stateEditor.state) return <Spinner />;
  let l = stateEditor.state.relationships,
    u = stateEditor.q.data?.relationship_tiers ?? {},
    d = [
      [`How they see you`, l.filter((e) => !e.source_id)],
      [`Between characters`, l.filter((e) => e.source_id && e.source_id !== `protagonist`)],
      [`Your own stance`, l.filter((e) => e.source_id === `protagonist`)],
    ],
    f = (e) =>
      e.source_id
        ? e.source_id === `protagonist`
          ? `You → ${e.target_name}`
          : `${e.source_name || e.source_id} → ${e.target_name}`
        : e.target_name,
    p = (e) => (!e.source_id || e.source_id === `protagonist` ? e.target_id : e.source_id) ?? ``;
  return (
    <div className="space-y-2">
      <DuplicateRelations storyId={storyId} onMerged={() => o(null)} />
      <p className="text-[11px] text-faint">
        {msg("Progression:")}{" "}
        <span className="text-muted">
          {
            {
              relaxed: `Relaxed`,
              normal: `Normal`,
              strict: `Strict`,
            }[stateEditor.q.data?.relationship_difficulty ?? `normal`]
          }
        </span>{" "}
        {msg("(story options). Stages are derived from the values, never chosen by the AI.")}
      </p>
      {l.length === 0 && <p className="text-xs text-faint">{msg("No relationships tracked yet.")}</p>}
      {d.map(([e, t]) =>
        t.length === 0 ? null : (
          <section className="space-y-2" aria-label={e} key={e}>
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-faint">{e}</h3>
            {t.map((e) => {
              let t = u[e.id];
              return (
                <button
                  onClick={() => o(e)}
                  className="flex w-full min-w-0 gap-2.5 rounded-md border border-line p-2 text-left hover:border-line-strong"
                  key={e.id}
                >
                  <Portrait assetId={portraitSlot(portraitMap.data?.[p(e)])} name={f(e)} className="size-10 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="flex min-w-0 flex-wrap items-center justify-between gap-1">
                      <span className="truncate text-[13px] font-medium">{f(e)}</span>
                      {t && (
                        <Badge
                          tone={
                            t.kind === `positive`
                              ? `accent`
                              : t.kind === `conflicted`
                                ? `warn`
                                : t.kind === `negative` || t.kind === `fear`
                                  ? `danger`
                                  : `info`
                          }
                          title={t.reason}
                        >
                          {t.tier}
                        </Badge>
                      )}
                    </div>
                    {e.label && e.label !== `Acquaintance` && (
                      <p className="truncate text-[11px] text-muted">“{e.label}”</p>
                    )}
                    <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5">
                      {Object.entries(e.axes).map(([e, t]) => (
                        <AxisValue label={e} value={t} key={e} />
                      ))}
                    </div>
                    {e.note && <p className="mt-1 truncate text-[11px] text-muted">{e.note}</p>}
                    {t && (
                      <p className="mt-1 text-[10px] text-faint">
                        {msg("Stage:")} {t.reason}
                      </p>
                    )}
                  </div>
                </button>
              );
            })}
          </section>
        ),
      )}
      <Button size="sm" onClick={() => c(true)}>
        <Icon.UserPlus className="size-3.5" /> {msg("Track a relationship")}
      </Button>
      {a && (
        <RelationEditor
          r={a}
          axes={stateEditor.state.relationship_axes}
          assetId={portraitSlot(portraitMap.data?.[a.target_id ?? ``])}
          onClose={() => o(null)}
          onOpenHistory={a.target_id ? () => onOpenCharacter(a.target_id) : undefined}
          onSave={(e) =>
            stateEditor.save(
              (t) => void (t.relationships = t.relationships.map((t) => (t.id === e.id ? e : t))),
              `Relationship with ${e.target_name} edited`,
            )
          }
          onDelete={() =>
            stateEditor.save(
              (e) => void (e.relationships = e.relationships.filter((e) => e.id !== a.id)),
              `Stopped tracking ${a.target_name}`,
            )
          }
        />
      )}
      {s && (
        <PickCharacterDialog
          worldId={worldId}
          title={msg("Track a relationship with…")}
          onClose={() => c(false)}
          onPick={(e, t) => {
            let n = l.find(
              (n) => !n.source_id && ((e && n.target_id === e) || n.target_name.toLowerCase() === t.toLowerCase()),
            );
            n
              ? o(n)
              : stateEditor.save(
                  (n) =>
                    void n.relationships.push({
                      id: shortId(),
                      target_id: e,
                      target_name: t,
                      label: `Acquaintance`,
                      axes: Object.fromEntries(n.relationship_axes.map((e) => [e, 0])),
                      note: ``,
                      history: [],
                    }),
                  `Started tracking ${t}`,
                );
          }}
        />
      )}
    </div>
  );
}

function DuplicateRelations({ storyId, onMerged }) {
  let invalidateStory = useInvalidateStory(),
    { toast } = useUi(),
    query = useQuery({
      queryKey: [`rel-duplicates`, storyId],
      queryFn: () => apiGet(`/stories/${storyId}/relationships/duplicates`),
    }),
    [a, o] = React.useState(null),
    [s, c] = React.useState(``),
    mutation = useMutation({
      mutationFn: (t) =>
        apiPost(`/stories/${storyId}/relationships/merge`, {
          keep_id: s,
          drop_ids: t.records.map((e) => e.id).filter((e) => e !== s),
          base_version: query.data?.version,
        }),
      onSuccess: (a) => {
        (toast(
          msg("{{v0}}. Use Undo to restore both records.", {
            v0: a.summary,
          }),
        ),
          o(null),
          onMerged(),
          invalidateStory(storyId),
          query.refetch());
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    }),
    u = query.data?.duplicates ?? [];
  return u.length ? (
    <>
      <Callout tone="warn">
        {u.length} {msg("possible duplicate relationship record")}
        {u.length > 1 ? `s` : ``}
        {" ("}
        {u.map((e) => e.records[0].target_name).join(`, `)}).{" "}
        <button
          type="button"
          className="underline"
          onClick={() => {
            (o(u[0]), c(u[0].records[0].id));
          }}
        >
          {msg("Review")}
        </button>
      </Callout>
      {a && (
        <Modal
          open
          onOpenChange={(e) => !e && o(null)}
          title={msg("Duplicate records — {{v0}}", {
            v0: a.records[0].target_name,
          })}
          description={msg(
            "Choose the record whose values you want to keep. Nothing is added up; the other record's history is kept (in order) and its values are written into the history. Undo restores both.",
          )}
          footer={
            <>
              <Button variant="ghost" onClick={() => o(null)}>
                {msg("Keep both")}
              </Button>
              <Button variant="primary" loading={mutation.isPending} onClick={() => mutation.mutate(a)}>
                {msg("Merge into the chosen record")}
              </Button>
            </>
          }
        >
          <div className="space-y-2">
            {a.records.map((e) => (
              <label
                className={cn(
                  `flex cursor-pointer gap-2 rounded-md border p-2 text-xs`,
                  s === e.id ? `border-accent` : `border-line`,
                )}
                key={e.id}
              >
                <input type="radio" name="keep" checked={s === e.id} onChange={() => c(e.id)} />
                <span className="min-w-0">
                  <span className="block font-medium">
                    {e.target_name}{" "}
                    {e.target_id ? (
                      <span className="text-faint">({e.target_id})</span>
                    ) : (
                      <span className="text-faint">{msg("(no id)")}</span>
                    )}
                  </span>
                  <span className="block text-muted">
                    {Object.entries(e.axes ?? {})
                      .map(([e, t]) => `${e} ${t}`)
                      .join(` · `)}
                  </span>
                  <span className="block text-faint">
                    {e.history_count} {msg("change(s)")}
                    {e.last_change
                      ? msg(" · last {{v0}}", {
                          v0: timeAgo(e.last_change),
                        })
                      : ``}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </Modal>
      )}
    </>
  ) : null;
}

function AxisValue({ label, value }) {
  let n = (Math.max(-100, Math.min(100, value)) + 100) / 2;
  return (
    <div className="text-[10px] text-faint" title={`${label}: ${value}`}>
      <div className="flex justify-between">
        <span className="capitalize">{label}</span>
        <span className="tabular-nums">{value}</span>
      </div>
      <div className="relative h-1 rounded-full bg-line">
        <span className="absolute left-1/2 top-0 h-1 w-px bg-line-strong" />
        <span
          className={cn(`absolute top-0 h-1 rounded-full`, value >= 0 ? `bg-accent` : `bg-danger`)}
          style={
            value >= 0
              ? {
                  left: `50%`,
                  width: `${n - 50}%`,
                }
              : {
                  left: `${n}%`,
                  width: `${50 - n}%`,
                }
          }
        />
      </div>
    </div>
  );
}

function RelationEditor({ r: e, axes, assetId, onClose, onSave, onDelete, onOpenHistory }) {
  let [s, c] = React.useState(structuredClone(e)),
    [l, u] = React.useState(``),
    d = Array.from(new Set([...axes, ...Object.keys(s.axes)]));
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      title={msg("Relationship — {{v0}}", {
        v0: e.source_id
          ? `${e.source_id === `protagonist` ? `You` : e.source_name || e.source_id} → ${e.target_name}`
          : `${e.target_name} → you`,
      })}
      size="md"
      footer={
        <>
          <Button
            variant="danger"
            className="mr-auto"
            onClick={() => {
              (onDelete(), onClose());
            }}
          >
            {msg("Stop tracking")}
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              (onSave({
                ...s,
                history: [
                  ...(s.history ?? []),
                  {
                    at: new Date().toISOString(),
                    change: `Edited manually`,
                    source: `manual`,
                  },
                ],
              }),
                onClose());
            }}
          >
            {msg("Save")}
          </Button>
        </>
      }
    >
      <div className="flex gap-4">
        <Portrait assetId={assetId} name={e.target_name} variant="card" className="h-40 w-30 shrink-0" />
        <div className="flex-1 space-y-2">
          <label className="block text-xs text-muted">
            {msg("Label (how the protagonist and")} {e.target_name} {msg("stand)")}
            <Input
              value={s.label}
              onChange={(e) =>
                c({
                  ...s,
                  label: e.target.value,
                })
              }
            />
          </label>
          {d.map((e) => (
            <label className="flex items-center gap-2 text-xs" key={e}>
              <span className="w-20 capitalize text-muted">{e}</span>
              <input
                type="range"
                min={-100}
                max={100}
                value={s.axes[e] ?? 0}
                onChange={(t) =>
                  c({
                    ...s,
                    axes: {
                      ...s.axes,
                      [e]: Number(t.target.value),
                    },
                  })
                }
                className="flex-1 accent-[var(--c-accent)]"
              />
              <span className="w-8 text-right tabular-nums">{s.axes[e] ?? 0}</span>
            </label>
          ))}
          <form
            className="flex gap-1"
            onSubmit={(e) => {
              (e.preventDefault(),
                l.trim() &&
                  c({
                    ...s,
                    axes: {
                      ...s.axes,
                      [l.trim().toLowerCase()]: 0,
                    },
                  }),
                u(``));
            }}
          >
            <Input
              value={l}
              onChange={(e) => u(e.target.value)}
              placeholder={msg("Add axis (e.g. rivalry)")}
              className="h-7 text-xs"
            />
          </form>
        </div>
      </div>
      <label className="mt-3 block text-xs text-muted">
        {msg("Note")}
        <Textarea
          value={s.note ?? ``}
          onChange={(e) =>
            c({
              ...s,
              note: e.target.value,
            })
          }
          className="min-h-16"
        />
      </label>
      <SectionTitle
        action={
          onOpenHistory && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                (onClose(), onOpenHistory());
              }}
            >
              {msg("Character history in journal")}
            </Button>
          )
        }
      >
        {msg("Trend")}
      </SectionTitle>
      <ol className="max-h-48 space-y-1 overflow-y-auto">
        {(e.history ?? [])
          .slice()
          .reverse()
          .map((e, t) => (
            <li className="text-xs text-muted" key={t}>
              <span className="text-faint">{timeAgo(e.at)}</span>
              {" · "}
              {e.change} <Badge>{e.source.replace(/_/g, ` `)}</Badge>
            </li>
          ))}
        {!e.history?.length && <li className="text-xs text-faint">{msg("No changes recorded yet.")}</li>}
      </ol>
    </Modal>
  );
}
