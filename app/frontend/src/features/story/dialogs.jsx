// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useInvalidateStory, useMessages, useStory, useWorlds, queryKeys } from "@/api/queries";
import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiPost, apiGet, apiPatch, errorMessage, apiPut, apiDelete } from "@/api/legacy";
import * as Icon from "lucide-react";
import { msg, msgKey } from "@/i18n";
import {
  Badge,
  Button,
  Callout,
  EmptyState,
  ErrorCallout,
  Field,
  Input,
  Modal,
  Select,
  Spinner,
  Textarea,
  Toggle,
  useUi,
} from "@/components/ui";
import { MONTHS, WEEKDAYS } from "@/features/story/chrono";
import { StoryMarkdown } from "@/features/story/prose";
import { loreSearchSchema, useStateEditor } from "@/features/lore/schemas";
import { timeAgo } from "@/lib/util";

export function RecapDialog({ storyId, action, onClose, onOpenJournal, onFocusStatus, onJump }) {
  if (!action) return null;
  let o = {
    storyId,
    input: action.input,
    onClose,
  };
  switch (action.name) {
    case `recap`:
      return <RecapRunner {...o} />;
    case `recon`:
    case `continuity`:
      return <ContinuityDialog {...o} focus={action.name} onJump={onJump} onFocusStatus={onFocusStatus} />;
    case `addlore`:
      return <AddLoreDialog {...o} />;
    case `content_prefs`:
      return <ContentPrefsDialog {...o} />;
    case `scene`:
      return <SceneDialog {...o} />;
    case `lore_search`:
      return <LoreSearchDialog {...o} />;
    case `memory`:
      return <MemoryDialog {...o} onJump={onJump} />;
    case `notes`:
      return <UserNotesDialog {...o} />;
    case `savepoints`:
      return <SavepointsDialog {...o} />;
    default:
      return null;
  }
}

function RecapRunner({ storyId, input, onClose }) {
  let invalidateStory = useInvalidateStory(),
    { toast } = useUi(),
    [a, o] = React.useState(``),
    mutation = useMutation({
      mutationFn: () =>
        apiPost(`/stories/${storyId}/recaps/generate`, {
          instructions: input,
        }),
      onSuccess: (e) => o(e.content),
    }),
    query = useQuery({
      queryKey: [`journal`, storyId, `recaps`],
      queryFn: () => apiGet(`/stories/${storyId}/recaps`).then((e) => e.recaps),
    });
  React.useEffect(() => {
    mutation.mutate();
  }, []);
  let l = async (t) => {
      mutation.data &&
        (await apiPatch(`/stories/${storyId}/recaps/${mutation.data.id}`, {
          content: a,
          status: t,
        }),
        invalidateStory(storyId),
        toast(
          t === `active`
            ? msg("Recap is now the rolling recap (the full transcript is unchanged).", {})
            : t === `rejected`
              ? msg("Recap discarded", {})
              : msg("Recap kept as a candidate", {}),
        ),
        onClose());
    },
    u = query.data?.find((e) => e.status === `active`);
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      size="lg"
      title="/recap — story so far"
      description={msg("A recap is a derived convenience: it never replaces the transcript or the journal.")}
      footer={
        mutation.data && (
          <>
            <Button variant="ghost" onClick={() => l(`rejected`)}>
              {msg("Discard")}
            </Button>
            <Button onClick={() => l(`candidate`)}>{msg("Keep as candidate")}</Button>
            <Button variant="primary" onClick={() => l(`active`)}>
              <Icon.Check className="size-4" /> {msg("Use as rolling recap")}
            </Button>
          </>
        )
      }
    >
      {u && (
        <p className="mb-2 text-xs text-faint">
          {msg("Current rolling recap: v")}
          {u.version}
          {msg(", covers up to message #")}
          {u.end_seq}.
        </p>
      )}
      {mutation.isPending && (
        <div className="flex items-center gap-2 text-sm text-muted">
          <Spinner /> {msg("Summarising with the extraction/narration model…")}
        </div>
      )}
      {mutation.isError && <ErrorCallout error={mutation.error} onRetry={() => mutation.mutate()} />}
      {mutation.data && (
        <Textarea
          value={a}
          onChange={(e) => o(e.target.value)}
          className="min-h-80 font-serif text-[14px]"
          aria-label={msg("Recap text")}
        />
      )}
    </Modal>
  );
}

