// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import * as React from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { apiGet, apiPost, apiPatch, errorMessage } from "@/api/legacy";
import { useWorlds, useStoryState, useInvalidateStory } from "@/api/queries";
import * as Icon from "lucide-react";
import { msg } from "@/i18n";
import {
  Badge,
  Button,
  Callout,
  EmptyState,
  Field,
  Input,
  Modal,
  Portrait,
  SectionTitle,
  Select,
  Spinner,
  TabPanel,
  Tabs,
  Textarea,
  useUi,
} from "@/components/ui";
import { MemoryList } from "@/features/story/dialogs";
import { ProposalRow } from "@/features/story/panels/StatusPanel";
import { cn, timeAgo } from "@/lib/util";
import { portraitSlot, usePortraitMap } from "@/lib/portraits";

var EVENT_TYPES = [
    `arrival`,
    `departure`,
    `promise`,
    `confrontation`,
    `injury`,
    `death`,
    `discovery`,
    `secret_revealed`,
    `item_gained`,
    `item_lost`,
    `quest_accepted`,
    `quest_completed`,
    `relationship_change`,
    `location_change`,
    `battle`,
    `faction_action`,
    `decision`,
    `conversation`,
    `other`,
  ],
  ReviewBadge = [
    `candidate`,
    `recorded_unverified`,
    `confirmed_from_transcript`,
    `confirmed`,
    `uncertain`,
    `rejected`,
    `superseded`,
  ],
  JournalTabLabel = (e) =>
    e.startsWith(`confirmed`)
      ? `ok`
      : e === `candidate` || e === `uncertain`
        ? `warn`
        : e === `rejected` || e === `superseded`
          ? `neutral`
          : `info`;

export function JournalView({ storyId, worldId, focus, onJump }) {
  let [i, a] = React.useState(focus?.character ? `characters` : `timeline`),
    query = useQuery({
      queryKey: [`journal`, storyId, `review`],
      queryFn: () => apiGet(`/stories/${storyId}/review`),
    });
  return (
    React.useEffect(() => {
      focus?.character && a(`characters`);
    }, [focus?.character]),
    (
      <Tabs
        value={i}
        onValueChange={a}
        className="h-full"
        listClassName="px-4"
        tabs={[
          {
            value: `timeline`,
            label: msg("Timeline"),
          },
          {
            value: `review`,
            label: msg("Review"),
            badge: query.data?.count ? <Badge tone="accent">{query.data.count}</Badge> : undefined,
          },
          {
            value: `memories`,
            label: msg("Memories & facts"),
          },
          {
            value: `state`,
            label: msg("Current state"),
          },
          {
            value: `characters`,
            label: msg("Characters"),
          },
          {
            value: `recaps`,
            label: msg("Recaps"),
          },
          {
            value: `maintenance`,
            label: msg("Maintenance"),
          },
        ]}
      >
        <TabPanel value="timeline">
          <TimelineTab storyId={storyId} worldId={worldId} onJump={onJump} />
        </TabPanel>
        <TabPanel value="review" className="p-4">
          <ReviewTab storyId={storyId} data={query.data} onJump={onJump} />
        </TabPanel>
        <TabPanel value="memories" className="p-4">
          <MemoriesTab storyId={storyId} onJump={onJump} />
        </TabPanel>
        <TabPanel value="state" className="p-4">
          <CurrentStateTab storyId={storyId} />
        </TabPanel>
        <TabPanel value="characters">
          <CharactersTab storyId={storyId} worldId={worldId} initial={focus?.character} onJump={onJump} />
        </TabPanel>
        <TabPanel value="recaps" className="p-4">
          <RecapsTab storyId={storyId} />
        </TabPanel>
        <TabPanel value="maintenance" className="p-4">
          <MaintenanceTab storyId={storyId} />
        </TabPanel>
      </Tabs>
    )
  );
}

function eventQuery(e, t) {
  let worlds = useWorlds(),
    storyState = useStoryState(t);
  return React.useMemo(() => {
    let t = {
      player: `Protagonist`,
    };
    for (let r of worlds.data?.find((t) => t.id === e)?.data_json.characters ?? []) t[r.id] = r.name;
    for (let r of worlds.data?.find((t) => t.id === e)?.data_json.locations ?? []) t[r.id] = r.name;
    for (let e of storyState.data?.state.npcs ?? []) t[e.id] = e.name;
    return t;
  }, [worlds.data, e, storyState.data]);
}

