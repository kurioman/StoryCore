// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useStoryState, useInvalidateStory } from "@/api/queries";
import * as React from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiPost, errorMessage, apiGet } from "@/api/legacy";
import * as Icon from "lucide-react";
import { msg, msgKey } from "@/i18n";
import {
  Badge,
  Button,
  EmptyState,
  IconButton,
  Input,
  Modal,
  SectionTitle,
  Select,
  Spinner,
  TabPanel,
  Tabs,
  Textarea,
  UploadedImage,
  useUi,
} from "@/components/ui";
import { CastPanel } from "@/features/story/panels/CastPanel";
import { ItemsPanel, QuestsPanel } from "@/features/story/panels/ItemsQuests";
import { KnownPanel } from "@/features/story/panels/KnownPanel";
import { ListEditor, RelationsPanel } from "@/features/story/panels/RelationsPanel";
import { cn, shortId, timeAgo } from "@/lib/util";
import { navigate } from "@/lib/router";
import { useStateEditor } from "@/features/lore/schemas";

export function StatusList({ title, items }) {
  return items.length ? (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-faint">{title}</p>
      <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted">
        {items.map((e) => (
          <li key={e.id}>
            {e.content}
            {e.source_seqs.length > 0 && (
              <span className="text-faint">
                {" (#"}
                {e.source_seqs.join(`, #`)})
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  ) : null;
}

export function StatusSection({ storyId, worldId, avatar, tab, setTab, onOpenCharacter, knownFocus, setKnownFocus }) {
  let c = useStoryState(storyId).data?.pending_proposals ?? 0;
  return (
    <Tabs
      value={tab}
      onValueChange={setTab}
      className="h-full"
      tabs={[
        {
          value: `status`,
          label: msg("Status"),
          badge: c ? <Badge tone="accent">{c}</Badge> : undefined,
        },
        {
          value: `known`,
          label: msg("Known"),
        },
        {
          value: `relations`,
          label: msg("Relations"),
        },
        {
          value: `cast`,
          label: msg("Cast"),
        },
        {
          value: `inventory`,
          label: msg("Items"),
        },
        {
          value: `quests`,
          label: msg("Quests"),
        },
      ]}
    >
      <TabPanel value="status" className="p-3">
        <StatusPanel storyId={storyId} avatar={avatar} />
      </TabPanel>
      <TabPanel value="known" className="p-3">
        <KnownPanel
          storyId={storyId}
          worldId={worldId}
          focus={knownFocus}
          setFocus={setKnownFocus}
          onOpenJournal={onOpenCharacter}
        />
      </TabPanel>
      <TabPanel value="relations" className="p-3">
        <RelationsPanel storyId={storyId} worldId={worldId} onOpenCharacter={onOpenCharacter} />
      </TabPanel>
      <TabPanel value="cast" className="p-3">
        <CastPanel storyId={storyId} worldId={worldId} onOpenCharacter={onOpenCharacter} />
      </TabPanel>
      <TabPanel value="inventory" className="p-3">
        <ItemsPanel storyId={storyId} />
      </TabPanel>
      <TabPanel value="quests" className="p-3">
        <QuestsPanel storyId={storyId} />
      </TabPanel>
    </Tabs>
  );
}

function StatusPanel({ storyId, avatar }) {
  let stateEditor = useStateEditor(storyId),
    invalidateStory = useInvalidateStory(),
    { toast, confirm } = useUi(),
    [o, s] = React.useState(false),
    [c, l] = React.useState(false),
    mutation = useMutation({
      mutationFn: () => apiPost(`/stories/${storyId}/state/undo`),
      onSuccess: (t) => {
        (invalidateStory(storyId), toast(t.summary));
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    });
  if (stateEditor.q.isLoading) return <Spinner />;
  if (!stateEditor.state) return <EmptyState title={msg("No state yet")} />;
  let d = stateEditor.state,
    f = d.stats.filter((e) => !e.hidden);
  return (
    <div className="space-y-4">
      <div className="flex gap-3 rounded-lg border border-line bg-panel-2/50 p-3">
        <UploadedImage path={avatar.portrait} name={d.player.name || avatar.name || `?`} className="size-16 shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-1">
            <div className="min-w-0">
              <p className="truncate font-semibold">{d.player.name || avatar.name || msg("Unnamed protagonist")}</p>
              {d.player.title && <p className="truncate text-xs text-muted">{d.player.title}</p>}
            </div>
            <IconButton label={msg("Edit player card")} onClick={() => l(true)}>
              <Icon.Pencil className="size-3.5" />
            </IconButton>
          </div>
          <p className="mt-1 truncate text-xs text-muted">
            {"📍 "}
            {d.scene.location || d.player.location || msg("Location not set")}
          </p>
          {d.player.condition && (
            <p className="truncate text-xs text-muted">
              {msg("Condition:")} {d.player.condition}
            </p>
          )}
          {avatar.id && (
            <button
              className="mt-1 text-[11px] text-accent hover:underline"
              onClick={() => navigate(`/avatars/${avatar.id}`)}
            >
              {msg("Open avatar profile")}
            </button>
          )}
        </div>
      </div>
      <section>
        <SectionTitle
          action={
            <IconButton label={o ? msg("Done editing stats") : msg("Edit stats")} active={o} onClick={() => s(!o)}>
              {o ? <Icon.Check className="size-3.5" /> : <Icon.Pencil className="size-3.5" />}
            </IconButton>
          }
        >
          {msg("Stats")}
        </SectionTitle>
        {o ? (
          <StatsEditor
            stats={d.stats}
            templates={stateEditor.q.data?.templates ?? []}
            onSave={(e, t) => stateEditor.save((t) => void (t.stats = e), t)}
          />
        ) : f.length === 0 ? (
          <p className="text-xs text-faint">{msg("No stats. Use the pencil to add some or apply a template.")}</p>
        ) : (
          <div className="space-y-2">
            {f.map((e) => (
              <StatBar
                st={e}
                onAdjust={(t) =>
                  stateEditor.change.mutate({
                    kind: `stat`,
                    payload: {
                      stat: e.id,
                      delta: t,
                    },
                  })
                }
                key={e.id}
              />
            ))}
          </div>
        )}
      </section>
      <section>
        <SectionTitle>{msg("Conditions")}</SectionTitle>
        <ListEditor
          items={d.conditions.map((e) => ({
            id: e.id,
            text: e.label,
            sub: [e.severity, e.note].filter(Boolean).join(` · `),
          }))}
          placeholder={msg("Add condition (e.g. Bruised ribs)")}
          onAdd={(e) =>
            stateEditor.change.mutate({
              kind: `condition_add`,
              payload: {
                label: e,
                severity: `moderate`,
              },
            })
          }
          onRemove={(e) => {
            let t = d.conditions.find((t) => t.id === e);
            t &&
              stateEditor.change.mutate({
                kind: `condition_remove`,
                payload: {
                  label: t.label,
                },
              });
          }}
        />
      </section>
      <div className="flex items-center gap-2 rounded-md border border-line px-2.5 py-2 text-xs">
        <div className="min-w-0 flex-1 text-muted">
          <span className="text-faint">
            {msg("State v")}
            {stateEditor.version}
          </span>
          {stateEditor.q.data?.last_change && (
            <p className="truncate">
              {msg("Last:")} {stateEditor.q.data.last_change}
            </p>
          )}
        </div>
        <Button
          size="sm"
          disabled={!stateEditor.q.data?.can_undo}
          loading={mutation.isPending}
          onClick={async () => {
            (await confirm({
              title: msg("Undo the last state change?"),
              body: (
                <>
                  {msg("This restores the previous state version (“")}
                  {stateEditor.q.data?.last_change}
                  {msg("” is reverted). The undo itself is recorded in history.")}
                </>
              ),

              confirmLabel: msg("Undo"),
            })) && mutation.mutate();
          }}
        >
          <Icon.Undo2 className="size-3.5" /> {msg("Undo")}
        </Button>
      </div>
      <ProposalsSection storyId={storyId} />
      <StateHistoryDialog storyId={storyId} />
      {c && (
        <PlayerCardDialog
          s={d}
          onClose={() => l(false)}
          onSave={(e, t) =>
            stateEditor.save(
              (n) => {
                ((n.player = e), (n.scene.location = t));
              },
              msg("Player card edited", {}),
            )
          }
        />
      )}
    </div>
  );
}

function StatBar({ st, onAdjust }) {
  let n = typeof st.value == `number`;
  if (st.type === `current_max` && n && st.max) {
    let n = Math.max(0, Math.min(1, st.value / st.max));
    return (
      <div className="group">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted">{st.label}</span>
          <span className="flex items-center gap-1 tabular-nums">
            <AdjustButtons onAdjust={onAdjust} />
            {String(st.value)}/{st.max} {st.unit}
          </span>
        </div>
        <div
          className="mt-1 h-1.5 overflow-hidden rounded-full bg-line"
          role="meter"
          aria-valuenow={st.value}
          aria-valuemax={st.max}
          aria-label={st.label}
        >
          <div
            className={cn(`h-full rounded-full`, n < 0.25 ? `bg-danger` : n < 0.5 ? `bg-warn` : `bg-accent`)}
            style={{
              width: `${n * 100}%`,
            }}
          />
        </div>
      </div>
    );
  }
  return (
    <div className="group flex items-center justify-between text-xs">
      <span className="text-muted">{st.label}</span>
      <span className="flex items-center gap-1 tabular-nums">
        {n && <AdjustButtons onAdjust={onAdjust} />}
        {st.type === `boolean` ? (st.value ? msg("Yes") : msg("No")) : String(st.value ?? `—`)} {st.unit}
      </span>
    </div>
  );
}

function AdjustButtons({ onAdjust }) {
  return (
    <span className="flex opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
      <IconButton label={msg("Decrease")} className="size-5" onClick={() => onAdjust(-1)}>
        <Icon.Minus className="size-3" />
      </IconButton>
      <IconButton label={msg("Increase")} className="size-5" onClick={() => onAdjust(1)}>
        <Icon.Plus className="size-3" />
      </IconButton>
    </span>
  );
}

function StatsEditor({ stats, templates, onSave }) {
  let [r, i] = React.useState(() => structuredClone(stats)),
    a = (e, t) =>
      i(
        r.map((n, r) =>
          r === e
            ? {
                ...n,
                ...t,
              }
            : n,
        ),
      ),
    o = (e, t) => {
      let n = e + t;
      if (n < 0 || n >= r.length) return;
      let a = [...r];
      (([a[e], a[n]] = [a[n], a[e]]), i(a));
    };
  return (
    <div className="space-y-2">
      {r.map((e, t) => (
        <div className="space-y-1.5 rounded-md border border-line p-2" key={e.id}>
          <div className="flex gap-1">
            <Input
              value={e.label}
              onChange={(e) =>
                a(t, {
                  label: e.target.value,
                })
              }
              aria-label={msg("Stat name")}
              className="h-7 flex-1"
            />

            <Select
              value={e.type}
              onChange={(e) =>
                a(t, {
                  type: e.target.value,
                })
              }
              className="h-7 w-28"
              aria-label={msg("Stat type")}
            >
              <option value="number">{msg("Number")}</option>
              <option value="current_max">{msg("Current / max")}</option>
              <option value="text">{msg("Text")}</option>
              <option value="boolean">{msg("Yes / no")}</option>
              <option value="enum">{msg("Choice")}</option>
            </Select>
          </div>
          <div className="flex items-center gap-1">
            {e.type === `boolean` ? (
              <Select
                value={e.value ? `1` : `0`}
                onChange={(e) =>
                  a(t, {
                    value: e.target.value === `1`,
                  })
                }
                className="h-7"
                aria-label={msg("Value")}
              >
                <option value="1">{msg("Yes")}</option>
                <option value="0">{msg("No")}</option>
              </Select>
            ) : e.type === `enum` ? (
              <>
                <Input
                  value={(e.options ?? []).join(`, `)}
                  onChange={(e) =>
                    a(t, {
                      options: e.target.value
                        .split(`,`)
                        .map((e) => e.trim())
                        .filter(Boolean),
                    })
                  }
                  placeholder={msg("Options, comma separated")}
                  className="h-7"
                  aria-label={msg("Options")}
                />

                <Select
                  value={String(e.value ?? ``)}
                  onChange={(e) =>
                    a(t, {
                      value: e.target.value,
                    })
                  }
                  className="h-7 w-28"
                  aria-label={msg("Value")}
                >
                  {(e.options ?? []).map((e) => (
                    <option key={e}>{e}</option>
                  ))}
                </Select>
              </>
            ) : (
              <Input
                value={String(e.value ?? ``)}
                onChange={(n) =>
                  a(t, {
                    value: e.type === `text` ? n.target.value : n.target.value === `` ? 0 : Number(n.target.value),
                  })
                }
                type={e.type === `text` ? `text` : `number`}
                className="h-7"
                aria-label={msg("Value")}
              />
            )}
            {e.type === `current_max` && (
              <Input
                value={String(e.max ?? ``)}
                onChange={(e) =>
                  a(t, {
                    max: Number(e.target.value),
                  })
                }
                type="number"
                className="h-7 w-20"
                placeholder="max"
                aria-label={msg("Maximum")}
              />
            )}
            <Input
              value={e.unit ?? ``}
              onChange={(e) =>
                a(t, {
                  unit: e.target.value,
                })
              }
              className="h-7 w-16"
              placeholder="unit"
              aria-label={msg("Unit")}
            />
          </div>
          <div className="flex justify-end gap-0.5">
            <IconButton label={msg("Move up")} onClick={() => o(t, -1)}>
              <Icon.ArrowUp className="size-3.5" />
            </IconButton>
            <IconButton label={msg("Move down")} onClick={() => o(t, 1)}>
              <Icon.ArrowDown className="size-3.5" />
            </IconButton>
            <IconButton
              label={e.hidden ? msg("Show") : msg("Hide")}
              onClick={() =>
                a(t, {
                  hidden: !e.hidden,
                })
              }
            >
              {e.hidden ? <Icon.EyeOff className="size-3.5" /> : <Icon.Eye className="size-3.5" />}
            </IconButton>
            <IconButton label={msg("Delete stat")} onClick={() => i(r.filter((e, n) => n !== t))}>
              <Icon.Trash className="size-3.5" />
            </IconButton>
          </div>
        </div>
      ))}
      <div className="flex flex-wrap gap-1.5">
        <Button
          size="sm"
          onClick={() =>
            i([
              ...r,
              {
                id: shortId(),
                label: msg("New stat"),
                type: `number`,
                value: 0,
                hidden: false,
              },
            ])
          }
        >
          <Icon.Plus className="size-3.5" /> {msg("Add stat")}
        </Button>
        <Select
          className="h-7 w-auto text-xs"
          value=""
          aria-label={msg("Add a template")}
          onChange={(e) => {
            let t = STAT_TEMPLATES[e.target.value];
            t &&
              i([
                ...r,
                ...t.map((e) => ({
                  ...e,
                  id: shortId(),
                  hidden: false,
                })),
              ]);
          }}
        >
          <option value="">{msg("Add template…")}</option>
          {templates
            .filter((e) => STAT_TEMPLATES[e])
            .map((e) => (
              <option value={e} key={e}>
                {e}
              </option>
            ))}
        </Select>
        <Button size="sm" variant="primary" className="ml-auto" onClick={() => onSave(r, msg("Stats edited", {}))}>
          {msg("Save stats")}
        </Button>
      </div>
    </div>
  );
}

var STAT_TEMPLATES = {
  fantasy: [
    {
      label: msg("HP"),
      type: `current_max`,
      value: 100,
      max: 100,
    },
    {
      label: msg("Stamina"),
      type: `current_max`,
      value: 100,
      max: 100,
    },
    {
      label: msg("Mana"),
      type: `current_max`,
      value: 50,
      max: 50,
    },
    {
      label: msg("Level"),
      type: `number`,
      value: 1,
    },
    {
      label: msg("Experience"),
      type: `current_max`,
      value: 0,
      max: 100,
      unit: `XP`,
    },
  ],

  minimal: [
    {
      label: msg("Condition"),
      type: `text`,
      value: `Healthy`,
    },
  ],
};

function PlayerCardDialog({ s, onClose, onSave }) {
  let [r, i] = React.useState(s.player),
    [a, o] = React.useState(s.scene.location);
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      title={msg("Player card")}
      size="sm"
      footer={
        <Button
          variant="primary"
          onClick={() => {
            (onSave(r, a), onClose());
          }}
        >
          {msg("Save")}
        </Button>
      }
    >
      <div className="space-y-2">
        {[`name`, `title`, `condition`].map((e) => (
          <label className="block text-xs text-muted" key={e}>
            {e[0].toUpperCase() + e.slice(1)}
            <Input
              value={r[e]}
              onChange={(t) =>
                i({
                  ...r,
                  [e]: t.target.value,
                })
              }
            />
          </label>
        ))}
        <label className="block text-xs text-muted">
          {msg("Current location")}
          <Input value={a} onChange={(e) => o(e.target.value)} />
        </label>
      </div>
    </Modal>
  );
}

function ProposalsSection({ storyId }) {
  let invalidateStory = useInvalidateStory(),
    { toast } = useUi(),
    query = useQuery({
      queryKey: [`journal`, storyId, `proposals`],
      queryFn: () => apiGet(`/stories/${storyId}/proposals`).then((e) => e.proposals),
    }),
    mutation = useMutation({
      mutationFn: ({ id, action, payload }) =>
        apiPost(`/stories/${storyId}/proposals/${id}`, {
          action,
          payload,
        }),
      onSuccess: () => invalidateStory(storyId),
      onError: (e) => toast(errorMessage(e), `danger`),
    }),
    a = useMutation({
      mutationFn: () => apiPost(`/stories/${storyId}/suggest-state`),
      onSuccess: (r) => {
        (invalidateStory(storyId),
          toast(
            r.proposals
              ? msg("{{v0}} change(s) proposed for review", { v0: r.proposals })
              : msg("No state changes suggested for the last turn", {}),

            `info`,
          ));
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    });
  return (
    <section>
      <SectionTitle
        action={
          <Button
            size="sm"
            variant="ghost"
            loading={a.isPending}
            onClick={() => a.mutate()}
            title={msg("Ask the extraction model to propose changes from the last turn")}
          >
            <Icon.Sparkles className="size-3.5" /> {msg("Suggest from last turn")}
          </Button>
        }
      >
        {msg("Proposed changes")}
      </SectionTitle>
      {query.data?.length ? (
        <div className="space-y-2">
          {query.data.map((e) => (
            <ProposalRow
              p={e}
              busy={mutation.isPending}
              onAct={(t, n) =>
                mutation.mutate({
                  id: e.id,
                  action: t,
                  payload: n,
                })
              }
              key={e.id}
            />
          ))}
        </div>
      ) : (
        <p className="text-xs text-faint">
          {msg("Nothing to review. AI-suggested changes appear here and only apply when you accept them.")}
        </p>
      )}
    </section>
  );
}

export function ProposalRow({ p, onAct, busy }) {
  let [r, i] = React.useState(false),
    [a, o] = React.useState(JSON.stringify(p.payload_json, null, 1)),
    [s, c] = React.useState(false);
  return (
    <div className="rounded-md border border-line bg-panel-2/40 p-2 text-xs">
      <div className="flex items-center gap-1.5">
        <Badge tone="accent">{msgKey(p.kind)}</Badge>
        <span className="text-faint">
          {Math.round(p.confidence * 100)}
          {msg("% confidence")}
        </span>
      </div>
      {r ? (
        <Textarea
          value={a}
          onChange={(e) => o(e.target.value)}
          className={cn(`mt-1 min-h-20 font-mono text-[11px]`, s && `border-danger`)}
          aria-label={msg("Edit proposal")}
        />
      ) : (
        <p className="mt-1 font-mono text-[11px] text-muted">
          {Object.entries(p.payload_json)
            .map(([e, t]) => `${e}: ${JSON.stringify(t)}`)
            .join(` · `)}
        </p>
      )}
      {p.rationale && <p className="mt-1 text-muted">{p.rationale}</p>}
      {p.error && <p className="mt-1 text-danger">{p.error}</p>}
      <div className="mt-1.5 flex gap-1">
        <Button
          size="sm"
          variant="primary"
          disabled={busy}
          onClick={() => {
            if (r)
              try {
                onAct(`accept`, JSON.parse(a));
              } catch {
                c(true);
              }
            else onAct(`accept`);
          }}
        >
          <Icon.Check className="size-3" /> {msg("Accept")}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => i(!r)}>
          <Icon.Pencil className="size-3" /> {r ? msg("Cancel edit") : msg("Edit")}
        </Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => onAct(`reject`)}>
          <Icon.X className="size-3" /> {msg("Reject")}
        </Button>
      </div>
    </div>
  );
}

function StateHistoryDialog({ storyId }) {
  let [t, n] = React.useState(false),
    query = useQuery({
      queryKey: [`journal`, storyId, `state-history`],
      enabled: t,
      queryFn: () => apiGet(`/stories/${storyId}/state/history`).then((e) => e.history),
    });
  return (
    <>
      <button className="text-xs text-accent hover:underline" onClick={() => n(true)}>
        {msg("View state history")}
      </button>
      <Modal
        open={t}
        onOpenChange={n}
        title={msg("State history")}
        description={msg(
          "Every change is a new version. Sources: manual, accepted AI suggestion, undo, branch fork, savepoint restore.",
        )}
      >
        <ol className="space-y-1">
          {query.data?.map((e) => (
            <li className="flex gap-2 text-xs" key={e.version}>
              <span className="w-8 shrink-0 text-faint">v{e.version}</span>
              <Badge>{msgKey(e.source)}</Badge>
              <span className="flex-1 text-muted">{e.summary}</span>
              <span className="text-faint">{timeAgo(e.created_at)}</span>
            </li>
          ))}
        </ol>
      </Modal>
    </>
  );
}