function ContinuityDialog({ storyId, input, onClose, focus, onJump, onFocusStatus }) {
  let invalidateStory = useInvalidateStory(),
    { toast } = useUi(),
    c = useMessages(storyId),
    [l, u] = React.useState({}),
    [d, f] = React.useState(null),
    mutation = useMutation({
      mutationFn: () =>
        apiPost(`/stories/${storyId}/continuity`, {
          focus,
          input,
        }),
    });
  React.useEffect(() => {
    mutation.mutate();
  }, []);
  let g = (e, t) =>
    u((n) => ({
      ...n,
      [e]: t,
    }));
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      size="lg"
      title={focus === `recon` ? `/recon — continuity reconciliation` : `/continuity — consistency check`}
      description={msg("Nothing is changed unless you choose a fix. The story is never retconned silently.")}
    >
      {mutation.isPending && (
        <div className="flex items-center gap-2 text-sm text-muted">
          <Spinner /> {msg("Comparing the recent transcript with avatar, notes, memories, state and lore…")}
        </div>
      )}
      {mutation.isError && <ErrorCallout error={mutation.error} onRetry={() => mutation.mutate()} />}
      {mutation.data && (
        <div className="space-y-3">
          {mutation.data.summary && <StoryMarkdown text={mutation.data.summary} className="prose-ui text-muted" />}
          {mutation.data.issues.length === 0 && (
            <Callout tone="ok">{msg("No contradictions found in the checked range.")}</Callout>
          )}
          {mutation.data.issues.map((t, n) => (
            <div className="rounded-md border border-line p-3 text-sm" key={n}>
              <p>{t.description}</p>
              {t.records?.length ? (
                <p className="mt-1 text-xs text-faint">
                  {msg("Records:")} {t.records.join(`; `)}
                </p>
              ) : null}
              {t.suggested_fix && (
                <p className="mt-1 text-xs text-muted">
                  {msg("Suggested fix:")} {t.suggested_fix}
                </p>
              )}
              {l[n] ? (
                <Badge tone="ok" className="mt-2">
                  {l[n]}
                </Badge>
              ) : (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {t.message_ids?.map((e) => (
                    <Button size="sm" onClick={() => onJump(e)} key={e}>
                      {msg("Go to message")}
                    </Button>
                  ))}
                  {t.message_ids?.[0] && (
                    <Button
                      size="sm"
                      onClick={() => {
                        let e = c.data?.messages.find((e) => e.id === t.message_ids[0]);
                        f({
                          i: n,
                          id: t.message_ids[0],
                          text: e?.content ?? ``,
                        });
                      }}
                    >
                      {msg("Apply correction to message")}
                    </Button>
                  )}
                  <Button
                    size="sm"
                    onClick={async () => {
                      (await apiPost(`/stories/${storyId}/facts`, {
                        content: t.fix_text || t.suggested_fix || t.description,
                        category: `memory`,
                        fact_kind: `established`,
                        source_message_ids: t.message_ids ?? [],
                      }),
                        invalidateStory(storyId),
                        g(n, msg("Memory created", {})));
                    }}
                  >
                    {msg("Create memory")}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => {
                      (onFocusStatus(), g(n, msg("Opened state panel", {})));
                    }}
                  >
                    {msg("Update state")}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => g(n, msg("Ignored", {}))}>
                    {msg("Ignore")}
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {d && (
        <Modal
          open
          onOpenChange={(e) => !e && f(null)}
          title={msg("Correct the message")}
          description={msg(
            "The previous text is kept in the message's edit history; dependent journal records are flagged for review.",
          )}
          size="lg"
          footer={
            <Button
              variant="primary"
              onClick={async () => {
                try {
                  (await apiPatch(`/stories/${storyId}/messages/${d.id}`, {
                    content: d.text,
                  }),
                    invalidateStory(storyId),
                    g(d.i, msg("Message corrected", {})),
                    f(null));
                } catch (e) {
                  toast(errorMessage(e), `danger`);
                }
              }}
            >
              {msg("Save correction")}
            </Button>
          }
        >
          {mutation.data?.issues[d.i]?.suggested_fix && (
            <Callout className="mb-2">{mutation.data.issues[d.i].suggested_fix}</Callout>
          )}
          <Textarea
            value={d.text}
            onChange={(e) =>
              f({
                ...d,
                text: e.target.value,
              })
            }
            className="min-h-72 font-serif"
          />
        </Modal>
      )}
    </Modal>
  );
}

function AddLoreDialog({ storyId, input, onClose }) {
  let story = useStory(storyId),
    worlds = useWorlds(),
    a = useMessages(storyId),
    { toast } = useUi(),
    queryClient = useQueryClient(),
    [c, l] = React.useState({
      title: input
        .split(
          `
`,
        )[0]
        .slice(0, 80),
      content: input,
      tags: ``,
      entities: [],
      scope: `story`,
      source: ``,
      confidence: 1,
    }),
    u = worlds.data?.find((e) => e.id === story.data?.world_id)?.data_json.characters ?? [],
    d = async (t) => {
      try {
        (await apiPost(`/local-canon`, {
          title: c.title || msg("Untitled fact", {}),
          content: c.content,
          world_id: story.data?.world_id,
          story_id: storyId,
          scope: c.scope,
          tags: c.tags
            .split(`,`)
            .map((e) => e.trim())
            .filter(Boolean),
          entity_ids: c.entities,
          source_message_id: c.source || null,
          confidence: c.confidence,
          approve: t,
        }),
          queryClient.invalidateQueries({
            queryKey: queryKeys.context(storyId),
          }),
          toast(t ? msg("Added to local canon", {}) : msg("Saved as a pending local-canon candidate", {})),
          onClose());
      } catch (e) {
        toast(errorMessage(e), `danger`);
      }
    };
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      title="/addlore — new local canon"
      description={msg(
        "Local canon is campaign-specific and kept separate from the imported baseline lore, which is never edited.",
      )}
      footer={
        <>
          <Button onClick={() => d(false)}>{msg("Save as candidate")}</Button>
          <Button variant="primary" onClick={() => d(true)} disabled={!c.content.trim()}>
            {msg("Approve & add")}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label={msg("Title")}>
          <Input
            value={c.title}
            onChange={(e) =>
              l({
                ...c,
                title: e.target.value,
              })
            }
          />
        </Field>
        <Field label={msg("Fact")}>
          <Textarea
            value={c.content}
            onChange={(e) =>
              l({
                ...c,
                content: e.target.value,
              })
            }
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={msg("Scope")}>
            <Select
              value={c.scope}
              onChange={(e) =>
                l({
                  ...c,
                  scope: e.target.value,
                })
              }
            >
              <option value="story">{msg("This story only")}</option>
              <option value="local">{msg("Local canon (all my stories in this world)")}</option>
              <option value="global_draft">{msg("Global lore draft")}</option>
            </Select>
          </Field>
          <Field label={msg("Confidence")}>
            <Select
              value={String(c.confidence)}
              onChange={(e) =>
                l({
                  ...c,
                  confidence: Number(e.target.value),
                })
              }
            >
              <option value="1">{msg("Certain")}</option>
              <option value="0.7">{msg("Likely")}</option>
              <option value="0.4">{msg("Uncertain")}</option>
            </Select>
          </Field>
        </div>
        <Field label={msg("Tags (comma separated)")}>
          <Input
            value={c.tags}
            onChange={(e) =>
              l({
                ...c,
                tags: e.target.value,
              })
            }
          />
        </Field>
        {u.length > 0 && (
          <Field label={msg("Characters involved")}>
            <div className="flex max-h-28 flex-wrap gap-1 overflow-y-auto">
              {u.map((e) => (
                <button
                  type="button"
                  onClick={() =>
                    l({
                      ...c,
                      entities: c.entities.includes(e.id)
                        ? c.entities.filter((t) => t !== e.id)
                        : [...c.entities, e.id],
                    })
                  }
                  className={
                    c.entities.includes(e.id)
                      ? `rounded bg-accent px-1.5 py-0.5 text-[11px] text-accent-fg`
                      : `rounded bg-panel-2 px-1.5 py-0.5 text-[11px] text-muted`
                  }
                  key={e.id}
                >
                  {e.name}
                </button>
              ))}
            </div>
          </Field>
        )}
        <Field label={msg("Source message (optional)")}>
          <Select
            value={c.source}
            onChange={(e) =>
              l({
                ...c,
                source: e.target.value,
              })
            }
          >
            <option value="">{msg("None")}</option>
            {a.data?.messages
              .slice(-12)
              .reverse()
              .map((e) => (
                <option value={e.id} key={e.id}>
                  #{e.seq} {e.role}
                  {": "}
                  {e.content.slice(0, 60)}
                </option>
              ))}
          </Select>
        </Field>
      </div>
    </Modal>
  );
}

function ContentPrefsDialog({ storyId, onClose }) {
  let story = useStory(storyId),
    invalidateStory = useInvalidateStory(),
    { toast, confirm } = useUi(),
    o = story.data?.settings_json.content_prefs ?? {},
    [s, c] = React.useState({
      romance_intensity: `subtle`,
      profanity: `mild`,
      violence: `moderate`,
      fade_to_black: true,
      adult_profile_enabled: false,
      notes: ``,
      ...o,
    }),
    l = async () => {
      (await apiPatch(`/stories/${storyId}`, {
        settings: {
          content_prefs: s,
        },
      }),
        invalidateStory(storyId),
        toast(msg("Content preferences saved for this story")),
        onClose());
    },
    u = (e, t, n) => (
      <Field label={n}>
        <Select
          value={String(s[e])}
          onChange={(t) =>
            c({
              ...s,
              [e]: t.target.value,
            })
          }
        >
          {t.map((e) => (
            <option key={e} value={e}>
              {msg(e)}
            </option>
          ))}
        </Select>
      </Field>
    );

  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      title={msg("Content preferences")}
      description={msg(
        "Describes tone and intensity for this story. It does not and cannot disable a provider's safety policies.",
      )}
      footer={
        <Button variant="primary" onClick={l}>
          {msg("Save")}
        </Button>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        {u(`romance_intensity`, [`none`, `subtle`, `moderate`, `mature`], msg("Romance intensity", {}))}
        {u(`profanity`, [`none`, `mild`, `strong`], msg("Profanity", {}))}
        {u(`violence`, [`low`, `moderate`, `graphic`], msg("Violence / gore", {}))}
        <div className="flex items-end pb-1">
          <Toggle
            checked={!!s.fade_to_black}
            onChange={(e) =>
              c({
                ...s,
                fade_to_black: e,
              })
            }
            label={msg("Fade to black for intimate scenes")}
          />
        </div>
      </div>
      <div className="mt-4 rounded-md border border-line p-3">
        <Toggle
          checked={!!s.adult_profile_enabled}
          onChange={async (e) => {
            (!e ||
              (await confirm({
                title: msg("Enable the adult-content profile?"),
                body: msg(
                  "Only for scenes between clearly adult characters. Content involving minors or characters of unclear age is always prohibited, and the provider's own policies still apply.",
                ),
                confirmLabel: msg("Enable"),
              }))) &&
              c({
                ...s,
                adult_profile_enabled: e,
              });
          }}
          label={msg("Adult-content profile")}
          description={msg(
            "Off by default. Allows more mature romance between clearly adult characters, within provider policy.",
          )}
        />
      </div>
      <Field label={msg("Additional notes")} className="mt-3">
        <Textarea
          value={String(s.notes ?? ``)}
          onChange={(e) =>
            c({
              ...s,
              notes: e.target.value,
            })
          }
          placeholder={msg("e.g. avoid body horror; keep battles tense but not gory")}
        />
      </Field>
      <Callout tone="info" className="mt-3">
        {msg("Sexual content involving minors is never allowed, regardless of these settings.")}
      </Callout>
    </Modal>
  );
}

function SceneDialog({ storyId, onClose }) {
  let stateEditor = useStateEditor(storyId),
    [r, i] = React.useState(null),
    a = stateEditor.q.data?.date_suggestion;
  if (
    (React.useEffect(() => {
      stateEditor.state && !r && i(structuredClone(stateEditor.state.scene));
    }, [stateEditor.state, r]),
    !r)
  )
    return null;
  let o = (e, t, n) => (
    <Field label={t}>
      <Input
        value={String(r[e] ?? ``)}
        placeholder={n}
        onChange={(t) =>
          i({
            ...r,
            [e]: t.target.value,
          })
        }
      />
    </Field>
  );

  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      title="/scene — scene details"
      description={msg(
        "The current scene: shown in the header of the latest reply and sent to the model. Earlier replies keep their own headers.",
      )}
      footer={
        <Button
          variant="primary"
          onClick={() => {
            (stateEditor.save(
              (e) =>
                void (e.scene = {
                  ...e.scene,
                  ...r,
                  present: e.scene.present,
                }),
              msg("Scene edited", {}),
            ),
              onClose());
          }}
        >
          {msg("Save scene")}
        </Button>
      }
    >
      {a && !r.month && !r.day && !r.date && (
        <Callout tone="info" className="mb-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span>
              {msg("Suggested start date:")} <strong>{a.label}</strong>
              {" — "}
              {a.reason}{" "}
              <span className="text-faint">
                {msg("Source:")} {a.provenance ?? msg("world calendar")}
                {msg(". No year or weekday is set.")}
              </span>
            </span>
            <Button
              size="sm"
              onClick={() =>
                i({
                  ...r,
                  month: a.month,
                  day: a.day,
                })
              }
            >
              {msg("Use")} {a.label}
            </Button>
          </div>
        </Callout>
      )}
      <div className="grid grid-cols-2 gap-3">
        {o(`location`, msg("Location", {}))}
        {o(`chapter`, msg("Chapter / arc", {}))}
        {o(`time`, msg("Time of day", {}))}
        {o(`weather`, msg("Weather", {}))}
        <Field label={msg("Story day (D…)")} hint={msg("D1 is the first in-story day")}>
          <Input
            type="number"
            min={1}
            value={r.story_day ?? 1}
            onChange={(e) =>
              i({
                ...r,
                story_day: e.target.value ? Math.max(1, Number(e.target.value)) : null,
              })
            }
          />
        </Field>
        <Field label={msg("Weekday")}>
          <Select
            value={r.weekday ?? ``}
            onChange={(e) =>
              i({
                ...r,
                weekday: e.target.value,
              })
            }
          >
            <option value="">{msg("not established")}</option>
            {WEEKDAYS.map((e) => (
              <option key={e} value={e}>
                {msg(e)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={msg("Day of month")}>
          <Input
            type="number"
            min={1}
            max={31}
            value={r.day ?? ``}
            onChange={(e) =>
              i({
                ...r,
                day: e.target.value ? Math.min(31, Math.max(1, Number(e.target.value))) : null,
              })
            }
          />
        </Field>
        <Field label={msg("Month")}>
          <Select
            value={r.month ?? ``}
            onChange={(e) =>
              i({
                ...r,
                month: e.target.value,
              })
            }
          >
            <option value="">{msg("not established")}</option>
            {MONTHS.map((e) => (
              <option key={e} value={e}>
                {msg(e)}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label={stateEditor.q.data?.calendar?.year_label ?? msg("Year", {})}
          hint={msg("Only if the story has established it")}
        >
          <Input
            type="number"
            min={1}
            value={r.year ?? ``}
            onChange={(e) =>
              i({
                ...r,
                year: e.target.value ? Number(e.target.value) : null,
              })
            }
          />
        </Field>
        {o(`date`, msg("Other date text", {}), msg("used only when no calendar date is set"))}
        {o(`mood`, msg("Mood", {}))}
        {o(`status`, msg("Scene status", {}), msg("e.g. tense negotiation", {}))}
      </div>
      <p className="mt-3 text-xs text-faint">
        {msg(
          "In-story time only — never the real date. D1 is the first day of the story (D5 = four days later). Scene analysis updates these when a reply establishes a change (with a quote); your edits here always win. Manage who is present from the Cast tab.",
        )}
      </p>
    </Modal>
  );
}

function LoreSearchDialog({ storyId, input, onClose }) {
  let story = useStory(storyId),
    queryClient = useQueryClient(),
    { toast } = useUi(),
    [o, s] = React.useState(input),
    [c, l] = React.useState(input),
    u = story.data?.world_id,
    query = useQuery({
      queryKey: [`lore-search`, u, c],
      enabled: !!u && !!c.trim(),
      queryFn: () => apiGet(`/worlds/${u}/search?q=${encodeURIComponent(c)}`, loreSearchSchema),
    }),
    f = story.data?.settings_json.pinned_lore_ids ?? [];
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      size="lg"
      title="/lore — search the lore library"
      description={msg("Results show source confidence. Pin an entry to always include it in this story's context.")}
    >
      {u ? (
        <>
          <form
            onSubmit={(e) => {
              (e.preventDefault(), l(o));
            }}
            className="mb-3 flex gap-2"
          >
            <Input
              autoFocus
              value={o}
              onChange={(e) => s(e.target.value)}
              placeholder={msg("Search characters, places, systems…")}
            />

            <Button type="submit">
              <Icon.Search className="size-4" />
            </Button>
          </form>
          {query.isLoading && <Spinner />}
          {query.data && query.data.results.length === 0 && query.data.local_canon.length === 0 && (
            <EmptyState title={msg("No matches")} />
          )}
          <div className="space-y-2">
            {query.data?.local_canon.map((e) => (
              <div className="rounded-md border border-line p-2.5 text-sm" key={e.id}>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{e.title}</span>
                  <Badge tone="info">
                    {msg("local canon ·")} {e.status}
                  </Badge>
                </div>
                <p className="mt-1 text-xs text-muted">{e.content}</p>
              </div>
            ))}
            {query.data?.results.map((t) => (
              <div className="rounded-md border border-line p-2.5 text-sm" key={t.chunk_id}>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-medium">{t.title}</span>
                  <Badge>{msgKey(t.category)}</Badge>
                  {t.confidence && (
                    <Badge tone={t.confidence === `high` ? `ok` : `warn`}>
                      {msg("{{v0}} confidence", { v0: msgKey(t.confidence) })}
                    </Badge>
                  )}
                  {t.canon_status && (
                    <Badge tone={t.canon_status === `recurring_reference` ? `neutral` : `warn`}>
                      {msgKey(t.canon_status)}
                    </Badge>
                  )}
                  <Button
                    size="sm"
                    variant="ghost"
                    className="ml-auto"
                    onClick={async () => {
                      (await apiPost(`/stories/${storyId}/context/pinned-lore`, {
                        chunk_id: t.chunk_id,
                        pinned: !f.includes(t.chunk_id),
                      }),
                        queryClient.invalidateQueries({
                          queryKey: queryKeys.story(storyId),
                        }),
                        queryClient.invalidateQueries({
                          queryKey: queryKeys.context(storyId),
                        }),
                        toast(
                          f.includes(t.chunk_id)
                            ? msg("Unpinned from context", {})
                            : msg("Pinned to this story's context", {}),
                        ));
                    }}
                  >
                    <Icon.Pin className="size-3.5" /> {f.includes(t.chunk_id) ? msg("Unpin") : msg("Pin to context")}
                  </Button>
                </div>
                <p className="mt-1 text-xs text-muted">{t.snippet}</p>
              </div>
            ))}
          </div>
        </>
      ) : (
        <EmptyState title={msg("This story has no world attached")}>
          {msg("Import a lore pack and pick it when creating a story.")}
        </EmptyState>
      )}
    </Modal>
  );
}

function MemoryDialog({ storyId, input, onClose, onJump }) {
  let invalidateStory = useInvalidateStory(),
    { toast } = useUi(),
    [o, s] = React.useState(input),
    [c, l] = React.useState(input),
    [u, d] = React.useState(`established`),
    query = useQuery({
      queryKey: [`journal`, storyId, `facts-search`, o],
      queryFn: () => apiGet(`/stories/${storyId}/facts?q=${encodeURIComponent(o)}`).then((e) => e.facts),
    });
  return (
    <Modal open onOpenChange={(e) => !e && onClose()} size="lg" title="/memory — durable memories & facts">
      <div className="mb-4 space-y-2 rounded-md border border-line p-3">
        <p className="text-xs font-medium text-muted">{msg("New memory")}</p>
        <Textarea
          value={c}
          onChange={(e) => l(e.target.value)}
          className="min-h-16"
          placeholder={msg("Something the story should remember")}
        />

        <div className="flex gap-2">
          <Select value={u} onChange={(e) => d(e.target.value)} className="w-48">
            <option value="established">{msg("Established fact")}</option>
            <option value="rumour">{msg("Rumour")}</option>
            <option value="belief">{msg("Character belief")}</option>
            <option value="secret">{msg("Secret")}</option>
            <option value="plan">{msg("Plan")}</option>
          </Select>
          <Button
            variant="primary"
            onClick={async () => {
              try {
                (await apiPost(`/stories/${storyId}/facts`, {
                  content: c,
                  category: `memory`,
                  fact_kind: u,
                  importance: 3,
                }),
                  invalidateStory(storyId),
                  l(``),
                  toast(msg("Memory saved")));
              } catch (e) {
                toast(errorMessage(e), `danger`);
              }
            }}
            disabled={!c.trim()}
          >
            <Icon.Save className="size-4" /> {msg("Save memory")}
          </Button>
        </div>
      </div>
      <Input value={o} onChange={(e) => s(e.target.value)} placeholder={msg("Search memories")} className="mb-2" />
      <MemoryList facts={query.data ?? []} storyId={storyId} onJump={onJump} />
    </Modal>
  );
}

export function MemoryList({ facts, storyId, onJump }) {
  let invalidateStory = useInvalidateStory();
  return facts.length ? (
    <div className="space-y-1.5">
      {facts.map((e) => (
        <div className="flex items-start gap-2 rounded-md border border-line p-2 text-sm" key={e.id}>
          <div className="min-w-0 flex-1">
            <p className={e.status === `rejected` || e.status === `superseded` ? `text-faint line-through` : ``}>
              {e.content}
            </p>
            <div className="mt-1 flex flex-wrap gap-1">
              <Badge>{e.fact_kind}</Badge>
              <Badge tone={e.status === `active` ? `ok` : e.status === `candidate` ? `warn` : `neutral`}>
                {e.status}
              </Badge>
              {e.pinned && <Badge tone="accent">{msg("pinned")}</Badge>}
              {e.stale && <Badge tone="warn">{msg("stale")}</Badge>}
              {e.subject_label && <Badge>{e.subject_label}</Badge>}
              {onJump &&
                e.source_message_ids_json.map((e) => (
                  <button className="text-[11px] text-accent hover:underline" onClick={() => onJump(e)} key={e}>
                    {msg("source")}
                  </button>
                ))}
            </div>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={async () => {
              (await apiPatch(`/stories/${storyId}/facts/${e.id}`, {
                pinned: !e.pinned,
              }),
                invalidateStory(storyId));
            }}
          >
            <Icon.Pin className="size-3.5" />
          </Button>
        </div>
      ))}
    </div>
  ) : (
    <p className="py-3 text-xs text-faint">{msg("No memories match.")}</p>
  );
}

function UserNotesDialog({ storyId, onClose }) {
  let query = useQuery({
      queryKey: queryKeys.notes(storyId),
      queryFn: () => apiGet(`/notes?story_id=${storyId}`),
    }),
    invalidateStory = useInvalidateStory(),
    queryClient = useQueryClient(),
    { toast } = useUi(),
    [o, s] = React.useState(null),
    [c, l] = React.useState(null),
    [u, d] = React.useState(false);
  React.useEffect(() => {
    query.data && !o && (s(query.data.global), l(query.data.story), d(query.data.global_disabled_for_story));
  }, [query.data, o]);
  let f = async () => {
    o &&
      c &&
      (await apiPut(`/notes/${o.id}`, {
        content: o.content,
        enabled: o.enabled,
      }),
      await apiPut(`/notes/${c.id}`, {
        content: c.content,
        enabled: c.enabled,
      }),
      await apiPatch(`/stories/${storyId}`, {
        settings: {
          disable_global_note: u || null,
        },
      }),
      queryClient.invalidateQueries({
        queryKey: queryKeys.notes(storyId),
      }),
      invalidateStory(storyId),
      toast(msg("Notes saved")),
      onClose());
  };
  if (!o || !c) return null;
  let p = o.enabled && !u && o.content.trim();
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      size="lg"
      title={msg("User notes")}
      description={msg("Precedence: your current message > story note > global note > imported lore.")}
      footer={
        <Button variant="primary" onClick={f}>
          {msg("Save notes")}
        </Button>
      }
    >
      <div className="space-y-4">
        <div>
          <div className="mb-1 flex items-center justify-between">
            <span className="text-sm font-medium">
              {msg("Story note")}{" "}
              {c.enabled && c.content.trim() ? (
                <Badge tone="ok">{msg("active")}</Badge>
              ) : (
                <Badge>{msg("inactive")}</Badge>
              )}
            </span>
            <Toggle
              checked={c.enabled}
              onChange={(e) =>
                l({
                  ...c,
                  enabled: e,
                })
              }
              label={msg("Enabled")}
            />
          </div>
          <Textarea
            value={c.content}
            onChange={(e) =>
              l({
                ...c,
                content: e.target.value,
              })
            }
            className="min-h-32"
            placeholder={msg("Instructions and persistent facts for this story only.")}
          />

          <p className="mt-0.5 text-right text-[11px] text-faint">
            ≈{Math.ceil(c.content.length / 4)} {msg("tokens")}
          </p>
        </div>
        <div>
          <div className="mb-1 flex items-center justify-between">
            <span className="text-sm font-medium">
              {msg("Global note")}{" "}
              {p ? <Badge tone="ok">{msg("active")}</Badge> : <Badge>{msg("inactive here")}</Badge>}
            </span>
            <Toggle
              checked={o.enabled}
              onChange={(e) =>
                s({
                  ...o,
                  enabled: e,
                })
              }
              label={msg("Enabled everywhere")}
            />
          </div>
          <Textarea
            value={o.content}
            onChange={(e) =>
              s({
                ...o,
                content: e.target.value,
              })
            }
            className="min-h-28"
            placeholder={msg("Applies to all stories (e.g. writing preferences).")}
          />

          <div className="mt-2">
            <Toggle checked={u} onChange={d} label={msg("Disable the global note for this story")} />
          </div>
        </div>
      </div>
    </Modal>
  );
}

function SavepointsDialog({ storyId, input, onClose }) {
  let query = useQuery({
      queryKey: [`journal`, storyId, `savepoints`],
      queryFn: () => apiGet(`/stories/${storyId}/savepoints`).then((e) => e.savepoints),
    }),
    invalidateStory = useInvalidateStory(),
    { toast, confirm } = useUi(),
    [s, c] = React.useState(input),
    mutation = useMutation({
      mutationFn: () =>
        apiPost(`/stories/${storyId}/savepoints`, {
          label: s,
        }),
      onSuccess: () => {
        (invalidateStory(storyId), c(``), toast(msg("Savepoint created")));
      },
    }),
    u = async (t, r) => {
      if (
        r !== `replace` ||
        (await confirm({
          title: msg("Replace the current branch?"),
          body: msg(
            "The current branch is archived (not deleted) and an automatic recovery savepoint is made first. The savepoint is restored as the new active branch.",
          ),
          confirmLabel: msg("Restore and replace"),
          danger: true,
        }))
      )
        try {
          (await apiPost(`/stories/${storyId}/savepoints/${t.id}/restore`, {
            mode: r,
            confirm: true,
          }),
            invalidateStory(storyId),
            toast(
              msg("Restored “{{v0}}” as a new branch", {
                v0: t.label,
              }),
            ),
            onClose());
        } catch (e) {
          toast(errorMessage(e), `danger`);
        }
    };
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      size="lg"
      title={msg("Savepoints")}
      description={msg("A savepoint captures this branch's transcript, state, journal, memories and recaps together.")}
    >
      <form
        className="mb-4 flex gap-2"
        onSubmit={(e) => {
          (e.preventDefault(), mutation.mutate());
        }}
      >
        <Input
          value={s}
          onChange={(e) => c(e.target.value)}
          placeholder={msg("Savepoint name (e.g. Before the duel)")}
        />

        <Button variant="primary" type="submit" loading={mutation.isPending}>
          {msg("Create")}
        </Button>
      </form>
      {query.data?.length === 0 && <EmptyState title={msg("No savepoints yet")} />}
      <div className="space-y-1.5">
        {query.data?.map((t) => (
          <div className="flex items-center gap-2 rounded-md border border-line px-3 py-2 text-sm" key={t.id}>
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{t.label}</p>
              <p className="text-xs text-faint">
                {timeAgo(t.created_at)}
                {" · "}
                {t.messages} {msg("messages ·")} {t.events} {msg("events ·")} {t.facts} {msg("facts")}{" "}
                {t.kind === `auto` && (
                  <Badge className="ml-1">
                    {msg("automatic ·")} {t.reason}
                  </Badge>
                )}
              </p>
            </div>
            <Button size="sm" onClick={() => u(t, `new_branch`)}>
              <Icon.RotateCcw className="size-3.5" /> {msg("Restore as branch")}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => u(t, `replace`)}>
              {msg("Replace current")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={async () => {
                (await confirm({
                  title: msg("Delete savepoint?"),
                  body: t.label,
                  danger: true,
                  confirmLabel: msg("Delete"),
                })) &&
                  (await apiDelete(`/stories/${storyId}/savepoints/${t.id}?confirm=true`), invalidateStory(storyId));
              }}
            >
              {msg("Delete")}
            </Button>
          </div>
        ))}
      </div>
    </Modal>
  );
}