function TimelineTab({ storyId, worldId, onJump }) {
  let r = eventQuery(worldId, storyId),
    [i, a] = React.useState({
      q: ``,
      entity: ``,
      event_type: ``,
      status: ``,
      min_importance: `0`,
      location: ``,
    }),
    [o, s] = React.useState(null),
    [c, l] = React.useState([]),
    [u, d] = React.useState(false),
    invalidateStory = useInvalidateStory(),
    { toast } = useUi(),
    g = new URLSearchParams(Object.entries(i).filter(([, e]) => e && e !== `0`)),
    query = useQuery({
      queryKey: [`journal`, storyId, `events`, g.toString()],
      queryFn: () => apiGet(`/stories/${storyId}/events?${g}`).then((e) => e.events),
    }),
    v = query.data ?? [],
    y = v.find((e) => e.id === o) ?? null,
    b = React.useMemo(() => Array.from(new Set(v.flatMap((e) => e.entity_ids_json))), [v]),
    x = React.useMemo(() => Array.from(new Set(v.map((e) => e.location_id).filter(Boolean))), [v]);
  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-end gap-2 border-b border-line px-4 py-2.5">
          <div className="relative w-56">
            <Icon.Search className="absolute left-2 top-2.5 size-3.5 text-faint" />
            <Input
              value={i.q}
              onChange={(e) =>
                a({
                  ...i,
                  q: e.target.value,
                })
              }
              placeholder={msg("Search events")}
              className="pl-7"
              aria-label={msg("Search events")}
            />
          </div>
          <Select
            value={i.entity}
            onChange={(e) =>
              a({
                ...i,
                entity: e.target.value,
              })
            }
            className="w-40"
            aria-label={msg("Character filter")}
          >
            <option value="">{msg("All characters")}</option>
            {b.map((e) => (
              <option value={e} key={e}>
                {r[e] ?? e}
              </option>
            ))}
          </Select>
          <Select
            value={i.event_type}
            onChange={(e) =>
              a({
                ...i,
                event_type: e.target.value,
              })
            }
            className="w-36"
            aria-label={msg("Type filter")}
          >
            <option value="">{msg("All types")}</option>
            {EVENT_TYPES.map((e) => (
              <option value={e} key={e}>
                {e.replace(/_/g, ` `)}
              </option>
            ))}
          </Select>
          <Select
            value={i.status}
            onChange={(e) =>
              a({
                ...i,
                status: e.target.value,
              })
            }
            className="w-40"
            aria-label={msg("Status filter")}
          >
            <option value="">{msg("Any status (no rejected)")}</option>
            {ReviewBadge.map((e) => (
              <option value={e} key={e}>
                {e.replace(/_/g, ` `)}
              </option>
            ))}
          </Select>
          <Select
            value={i.min_importance}
            onChange={(e) =>
              a({
                ...i,
                min_importance: e.target.value,
              })
            }
            className="w-32"
            aria-label={msg("Importance filter")}
          >
            <option value="0">{msg("Any importance")}</option>
            {[2, 3, 4, 5].map((e) => (
              <option value={e} key={e}>
                {"≥ "}
                {e}
              </option>
            ))}
          </Select>
          {x.length > 0 && (
            <Select
              value={i.location}
              onChange={(e) =>
                a({
                  ...i,
                  location: e.target.value,
                })
              }
              className="w-36"
              aria-label={msg("Location filter")}
            >
              <option value="">{msg("Any location")}</option>
              {x.map((e) => (
                <option value={e} key={e}>
                  {r[e] ?? e}
                </option>
              ))}
            </Select>
          )}
          <div className="ml-auto flex gap-1.5">
            {c.length >= 2 && (
              <Button
                size="sm"
                onClick={async () => {
                  (await apiPost(`/stories/${storyId}/events/merge`, {
                    keep_id: c[0],
                    merge_ids: c.slice(1),
                  }),
                    l([]),
                    invalidateStory(storyId),
                    toast(
                      msg("Merged {{v0}} duplicate(s) into the first selected event", {
                        v0: c.length - 1,
                      }),
                    ));
                }}
              >
                <Icon.GitMerge className="size-3.5" /> {msg("Merge")} {c.length}
              </Button>
            )}
            <Button size="sm" variant="primary" onClick={() => d(true)}>
              <Icon.Plus className="size-3.5" /> {msg("Manual event")}
            </Button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          {query.isLoading && <Spinner />}
          {!query.isLoading && v.length === 0 && (
            <EmptyState title={msg("No events recorded yet")}>
              {msg(
                "Events are captured automatically every few turns (see Maintenance), or use “Save important events now”.",
              )}
            </EmptyState>
          )}
          <ol className="relative space-y-1 border-l border-line pl-4">
            {v.map((e) => (
              <li className="relative" key={e.id}>
                <span
                  className={cn(
                    `absolute -left-[21px] top-3 size-2.5 rounded-full border-2 border-bg`,
                    e.importance >= 4 ? `bg-accent` : `bg-line-strong`,
                  )}
                />
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => s(e.id)}
                  onKeyDown={(t) => t.key === `Enter` && s(e.id)}
                  className={cn(
                    `flex cursor-pointer gap-2 rounded-md px-2.5 py-2 hover:bg-panel-2`,
                    o === e.id && `bg-panel-2`,
                    (e.verification_status === `rejected` || e.verification_status === `superseded`) && `opacity-50`,
                  )}
                >
                  <input
                    type="checkbox"
                    aria-label={msg("Select for merge")}
                    checked={c.includes(e.id)}
                    onClick={(e) => e.stopPropagation()}
                    onChange={() => l(c.includes(e.id) ? c.filter((t) => t !== e.id) : [...c, e.id])}
                    className="mt-1 accent-[var(--c-accent)]"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] tabular-nums text-faint">#{e.branch_sequence}</span>
                      <span className="text-sm font-medium">{e.title}</span>
                      {e.pinned && <Icon.Pin className="size-3 text-accent" />}
                    </div>
                    <p className="line-clamp-2 text-xs text-muted">{e.summary}</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      <Badge>{e.event_type.replace(/_/g, ` `)}</Badge>
                      <Badge tone={JournalTabLabel(e.verification_status)}>
                        {e.verification_status.replace(/_/g, ` `)}
                      </Badge>
                      {e.evidence_kind !== `witnessed` && (
                        <Badge tone="warn">{e.evidence_kind.replace(/_/g, ` `)}</Badge>
                      )}
                      {e.stale && <Badge tone="warn">{msg("stale")}</Badge>}
                      {e.in_world_time && <Badge>{e.in_world_time}</Badge>}
                      {e.entity_ids_json.slice(0, 4).map((e) => (
                        <Badge tone="info" key={e}>
                          {r[e] ?? e}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
      {y && (
        <aside className="w-[380px] shrink-0 overflow-y-auto border-l border-line bg-panel p-4">
          <EventDetail e={y} storyId={storyId} names={r} onJump={onJump} onClose={() => s(null)} key={y.id} />
        </aside>
      )}
      {u && <ManualEventDialog storyId={storyId} onClose={() => d(false)} />}
    </div>
  );
}

function EventDetail({ e, storyId, names, onJump, onClose }) {
  let invalidateStory = useInvalidateStory(),
    { toast } = useUi(),
    [s, c] = React.useState(false),
    [l, u] = React.useState({
      title: e.title,
      summary: e.summary,
      event_type: e.event_type,
      importance: e.importance,
      in_world_time: e.in_world_time ?? ``,
      notes: e.notes,
      tags: e.tags_json.join(`, `),
    }),
    [d, f] = React.useState(false),
    mutation = useMutation({
      mutationFn: (n) => apiPatch(`/stories/${storyId}/events/${e.id}`, n),
      onSuccess: () => invalidateStory(storyId),
      onError: (e) => toast(errorMessage(e), `danger`),
    });
  return (
    <div className="space-y-3 text-sm">
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold">{e.title}</h3>
        <button onClick={onClose} aria-label={msg("Close details")} className="text-faint hover:text-fg">
          <Icon.X className="size-4" />
        </button>
      </div>
      {s ? (
        <div className="space-y-2">
          <Input
            value={l.title}
            onChange={(e) =>
              u({
                ...l,
                title: e.target.value,
              })
            }
            aria-label={msg("Title")}
          />
          <Textarea
            value={l.summary}
            onChange={(e) =>
              u({
                ...l,
                summary: e.target.value,
              })
            }
            aria-label={msg("Summary")}
          />
          <div className="grid grid-cols-2 gap-2">
            <Select
              value={l.event_type}
              onChange={(e) =>
                u({
                  ...l,
                  event_type: e.target.value,
                })
              }
              aria-label={msg("Type")}
            >
              {EVENT_TYPES.map((e) => (
                <option key={e}>{e}</option>
              ))}
            </Select>
            <Select
              value={String(l.importance)}
              onChange={(e) =>
                u({
                  ...l,
                  importance: Number(e.target.value),
                })
              }
              aria-label={msg("Importance")}
            >
              {[1, 2, 3, 4, 5].map((e) => (
                <option value={e} key={e}>
                  {msg("Importance")} {e}
                </option>
              ))}
            </Select>
          </div>
          <Input
            value={l.in_world_time}
            onChange={(e) =>
              u({
                ...l,
                in_world_time: e.target.value,
              })
            }
            placeholder={msg("In-world date/time")}
            aria-label={msg("In-world time")}
          />
          <Input
            value={l.tags}
            onChange={(e) =>
              u({
                ...l,
                tags: e.target.value,
              })
            }
            placeholder={msg("Tags, comma separated")}
            aria-label={msg("Tags")}
          />
          <Textarea
            value={l.notes}
            onChange={(e) =>
              u({
                ...l,
                notes: e.target.value,
              })
            }
            placeholder={msg("Notes")}
            className="min-h-14"
            aria-label={msg("Notes")}
          />
          <div className="flex justify-end gap-1.5">
            <Button size="sm" variant="ghost" onClick={() => c(false)}>
              {msg("Cancel")}
            </Button>
            <Button
              size="sm"
              variant="primary"
              onClick={() => {
                (mutation.mutate({
                  ...l,
                  in_world_time: l.in_world_time || null,
                  tags: l.tags
                    .split(`,`)
                    .map((e) => e.trim())
                    .filter(Boolean),
                }),
                  c(false));
              }}
            >
              {msg("Save")}
            </Button>
          </div>
        </div>
      ) : (
        <>
          <p className="text-muted">{e.summary}</p>
          {e.evidence_excerpt && (
            <blockquote className="border-l-2 border-line-strong pl-2 text-xs italic text-muted">
              “{e.evidence_excerpt}”
            </blockquote>
          )}
        </>
      )}
      <dl className="grid grid-cols-[7rem_1fr] gap-y-1 text-xs">
        <dt className="text-faint">{msg("Status")}</dt>
        <dd>
          <Badge tone={JournalTabLabel(e.verification_status)}>{e.verification_status.replace(/_/g, ` `)}</Badge>
        </dd>
        <dt className="text-faint">{msg("Evidence")}</dt>
        <dd>{e.evidence_kind.replace(/_/g, ` `)}</dd>
        <dt className="text-faint">{msg("Confidence")}</dt>
        <dd>{Math.round(e.confidence * 100)}%</dd>
        <dt className="text-faint">{msg("Importance")}</dt>
        <dd>
          {e.importance}
          {" / 5"}
        </dd>
        <dt className="text-faint">{msg("Characters")}</dt>
        <dd>
          {e.entity_ids_json.map((e) => names[e] ?? e).join(`, `) || `—`}
          {e.unresolved_entities_json.length > 0 && (
            <span className="text-warn">
              {" "}
              {msg("(unresolved:")} {e.unresolved_entities_json.join(`, `)})
            </span>
          )}
        </dd>
        <dt className="text-faint">{msg("Location")}</dt>
        <dd>{e.location_id ? (names[e.location_id] ?? e.location_id) : `—`}</dd>
        <dt className="text-faint">{msg("Captured")}</dt>
        <dd>
          {e.capture_method.replace(/_/g, ` `)}
          {" · "}
          {timeAgo(e.created_at)}
          {e.extraction_metadata_json.model_id && (
            <span className="text-faint">
              {" · "}
              {e.extraction_metadata_json.model_id}
            </span>
          )}
        </dd>
        <dt className="text-faint">{msg("Sources")}</dt>
        <dd className="flex flex-wrap gap-1">
          {e.source_message_ids_json.length === 0 && <span className="text-faint">{msg("none cited")}</span>}
          {e.source_message_ids_json.map((t, n) => (
            <button className="text-accent hover:underline" onClick={() => onJump(t)} key={t}>
              {msg("message #")}
              {e.source_seqs?.[n] ?? `?`}
            </button>
          ))}
        </dd>
      </dl>
      {e.stale && (
        <Callout tone="warn">
          {msg("Possibly stale:")} {e.stale_reason}
          {msg(". Compare with the source message, then confirm, edit or supersede.")}
        </Callout>
      )}
      {e.supersedes_event_id && <p className="text-xs text-faint">{msg("Correction of an earlier event (retcon).")}</p>}
      {e.notes && !s && (
        <p className="text-xs text-muted">
          {msg("Note:")} {e.notes}
        </p>
      )}
      <div className="flex flex-wrap gap-1.5 border-t border-line pt-3">
        <Button
          size="sm"
          variant="primary"
          onClick={() =>
            mutation.mutate({
              verification_status: `confirmed`,
              stale: false,
            })
          }
        >
          <Icon.Check className="size-3.5" /> {msg("Confirm")}
        </Button>
        <Button size="sm" onClick={() => c(true)}>
          {msg("Edit")}
        </Button>
        <Button
          size="sm"
          onClick={() =>
            mutation.mutate({
              pinned: !e.pinned,
            })
          }
        >
          <Icon.Pin className="size-3.5" /> {e.pinned ? msg("Unpin") : msg("Pin")}
        </Button>
        <Button
          size="sm"
          onClick={() =>
            mutation.mutate({
              verification_status: `uncertain`,
            })
          }
        >
          {msg("Mark uncertain")}
        </Button>
        <Button
          size="sm"
          onClick={() =>
            mutation.mutate({
              evidence_kind: e.evidence_kind === `rumour` ? `witnessed` : `rumour`,
            })
          }
        >
          {e.evidence_kind === `rumour` ? msg("Not a rumour") : msg("Mark rumour")}
        </Button>
        <Button size="sm" onClick={() => f(true)}>
          <Icon.RotateCcwClock className="size-3.5" /> {msg("Supersede / retcon")}
        </Button>
        <Button
          size="sm"
          variant="danger"
          onClick={() =>
            mutation.mutate({
              verification_status: `rejected`,
            })
          }
        >
          {msg("Reject")}
        </Button>
      </div>
      {d && <SupersedeEventDialog e={e} storyId={storyId} onClose={() => f(false)} />}
    </div>
  );
}

function SupersedeEventDialog({ e, storyId, onClose }) {
  let [r, i] = React.useState(e.title),
    [a, o] = React.useState(e.summary),
    [s, c] = React.useState(``),
    invalidateStory = useInvalidateStory();
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      title={msg("Supersede (retcon) this event")}
      description={msg(
        "The original stays in the journal as 'superseded' and links to the correction. A recovery savepoint is created first.",
      )}
      footer={
        <Button
          variant="primary"
          onClick={async () => {
            (await apiPost(`/stories/${storyId}/events/${e.id}/supersede`, {
              title: r,
              summary: a,
              reason: s || `Retcon / correction`,
            }),
              invalidateStory(storyId),
              onClose());
          }}
        >
          {msg("Record correction")}
        </Button>
      }
    >
      <div className="space-y-2">
        <Field label={msg("Corrected title")}>
          <Input value={r} onChange={(e) => i(e.target.value)} />
        </Field>
        <Field label={msg("Corrected summary")}>
          <Textarea value={a} onChange={(e) => o(e.target.value)} />
        </Field>
        <Field label={msg("Reason")}>
          <Input
            value={s}
            onChange={(e) => c(e.target.value)}
            placeholder={msg("e.g. I changed my mind about how the duel ended")}
          />
        </Field>
      </div>
    </Modal>
  );
}

function ManualEventDialog({ storyId, onClose }) {
  let invalidateStory = useInvalidateStory(),
    { toast } = useUi(),
    [i, a] = React.useState({
      title: ``,
      summary: ``,
      event_type: `other`,
      importance: 3,
      in_world_time: ``,
      evidence_kind: `witnessed`,
    });
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      title={msg("Manual journal event")}
      footer={
        <Button
          variant="primary"
          disabled={!i.title.trim()}
          onClick={async () => {
            try {
              (await apiPost(`/stories/${storyId}/events`, {
                ...i,
                in_world_time: i.in_world_time || null,
                verification_status: `confirmed`,
              }),
                invalidateStory(storyId),
                onClose());
            } catch (e) {
              toast(errorMessage(e), `danger`);
            }
          }}
        >
          {msg("Add event")}
        </Button>
      }
    >
      <div className="space-y-2">
        <Field label={msg("Title")}>
          <Input
            value={i.title}
            onChange={(e) =>
              a({
                ...i,
                title: e.target.value,
              })
            }
          />
        </Field>
        <Field label={msg("What happened")}>
          <Textarea
            value={i.summary}
            onChange={(e) =>
              a({
                ...i,
                summary: e.target.value,
              })
            }
          />
        </Field>
        <div className="grid grid-cols-3 gap-2">
          <Field label={msg("Type")}>
            <Select
              value={i.event_type}
              onChange={(e) =>
                a({
                  ...i,
                  event_type: e.target.value,
                })
              }
            >
              {EVENT_TYPES.map((e) => (
                <option key={e}>{e}</option>
              ))}
            </Select>
          </Field>
          <Field label={msg("Evidence")}>
            <Select
              value={i.evidence_kind}
              onChange={(e) =>
                a({
                  ...i,
                  evidence_kind: e.target.value,
                })
              }
            >
              {[`witnessed`, `claim`, `rumour`, `dream_vision`, `plan`, `hypothetical`].map((e) => (
                <option key={e}>{e}</option>
              ))}
            </Select>
          </Field>
          <Field label={msg("Importance")}>
            <Select
              value={String(i.importance)}
              onChange={(e) =>
                a({
                  ...i,
                  importance: Number(e.target.value),
                })
              }
            >
              {[1, 2, 3, 4, 5].map((e) => (
                <option key={e}>{e}</option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label={msg("In-world time (optional)")}>
          <Input
            value={i.in_world_time}
            onChange={(e) =>
              a({
                ...i,
                in_world_time: e.target.value,
              })
            }
          />
        </Field>
      </div>
    </Modal>
  );
}

function ReviewTab({ storyId, data, onJump }) {
  let invalidateStory = useInvalidateStory(),
    { toast } = useUi();
  if (!data) return <Spinner />;
  if (!data.count)
    return (
      <EmptyState title={msg("Nothing to review")}>
        {msg("Low-confidence, contradictory or stale records, and proposed state changes, appear here.")}
      </EmptyState>
    );
  let a = (t, n) =>
      apiPatch(`/stories/${storyId}/events/${t}`, n)
        .then(() => invalidateStory(storyId))
        .catch((e) => toast(errorMessage(e), `danger`)),
    o = (t, n) =>
      apiPatch(`/stories/${storyId}/facts/${t}`, n)
        .then(() => invalidateStory(storyId))
        .catch((e) => toast(errorMessage(e), `danger`));
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {data.proposals.length > 0 && (
        <section>
          <SectionTitle>
            {msg("Proposed state changes (")}
            {data.proposals.length})
          </SectionTitle>
          <div className="space-y-2">
            {data.proposals.map((t) => (
              <ProposalRow
                p={t}
                onAct={(n, a) =>
                  apiPost(`/stories/${storyId}/proposals/${t.id}`, {
                    action: n,
                    payload: a,
                  })
                    .then(() => invalidateStory(storyId))
                    .catch((e) => toast(errorMessage(e), `danger`))
                }
                key={t.id}
              />
            ))}
          </div>
        </section>
      )}
      {data.events.length > 0 && (
        <section>
          <SectionTitle>
            {msg("Events to verify (")}
            {data.events.length})
          </SectionTitle>
          <div className="space-y-2">
            {data.events.map((e) => (
              <div className="rounded-md border border-line p-3 text-sm" key={e.id}>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-medium">{e.title}</span>
                  <Badge tone={JournalTabLabel(e.verification_status)}>{e.verification_status}</Badge>
                  {e.evidence_kind !== `witnessed` && <Badge tone="warn">{e.evidence_kind}</Badge>}
                  {e.stale && <Badge tone="warn">{msg("stale")}</Badge>}
                  {e.tags_json.includes(`contradiction`) && (
                    <Badge tone="danger">
                      <Icon.TriangleAlert className="size-3" /> {msg("contradiction")}
                    </Badge>
                  )}
                  <span className="text-[11px] text-faint">{Math.round(e.confidence * 100)}%</span>
                </div>
                <p className="mt-1 text-xs text-muted">{e.summary}</p>
                {e.stale_reason && <p className="text-xs text-warn">{e.stale_reason}</p>}
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() =>
                      a(e.id, {
                        verification_status: `confirmed`,
                        stale: false,
                      })
                    }
                  >
                    <Icon.Check className="size-3" /> {msg("Accept")}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() =>
                      a(e.id, {
                        evidence_kind: `rumour`,
                        verification_status: `recorded_unverified`,
                        stale: false,
                      })
                    }
                  >
                    {msg("Keep as rumour")}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() =>
                      a(e.id, {
                        verification_status: `recorded_unverified`,
                        evidence_kind: `hypothetical`,
                        stale: false,
                      })
                    }
                  >
                    {msg("Hypothesis")}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() =>
                      a(e.id, {
                        pinned: true,
                        verification_status: `confirmed`,
                        stale: false,
                      })
                    }
                  >
                    <Icon.Pin className="size-3" /> {msg("Accept & pin")}
                  </Button>
                  {e.source_message_ids_json[0] && (
                    <Button size="sm" variant="ghost" onClick={() => onJump(e.source_message_ids_json[0])}>
                      {msg("View source")}
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() =>
                      a(e.id, {
                        verification_status: `rejected`,
                      })
                    }
                  >
                    {msg("Reject")}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      {data.facts.length > 0 && (
        <section>
          <SectionTitle>
            {msg("Facts to verify (")}
            {data.facts.length})
          </SectionTitle>
          <div className="space-y-2">
            {data.facts.map((e) => (
              <div className="rounded-md border border-line p-3 text-sm" key={e.id}>
                <p>{e.content}</p>
                <div className="mt-1 flex flex-wrap gap-1">
                  <Badge>{e.fact_kind}</Badge>
                  <Badge tone="warn">{e.status}</Badge>
                  {e.stale && <Badge tone="warn">{msg("stale")}</Badge>}
                  {e.contradicts_fact_ids_json.length > 0 && (
                    <Badge tone="danger">
                      {msg("contradicts")} {e.contradicts_fact_ids_json.length} {msg("record(s)")}
                    </Badge>
                  )}
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() =>
                      o(e.id, {
                        status: `active`,
                        stale: false,
                      })
                    }
                  >
                    <Icon.Check className="size-3" /> {msg("Accept")}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() =>
                      o(e.id, {
                        status: `active`,
                        fact_kind: `rumour`,
                        stale: false,
                      })
                    }
                  >
                    {msg("Accept as rumour")}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() =>
                      o(e.id, {
                        status: `active`,
                        pinned: true,
                        stale: false,
                      })
                    }
                  >
                    <Icon.Pin className="size-3" /> {msg("Accept & pin")}
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() =>
                      o(e.id, {
                        status: `rejected`,
                      })
                    }
                  >
                    {msg("Reject")}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function MemoriesTab({ storyId, onJump }) {
  let [n, r] = React.useState(``),
    [i, a] = React.useState(``),
    [o, s] = React.useState(false),
    query = useQuery({
      queryKey: [`journal`, storyId, `facts`, n, i],
      queryFn: () =>
        apiGet(`/stories/${storyId}/facts?perspective=${n}&q=${encodeURIComponent(i)}`).then((e) => e.facts),
    });
  return (
    <div className="mx-auto max-w-3xl space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-md border border-line p-0.5">
          {[
            {
              v: ``,
              l: `All`,
            },
            {
              v: `happened`,
              l: `What happened`,
            },
            {
              v: `player`,
              l: `What the player knows`,
            },
            {
              v: `beliefs`,
              l: `What characters believe`,
            },
            {
              v: `uncertain`,
              l: `Uncertain`,
            },
          ].map((e) => (
            <button
              onClick={() => r(e.v)}
              className={cn(`rounded px-2 py-1 text-xs`, n === e.v ? `bg-panel-2 text-fg` : `text-muted`)}
              key={e.v}
            >
              {e.l}
            </button>
          ))}
        </div>
        <Input
          value={i}
          onChange={(e) => a(e.target.value)}
          placeholder={msg("Search")}
          className="w-48"
          aria-label={msg("Search memories")}
        />
        <Button size="sm" variant="primary" className="ml-auto" onClick={() => s(true)}>
          <Icon.Plus className="size-3.5" /> {msg("New memory")}
        </Button>
      </div>
      <p className="text-[11px] text-faint">
        {msg(
          "“What the narrator knows” is everything below under “All”. Secrets list who knows them; characters without a knowledge link must not act on a secret.",
        )}
      </p>
      {query.isLoading ? <Spinner /> : <FactList facts={query.data ?? []} storyId={storyId} onJump={onJump} />}
      {o && <NewFactDialog storyId={storyId} onClose={() => s(false)} />}
    </div>
  );
}

function FactList({ facts, storyId, onJump }) {
  let invalidateStory = useInvalidateStory(),
    [i, a] = React.useState(null),
    [o, s] = React.useState(null);
  if (!facts.length) return <EmptyState title={msg("No memories here yet")} />;
  let c = (e, n) => apiPatch(`/stories/${storyId}/facts/${e.id}`, n).then(() => invalidateStory(storyId));
  return (
    <>
      <div className="space-y-1.5">
        {facts.map((e) => (
          <div className="group rounded-md border border-line p-2.5 text-sm" key={e.id}>
            <p className={cn([`rejected`, `superseded`].includes(e.status) && `text-faint line-through`)}>
              {e.content}
            </p>
            <div className="mt-1 flex flex-wrap items-center gap-1">
              <Badge tone={e.fact_kind === `secret` ? `danger` : e.fact_kind === `established` ? `neutral` : `warn`}>
                {e.fact_kind.replace(/_/g, ` `)}
              </Badge>
              <Badge tone={e.status === `active` ? `ok` : `warn`}>{e.status}</Badge>
              {e.pinned && <Badge tone="accent">{msg("pinned")}</Badge>}
              {e.stale && <Badge tone="warn">{msg("stale")}</Badge>}
              {e.knowledge_json.known_by?.length ? (
                <Badge tone="info">
                  {msg("known by")} {e.knowledge_json.known_by.join(`, `)}
                </Badge>
              ) : null}
              {e.knowledge_json.hidden_from?.length ? (
                <Badge tone="danger">
                  {msg("hidden from")} {e.knowledge_json.hidden_from.join(`, `)}
                </Badge>
              ) : null}
              {e.source_message_ids_json.map((e) => (
                <button onClick={() => onJump(e)} className="text-[11px] text-accent hover:underline" key={e}>
                  {msg("source")}
                </button>
              ))}
              <span className="ml-auto flex gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    c(e, {
                      pinned: !e.pinned,
                    })
                  }
                >
                  {e.pinned ? msg("Unpin") : msg("Pin")}
                </Button>
                {e.status !== `active` && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      c(e, {
                        status: `active`,
                        stale: false,
                      })
                    }
                  >
                    {msg("Confirm")}
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    c(e, {
                      status: `disputed`,
                    })
                  }
                >
                  {msg("Dispute")}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => s(e)}>
                  {msg("Contradicts…")}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => a(e)}>
                  {msg("Supersede")}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    c(e, {
                      status: `rejected`,
                    })
                  }
                >
                  {msg("Reject")}
                </Button>
              </span>
            </div>
          </div>
        ))}
      </div>
      {i && <CorrectFactDialog f={i} storyId={storyId} onClose={() => a(null)} />}
      {o && (
        <Modal
          open
          onOpenChange={(e) => !e && s(null)}
          title={msg("Which record does this contradict?")}
          description={msg("Both are marked disputed and linked; nothing is resolved automatically.")}
        >
          <div className="space-y-1">
            {facts
              .filter((e) => e.id !== o.id)
              .map((e) => (
                <button
                  className="block w-full rounded border border-line p-2 text-left text-xs hover:border-accent"
                  onClick={async () => {
                    (await apiPost(`/stories/${storyId}/facts/${o.id}/contradiction`, {
                      other_id: e.id,
                    }),
                      invalidateStory(storyId),
                      s(null));
                  }}
                  key={e.id}
                >
                  {e.content}
                </button>
              ))}
          </div>
        </Modal>
      )}
    </>
  );
}

function CorrectFactDialog({ f, storyId, onClose }) {
  let [r, i] = React.useState(f.content),
    invalidateStory = useInvalidateStory();
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      title={msg("Correct this fact")}
      description={msg("The old fact is kept as 'superseded' and linked to the correction.")}
      footer={
        <Button
          variant="primary"
          onClick={async () => {
            (await apiPost(`/stories/${storyId}/facts/${f.id}/supersede`, {
              content: r,
            }),
              invalidateStory(storyId),
              onClose());
          }}
        >
          {msg("Save correction")}
        </Button>
      }
    >
      <Textarea value={r} onChange={(e) => i(e.target.value)} />
    </Modal>
  );
}

function NewFactDialog({ storyId, onClose }) {
  let invalidateStory = useInvalidateStory(),
    { toast } = useUi(),
    [i, a] = React.useState({
      content: ``,
      fact_kind: `established`,
      subject_label: ``,
      known_by: ``,
      hidden_from: ``,
      importance: 3,
      pinned: false,
      scope: `story`,
    }),
    o = (e) =>
      e
        .split(`,`)
        .map((e) => e.trim())
        .filter(Boolean);
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      title={msg("New memory / fact")}
      footer={
        <Button
          variant="primary"
          disabled={!i.content.trim()}
          onClick={async () => {
            try {
              (await apiPost(`/stories/${storyId}/facts`, {
                ...i,
                known_by: o(i.known_by),
                hidden_from: o(i.hidden_from),
                subject_label: i.subject_label || null,
                category: `memory`,
              }),
                invalidateStory(storyId),
                onClose());
            } catch (e) {
              toast(errorMessage(e), `danger`);
            }
          }}
        >
          <Icon.Save className="size-4" /> {msg("Save")}
        </Button>
      }
    >
      <div className="space-y-2">
        <Field label={msg("Memory")}>
          <Textarea
            value={i.content}
            onChange={(e) =>
              a({
                ...i,
                content: e.target.value,
              })
            }
          />
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label={msg("Kind")}>
            <Select
              value={i.fact_kind}
              onChange={(e) =>
                a({
                  ...i,
                  fact_kind: e.target.value,
                })
              }
            >
              {[
                `established`,
                `witnessed`,
                `claim`,
                `rumour`,
                `belief`,
                `plan`,
                `hypothetical`,
                `dream_vision`,
                `secret`,
              ].map((e) => (
                <option key={e}>{e}</option>
              ))}
            </Select>
          </Field>
          <Field label={msg("Scope")}>
            <Select
              value={i.scope}
              onChange={(e) =>
                a({
                  ...i,
                  scope: e.target.value,
                })
              }
            >
              <option value="story">{msg("This story")}</option>
              <option value="branch">{msg("This branch only")}</option>
              <option value="global">{msg("All stories (global)")}</option>
            </Select>
          </Field>
        </div>
        <Field label={msg("About (character / thing)")}>
          <Input
            value={i.subject_label}
            onChange={(e) =>
              a({
                ...i,
                subject_label: e.target.value,
              })
            }
          />
        </Field>
        <Field label={msg("Known by (IDs or names, comma separated; 'player' for you)")}>
          <Input
            value={i.known_by}
            onChange={(e) =>
              a({
                ...i,
                known_by: e.target.value,
              })
            }
          />
        </Field>
        <Field label={msg("Must NOT be known by")}>
          <Input
            value={i.hidden_from}
            onChange={(e) =>
              a({
                ...i,
                hidden_from: e.target.value,
              })
            }
          />
        </Field>
      </div>
    </Modal>
  );
}

function CurrentStateTab({ storyId }) {
  let storyState = useStoryState(storyId);
  if (!storyState.data) return <Spinner />;
  let n = storyState.data.state,
    r = (e, t) => (
      <div className="rounded-md border border-line p-3">
        <SectionTitle>{e}</SectionTitle>
        {t.length ? (
          <ul className="space-y-0.5 text-xs text-muted">
            {t.map((e, t) => (
              <li key={t}>{e}</li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-faint">—</p>
        )}
      </div>
    );
  return (
    <div className="mx-auto grid max-w-5xl gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {r(
        `Scene`,
        [
          n.scene.location && `Location: ${n.scene.location}`,
          n.scene.date && `Date: ${n.scene.date}`,
          n.scene.time && `Time: ${n.scene.time}`,
          n.scene.weather && `Weather: ${n.scene.weather}`,
          n.scene.status && `Status: ${n.scene.status}`,
        ].filter(Boolean),
      )}
      {r(`Cast present`, n.scene.present)}
      {r(
        `Injuries & conditions`,
        n.conditions.map((e) => `${e.label} (${e.severity})`),
      )}
      {r(
        `Inventory`,
        n.inventory.map((e) => `${e.name} ×${e.qty}${e.equipped ? ` (equipped)` : ``}`),
      )}
      {r(
        `Active quests`,
        n.quests.filter((e) => e.status === `active`).map((e) => e.title),
      )}
      {r(
        `Relationships`,
        n.relationships.map(
          (e) =>
            `${e.target_name}: ${e.label} — ${Object.entries(e.axes)
              .filter(([, e]) => e)
              .map(([e, t]) => `${e} ${t}`)
              .join(`, `)}`,
        ),
      )}
      {r(
        `Known clues`,
        n.clues.filter((e) => !e.resolved).map((e) => e.text),
      )}
      {r(
        `Pending promises`,
        n.promises.filter((e) => !e.resolved).map((e) => e.text),
      )}
      {r(
        `Unresolved mysteries`,
        n.mysteries.filter((e) => !e.resolved).map((e) => e.text),
      )}
      {r(
        `Immediate goals`,
        n.goals.filter((e) => !e.resolved).map((e) => e.text),
      )}
      {r(
        `Stats`,
        n.stats
          .filter((e) => !e.hidden)
          .map((e) => `${e.label}: ${e.value}${e.max != null && e.type === `current_max` ? `/${e.max}` : ``}`),
      )}
      <p className="text-xs text-faint sm:col-span-2 lg:col-span-3">
        {msg("The current state is an editable snapshot (v")}
        {storyState.data.version}
        {msg("); edit it from the right panel. The timeline remains the record of what happened.")}
      </p>
    </div>
  );
}

function CharactersTab({ storyId, worldId, initial, onJump }) {
  let worlds = useWorlds(),
    portraitMap = usePortraitMap(),
    storyState = useStoryState(storyId),
    [s, c] = React.useState(initial);
  React.useEffect(() => c(initial), [initial]);
  let l = [
      ...(worlds.data?.find((e) => e.id === worldId)?.data_json.characters ?? []),
      ...(storyState.data?.state.npcs ?? []).map((e) => ({
        id: e.id,
        name: e.name,
        type: `local npc`,
      })),
    ],
    query = useQuery({
      queryKey: [`journal`, storyId, `char`, s],
      enabled: !!s,
      queryFn: () => apiGet(`/stories/${storyId}/characters/${s}/history`),
    });
  return (
    <div className="flex h-full min-h-0">
      <div className="w-56 shrink-0 overflow-y-auto border-r border-line p-2">
        {l.map((e) => (
          <button
            onClick={() => c(e.id)}
            className={cn(
              `flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs hover:bg-panel-2`,
              s === e.id && `bg-panel-2`,
            )}
            key={e.id}
          >
            <Portrait
              assetId={portraitSlot(portraitMap.data?.[e.id])}
              name={e.name}
              className="size-7 shrink-0"
              rounded="rounded-full"
            />
            <span className="truncate">{e.name}</span>
          </button>
        ))}
        {l.length === 0 && <p className="p-2 text-xs text-faint">{msg("No characters known for this story.")}</p>}
      </div>
      <div className="min-w-0 flex-1 overflow-y-auto p-4">
        {!s && <EmptyState title={msg("Choose a character")} />}
        {query.isLoading && <Spinner />}
        {query.data && (
          <div className="mx-auto max-w-3xl space-y-5">
            <div className="flex items-center gap-3">
              <Portrait
                assetId={portraitSlot(portraitMap.data?.[query.data.character_id])}
                name={query.data.name}
                variant="card"
                className="h-24 w-18"
              />
              <div>
                <h2 className="text-lg font-semibold">{query.data.name}</h2>
                {query.data.relationship ? (
                  <p className="text-sm text-muted">
                    {query.data.relationship.label}
                    {" · "}
                    {Object.entries(query.data.relationship.axes)
                      .map(([e, t]) => `${e} ${t}`)
                      .join(`, `)}
                  </p>
                ) : (
                  <p className="text-sm text-faint">{msg("Relationship not tracked.")}</p>
                )}
              </div>
            </div>
            <section>
              <SectionTitle>
                {msg("Notable events (")}
                {query.data.events.length})
              </SectionTitle>
              {query.data.events.map((e) => (
                <div className="mb-1 flex gap-2 text-sm" key={e.id}>
                  <span className="w-8 shrink-0 text-xs text-faint">#{e.branch_sequence}</span>
                  <span className="flex-1">
                    <b className="font-medium">{e.title}</b>{" "}
                    <span className="text-muted">
                      {"— "}
                      {e.summary}
                    </span>
                  </span>
                  {e.source_message_ids_json[0] && (
                    <button
                      className="text-xs text-accent hover:underline"
                      onClick={() => onJump(e.source_message_ids_json[0])}
                    >
                      {msg("source")}
                    </button>
                  )}
                </div>
              ))}
              {!query.data.events.length && <p className="text-xs text-faint">{msg("None recorded.")}</p>}
            </section>
            <section>
              <SectionTitle>
                {msg("Facts about")} {query.data.name}
              </SectionTitle>
              <MemoryList facts={query.data.facts_about} storyId={storyId} onJump={onJump} />
            </section>
            <section>
              <SectionTitle>
                {msg("Secrets")} {query.data.name} {msg("knows")}
              </SectionTitle>
              <MemoryList facts={query.data.secrets_known} storyId={storyId} onJump={onJump} />
            </section>
            <section>
              <SectionTitle>
                {msg("Kept from")} {query.data.name}
              </SectionTitle>
              <MemoryList facts={query.data.kept_from} storyId={storyId} onJump={onJump} />
            </section>
            <section>
              <SectionTitle>
                {query.data.name}
                {msg("'s beliefs")}
              </SectionTitle>
              <MemoryList facts={query.data.beliefs} storyId={storyId} onJump={onJump} />
            </section>
            {query.data.relationship?.history?.length ? (
              <section>
                <SectionTitle>{msg("Relationship changes")}</SectionTitle>
                {query.data.relationship.history.map((e, t) => (
                  <p className="text-xs text-muted" key={t}>
                    {timeAgo(e.at)}
                    {" · "}
                    {e.change}
                  </p>
                ))}
              </section>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}

function RecapsTab({ storyId }) {
  let query = useQuery({
      queryKey: [`journal`, storyId, `recaps`],
      queryFn: () => apiGet(`/stories/${storyId}/recaps`).then((e) => e.recaps),
    }),
    invalidateStory = useInvalidateStory(),
    [r, i] = React.useState(null),
    [a, o] = React.useState(false),
    [s, c] = React.useState(``);
  return (
    <div className="mx-auto max-w-3xl space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted">
          {msg("Recaps summarise older history. The transcript is always preserved in full.")}
        </p>
        <Button
          size="sm"
          onClick={() => {
            (c(``), o(true));
          }}
        >
          <Icon.Plus className="size-3.5" /> {msg("Write recap")}
        </Button>
      </div>
      {query.data?.length === 0 && (
        <EmptyState title={msg("No recaps yet")}>{msg("Use /recap in the composer to generate one.")}</EmptyState>
      )}
      {query.data?.map((t) => (
        <div
          className={cn(`rounded-md border p-3`, t.status === `active` ? `border-accent/50` : `border-line`)}
          key={t.id}
        >
          <div className="mb-1 flex flex-wrap items-center gap-1.5 text-xs">
            <b>v{t.version}</b>
            <Badge tone={t.status === `active` ? `accent` : `neutral`}>{t.status}</Badge>
            <Badge>{t.source}</Badge>
            <span className="text-faint">
              {msg("covers up to #")}
              {t.end_seq}
              {" · "}
              {timeAgo(t.created_at)}
            </span>
            <span className="ml-auto flex gap-1">
              {t.status !== `active` && (
                <Button
                  size="sm"
                  onClick={async () => {
                    (await apiPatch(`/stories/${storyId}/recaps/${t.id}`, {
                      status: `active`,
                    }),
                      invalidateStory(storyId));
                  }}
                >
                  {msg("Make active")}
                </Button>
              )}
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  (i(t), c(t.content));
                }}
              >
                {msg("Edit")}
              </Button>
            </span>
          </div>
          <p className="line-clamp-6 whitespace-pre-wrap text-sm text-muted">{t.content}</p>
        </div>
      ))}
      {(r || a) && (
        <Modal
          open
          onOpenChange={(e) => {
            e || (i(null), o(false));
          }}
          title={
            r
              ? msg("Edit recap v{{v0}}", {
                  v0: r.version,
                })
              : msg("New recap")
          }
          size="lg"
          footer={
            <Button
              variant="primary"
              onClick={async () => {
                (r
                  ? await apiPatch(`/stories/${storyId}/recaps/${r.id}`, {
                      content: s,
                    })
                  : await apiPost(`/stories/${storyId}/recaps`, {
                      content: s,
                      activate: true,
                    }),
                  invalidateStory(storyId),
                  i(null),
                  o(false));
              }}
            >
              {msg("Save")}
            </Button>
          }
        >
          <Textarea value={s} onChange={(e) => c(e.target.value)} className="min-h-80" />
        </Modal>
      )}
    </div>
  );
}

function maintenanceSummary(e) {
  let t = e.remaining_messages ? ` ${e.remaining_messages} message(s) still waiting — run it again to continue.` : ``;
  if (e.status === `nothing_to_do`) return [`Nothing new to process.`, `info`];
  if (e.status === `skipped` && e.skipped)
    return [`Skipped messages #${e.skipped[0]}–#${e.skipped[1]} (not captured).${t}`, `warn`];
  if (e.status === `failed`) return [`Capture failed: ${e.error ?? `unknown error`}`, `danger`];
  let n = `Saved ${e.events ?? 0} event(s), ${e.facts ?? 0} fact(s), ${e.proposals ?? 0} proposal(s)${e.processed ? ` from #${e.processed[0]}–#${e.processed[1]}` : ``}`;
  return e.status === `partial`
    ? [`${n}; then a chunk failed: ${e.error ?? ``}`, `warn`]
    : [`${n}; ${e.duplicates_skipped ?? 0} duplicate(s) skipped.${t}`, `ok`];
}

function MaintenanceTab({ storyId }) {
  let query = useQuery({
      queryKey: [`journal`, storyId, `maint`],
      queryFn: () => apiGet(`/stories/${storyId}/maintenance`),
    }),
    n = useQuery({
      queryKey: [`journal`, storyId, `runs`],
      queryFn: () => apiGet(`/stories/${storyId}/extract/runs`).then((e) => e.runs),
    }),
    invalidateStory = useInvalidateStory(),
    { toast, confirm } = useUi(),
    [o, s] = React.useState(`0`),
    mutation = useMutation({
      mutationFn: (t) =>
        t === `now`
          ? apiPost(`/stories/${storyId}/extract`)
          : t === `rebuild`
            ? apiPost(`/stories/${storyId}/extract/rebuild`, {
                from_seq: Number(o),
              })
            : t === `skip`
              ? apiPost(`/stories/${storyId}/extract/skip`, {
                  confirm: true,
                })
              : t.startsWith(`retry:`)
                ? apiPost(`/stories/${storyId}/extract/runs/${t.slice(6)}/retry`)
                : apiPost(`/stories/${storyId}/reconcile`).then(
                    (e) =>
                      e.re_extraction ?? {
                        status: `succeeded`,
                      },
                  ),
      onSuccess: (t) => {
        invalidateStory(storyId);
        let [n, a] = maintenanceSummary(t);
        toast(n, a);
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    });
  if (!query.data) return <Spinner />;
  let l = query.data,
    u = (e, t) => (
      <div className="rounded-md border border-line p-2.5">
        <p className="text-[11px] text-faint">{e}</p>
        <p className="text-sm font-medium">{t}</p>
      </div>
    );
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {u(`Transcript`, `${l.transcript_messages} messages`)}
        {u(`Processed up to`, l.last_processed_seq >= 0 ? `#${l.last_processed_seq} of #${l.head_seq}` : `nothing yet`)}
        {u(
          `Last successful extraction`,
          l.last_successful_extraction ? timeAgo(l.last_successful_extraction) : `never`,
        )}
        {u(
          `Capture mode`,
          `${l.capture_mode}${l.capture_mode === `batch` ? ` (every ${l.batch_every}, ${l.turns_since_extraction} since)` : ``}`,
        )}
        {u(`Events`, `${l.events_total} (${l.events_candidates} to review)`)}
        {u(`Active memories`, `${l.facts_active} (${l.facts_candidates} candidates)`)}
        {u(`Stale records`, l.stale_records)}
        {u(`Pending state proposals`, l.pending_proposals)}
        {u(`Rolling recap`, l.recap ? `v${l.recap.version} up to #${l.recap.end_seq}` : `none`)}
        {u(`Last full backup`, l.last_backup ? timeAgo(l.last_backup) : `never`)}
      </div>
      {l.capture_paused ? (
        <Callout tone="warn" title={msg("Automatic memory capture is paused")}>
          {l.capture_paused} {msg("The story itself is unaffected. Each click below processes at most a few chunks of")}{" "}
          {l.chunk_max_messages ?? 6} {msg("messages (one model request each).")}
        </Callout>
      ) : (
        l.last_failed_extraction && (
          <Callout tone="danger" title={msg("Last extraction failed")}>
            {l.last_failed_extraction.error} {msg("— the transcript is unaffected; retry below.")}
          </Callout>
        )
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          loading={mutation.isPending && mutation.variables === `now`}
          onClick={() => mutation.mutate(`now`)}
          disabled={!l.capturable_messages && l.capturable_messages !== undefined}
        >
          <Icon.Save className="size-4" />{" "}
          {l.capture_paused ? msg("Process next chunks") : msg("Save important events now")}
          {" ("}
          {l.capturable_messages ?? l.unprocessed_messages} {msg("waiting)")}
        </Button>
        {l.next_chunk && (l.capture_paused || l.last_failed_extraction) && (
          <Button
            loading={mutation.isPending && mutation.variables === `skip`}
            onClick={async () => {
              (await confirm({
                title: msg("Skip messages #{{v0}}–#{{v1}}?", {
                  v0: l.next_chunk.start_seq,
                  v1: l.next_chunk.end_seq,
                }),
                body: msg(
                  "They will not be added to the journal (no events, memories or proposals from them). The story text is not changed. The skip is recorded in the run list.",
                ),
                confirmLabel: msg("Skip"),
                danger: true,
              })) && mutation.mutate(`skip`);
            }}
          >
            {msg("Skip #")}
            {l.next_chunk.start_seq}–#{l.next_chunk.end_seq}
          </Button>
        )}
        <Button
          loading={mutation.isPending && mutation.variables === `reconcile`}
          onClick={() => mutation.mutate(`reconcile`)}
          disabled={!l.stale_records}
        >
          <Icon.Wrench className="size-4" /> {msg("Reconcile journal")}
        </Button>
        <span className="flex items-center gap-1.5">
          <Input
            value={o}
            onChange={(e) => s(e.target.value)}
            className="w-16"
            aria-label={msg("Rebuild from message number")}
          />
          <Button
            loading={mutation.isPending && mutation.variables === `rebuild`}
            onClick={async () => {
              (await confirm({
                title: msg("Re-extract from message #{{v0}}?", {
                  v0: o,
                }),
                body: msg(
                  "Analyses that range again. Existing records are kept; duplicates are skipped; new candidates go to the review queue. This makes a model call (possible API cost).",
                ),
              })) && mutation.mutate(`rebuild`);
            }}
          >
            <Icon.RefreshCw className="size-4" /> {msg("Rebuild from #")}
          </Button>
        </span>
      </div>
      <section>
        <SectionTitle>{msg("Extraction runs")}</SectionTitle>
        <div className="space-y-1">
          {n.data?.map((e) => (
            <div
              className="flex flex-wrap items-center gap-2 rounded border border-line px-2.5 py-1.5 text-xs"
              key={e.id}
            >
              <Badge tone={e.status === `succeeded` ? `ok` : e.status === `failed` ? `danger` : `warn`}>
                {e.status}
              </Badge>
              <span>
                #{e.start_seq}–#{e.end_seq}
              </span>
              <span className="text-faint">
                {e.capture_method.replace(/_/g, ` `)}
                {" · "}
                {e.model_id ?? msg("no model")}
                {" · "}
                {timeAgo(e.started_at)}
              </span>
              {e.status === `succeeded` && (
                <span className="text-muted">
                  {e.result_json.events ?? 0} {msg("events,")} {e.result_json.facts ?? 0} {msg("facts,")}{" "}
                  {e.result_json.proposals ?? 0} {msg("proposals")}
                </span>
              )}
              {e.error_summary && (
                <span className={e.status === `skipped` ? `text-warn` : `text-danger`}>{e.error_summary}</span>
              )}
              {e.status === `failed` && (
                <Button
                  size="sm"
                  className="ml-auto"
                  loading={mutation.isPending && mutation.variables === `retry:${e.id}`}
                  onClick={() => mutation.mutate(`retry:${e.id}`)}
                >
                  {msg("Retry")}
                </Button>
              )}
              {!!e.result_json.diagnostics?.length && (
                <details className="basis-full text-faint">
                  <summary className="cursor-pointer">
                    {e.result_json.diagnostics.length} {msg("request(s)")}
                  </summary>
                  <ul className="mt-1 space-y-0.5 pl-4">
                    {e.result_json.diagnostics.map((e) => (
                      <li key={e.attempt}>
                        #{e.attempt} {e.ok ? `ok` : e.category}
                        {" · "}
                        {e.messages ?? `?`} {msg("message(s) ·")} {e.seconds ?? `?`}
                        {" s"}
                        {e.reason ? ` — ${e.reason}` : ``}
                        {e.excerpt && <code className="ml-1 break-all text-[11px]">…{e.excerpt}…</code>}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          ))}
          {!n.data?.length && <p className="text-xs text-faint">{msg("No extraction runs yet.")}</p>}
        </div>
      </section>
    </div>
  );
}
