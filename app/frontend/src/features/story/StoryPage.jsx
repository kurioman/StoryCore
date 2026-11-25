// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import * as React from "react";
import {
  useInvalidateStory,
  streamEventSchema,
  useStory,
  useMessages,
  useSettings,
  useProviders,
  useContextPreview,
  useCast,
  useStoryState,
  useReviewCount,
} from "@/api/queries";
import { apiStream, ApiError, apiGet, apiPost, errorMessage } from "@/api/legacy";
import { useMutation, useQuery } from "@tanstack/react-query";
import * as Icon from "lucide-react";
import { msg } from "@/i18n";
import { Button, Callout, EmptyState, ErrorCallout, IconButton, Modal, Spinner, useUi } from "@/components/ui";
import { Composer, ContextInspector } from "@/features/story/composer";
import { JournalView } from "@/features/story/journal";
import { MessageItem, SpeakersPanel, TurnAnalysisBar } from "@/features/story/transcript";
import { RecapDialog, ResumeOffer } from "@/features/story/dialogs";
import { StatusSection } from "@/features/story/panels/StatusPanel";
import { StoryPanelActions } from "@/features/report/ReportProblem";
import { MusicPlayer } from "@/features/music/MusicPlayer";
import { StoryHeader } from "@/features/story/header";
import { cn, isCloudModelId } from "@/lib/util";
import { useLocalState, useMediaQuery } from "@/lib/hooks";
import { usePhoneLayout } from "@/lib/layout";
import { useScene } from "@/features/story/api";
import { usePreloadPortraits } from "@/lib/portraits";

function runCommand(e, t, n) {
  let [r, i] = React.useState(null),
    // v0.6: portraits found while a reply is written, per message (kept until the saved ones arrive)
    [livePortraits, setLivePortraits] = React.useState({}),
    [a, o] = React.useState(null),
    s = React.useRef(null),
    c = React.useRef(null),
    l = React.useRef(new Set()),
    invalidateStory = useInvalidateStory(),
    d = React.useRef({
      invalidate: invalidateStory,
      onError: n,
    });
  d.current = {
    invalidate: invalidateStory,
    onError: n,
  };
  let f = React.useRef(true);
  React.useEffect(
    () => (
      (f.current = true),
      () => {
        f.current = false;
      }
    ),

    [],
  );
  let p = React.useCallback(
    async (t) => {
      if (!f.current || c.current === t) return;
      ((c.current = t), l.current.delete(t), s.current?.abort());
      let n = new AbortController();
      ((s.current = n),
        i({
          messageId: t,
          text: ``,
          status: `streaming`,
        }),
        d.current.invalidate(e));
      let r = `streaming`;
      try {
        await apiStream(
          `/generations/${t}/stream`,
          (e) => {
            let n = streamEventSchema.safeParse(e);
            if (!n.success) return;
            let a = n.data;
            a.type === `snapshot`
              ? i({
                  messageId: t,
                  text: a.text,
                  status: a.status,
                })
              : a.type === `portraits`
                ? setLivePortraits((p) => ({ ...p, [t]: a.beats }))
              : a.type === `delta`
                ? i((e) =>
                    e && e.messageId === t
                      ? {
                          ...e,
                          text: e.text + a.text,
                        }
                      : e,
                  )
                : a.type === `done` &&
                  ((r = a.status),
                  i((e) => ({
                    messageId: t,
                    text: e?.text ?? ``,
                    status: a.status,
                    error: a.error,
                  })));
          },
          n.signal,
        );
      } catch (e) {
        n.signal.aborted || d.current.onError(e);
      } finally {
        (c.current === t && (c.current = null),
          n.signal.aborted ||
            (l.current.add(t),
            r === `streaming` && setTimeout(() => l.current.delete(t), 4e3),
            d.current.invalidate(e),
            setTimeout(() => i((e) => (e?.messageId === t ? null : e)), 400),
            setTimeout(() => d.current.invalidate(e), 2500)));
      }
    },
    [e],
  );
  (React.useEffect(() => {
    let e = t?.find((e) => e.status === `streaming`);
    e && c.current !== e.id && !l.current.has(e.id) && p(e.id);
  }, [t, p]),
    React.useEffect(() => () => s.current?.abort(), []));
  let h = React.useCallback(
      async (t) => {
        try {
          let n = await t();
          return (
            d.current.invalidate(e),
            (n.story_id && n.story_id !== e) || (n.assistant_message_id && p(n.assistant_message_id)),
            n
          );
        } catch (e) {
          if (e instanceof ApiError && e.code === `cloud_consent_required`)
            return (
              o({
                providerId: String(e.data.provider_id),
                providerName: String(e.data.provider_name),
                notice: String(e.data.notice),
                retry: () => h(t),
              }),
              null
            );

          throw (d.current.onError(e), e);
        }
      },
      [p, e],
    ),
    g = React.useCallback(async () => {
      r?.messageId && (await apiPost(`/generations/${r.messageId}/cancel`));
    }, [r?.messageId]),
    _ = React.useCallback(async () => {
      if (!a) return;
      await apiPost(`/providers/${a.providerId}/consent`);
      let e = a.retry;
      (o(null), await e());
    }, [a]);
  return {
    live: r,
    livePortraits,
    generating: r?.status === `streaming`,
    run: h,
    stop: g,
    consent: a,
    setConsent: o,
    acceptConsent: _,
  };
}

export function StoryPage({ storyId }) {
  let story = useStory(storyId),
    n = useMessages(storyId),
    settings = useSettings(),
    i = useProviders(),
    contextPreview = useContextPreview(storyId),
    cast = useCast(storyId),
    storyState = useStoryState(storyId),
    reviewCount = useReviewCount(storyId),
    scene = useScene(storyId),
    [u, d] = React.useState(null),
    invalidateStory = useInvalidateStory(),
    { toast, confirm } = useUi(),
    mediaQuery = useMediaQuery(`(min-width: 1280px)`),
    phone = usePhoneLayout(),
    [v, y] = useLocalState(`right-panel`, true),
    [b, x] = React.useState(false),
    S = mediaQuery ? v : b,
    C = mediaQuery ? y : x,
    [w, T] = React.useState(`status`),
    [E, D] = React.useState(`story`),
    [O, ee] = React.useState(null),
    [te, ne] = React.useState(null),
    [re, ie] = React.useState(false),
    [ae, oe] = React.useState(null),
    [se, ce] = React.useState(false),
    le = React.useRef(null),
    ue = React.useCallback(
      (e) => {
        e instanceof ApiError && e.code === `no_model` ? toast(e.message, `danger`) : toast(errorMessage(e), `danger`);
      },
      [toast],
    ),
    de = runCommand(storyId, n.data?.messages, ue);
  useAnalysisWatcher(storyId, scene.data?.message_id ?? null, scene.data?.status ?? `none`, invalidateStory);
  // v0.6: the six expressions of everyone in the scene are loaded ahead (instant change of expression)
  usePreloadPortraits(story.data?.world_id, [
    ...(storyState.data?.state?.scene?.present ?? []),
    ...(scene.data?.cast?.present ?? []),
    ...(scene.data?.speakers ?? []).map((e) => e.character_id),
    ...Object.values(de.livePortraits)
      .flat()
      .map((e) => e.character_id),
  ]);
  let fe = (e) => {
      (ee(
        e
          ? {
              character: e,
            }
          : null,
      ),
        D(`journal`));
    },
    pe = React.useCallback(
      (e) => {
        (D(`story`),
          setTimeout(() => {
            let t = document.getElementById(`msg-${e}`);
            t && window.dispatchEvent(new Event(`story-jump`)); // the view stays on that message (AutoScroll)
            t
              ? (t.scrollIntoView({
                  behavior: `smooth`,
                  block: `center`,
                }),
                oe(e),
                setTimeout(() => oe(null), 2500))
              : toast(msg("That message is not on the active branch (or was deleted)."), `warn`);
          }, 60));
      },
      [toast],
    ),
    me = async (t, n) => {
      switch (t) {
        case `state`:
          return (C(true), T(`status`), true);
        case `journal`:
          return (
            n.trim() &&
              (await apiPost(`/stories/${storyId}/events`, {
                title: n
                  .trim()
                  .split(
                    `
`,
                  )[0]
                  .slice(0, 120),
                summary: n.trim(),
                verification_status: `confirmed`,
              }),
              invalidateStory(storyId),
              toast(msg("Manual event added to the journal"))),
            fe(),
            true
          );

        case `savepoint`:
          return (
            n.trim()
              ? (await apiPost(`/stories/${storyId}/savepoints`, {
                  label: n.trim(),
                }),
                toast(
                  msg("Savepoint “{{v0}}” created", {
                    v0: n.trim(),
                  }),
                ))
              : ne({
                  name: `savepoints`,
                  input: ``,
                }),
            true
          );

        case `undo`: {
          let t = storyState.data?.last_change;
          if (!storyState.data?.can_undo) return (toast(msg("Nothing to undo in the story state."), `warn`), true);
          if (
            await confirm({
              title: msg("Undo the last state change?"),
              body: (
                <>
                  {msg("Reverts: “")}
                  {t}
                  {msg(
                    "”. Message edits can be restored from each message's edit history; branches can be switched from the branch menu.",
                  )}
                </>
              ),

              confirmLabel: msg("Undo"),
            })
          ) {
            let t = await apiPost(`/stories/${storyId}/state/undo`);
            (invalidateStory(storyId), toast(t.summary));
          }
          return true;
        }
        default:
          return (
            ne({
              name: t,
              input: n,
            }),
            true
          );
      }
    },
    he = async ({ content, command, requestId }) => {
      try {
        if (command && (command.kind === `local_action` || command.kind === `hybrid`) && command.action)
          return await me(command.action, content);
        let i = await de.run(() =>
          apiPost(`/stories/${storyId}/turns`, {
            content,
            command: command
              ? {
                  id: command.id,
                  name: command.name,
                }
              : null,
            request_id: requestId,
          }),
        );
        return (
          i?.duplicate && toast(msg("That message was already saved — it was not sent twice."), `info`),
          i !== null
        );
      } catch {
        return false;
      }
    },
    mutation = useMutation({
      mutationFn: () => de.run(() => apiPost(`/stories/${storyId}/start`)),
    }),
    _e = (t) =>
      de
        .run(() => apiPost(`/stories/${storyId}/messages/${t}/regenerate`))
        .then((e) => {
          e &&
            e.created_branch_id &&
            toast(msg("Created a new branch; the previous continuation is kept in the branch menu."), `info`);
        })
        .catch(() => {}),
    ve = async (t) => {
      try {
        (await apiPost(`/stories/${storyId}/messages/${t}/branch`),
          invalidateStory(storyId),
          toast(msg("New branch created from this message. Continue writing to diverge."), `info`));
      } catch (e) {
        ue(e);
      }
    },
    ye = async (t) => {
      (await apiPost(`/stories/${storyId}/messages/${t}/select`).catch(ue), invalidateStory(storyId));
    };
  if (story.isLoading)
    return (
      <div className="p-6">
        <Spinner />
      </div>
    );

  if (story.isError || !story.data)
    return (
      <div className="p-6">
        <ErrorCallout error={story.error ?? msg("Story not found", {})} />
      </div>
    );

  let k = story.data,
    be = n.data?.messages ?? [],
    xe = k.settings_json.model_profile_id ?? i.data?.default_model_profile_id ?? null,
    Se = i.data?.profiles.find((e) => e.id === xe),
    Ce = i.data?.providers.find((e) => e.id === Se?.provider_id),
    we =
      Se && Ce
        ? {
            cloud: !!Ce.is_cloud || isCloudModelId(Se.model_id),
            provider: Ce.display_name,
            name: Se.display_name,
          }
        : null,
    Te = Object.fromEntries((cast.data ?? []).map((e) => [e.id, e])),
    Ee = [...be].reverse().find((e) => e.role === `assistant` && e.kind === `story` && !e.deleted_at)?.id ?? null,
    De = (e) => {
      (d(e), T(`known`), C(true));
    },
    Oe = (
      <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1">
      <StatusSection
        storyId={storyId}
        worldId={k.world_id}
        avatar={{
          id: k.active_avatar_id,
          name: k.avatar_name ?? null,
          portrait: k.avatar_portrait ?? null,
        }}
        tab={w}
        setTab={T}
        onOpenCharacter={(e) => fe(e)}
        knownFocus={u}
        setKnownFocus={d}
      />
      </div>
      <div className="border-t border-line p-3 pb-0">
        <MusicPlayer storyId={storyId} refreshKey={`${n.data?.messages?.length ?? 0}:${de.generating ? 1 : 0}`} />
      </div>
      <StoryPanelActions storyId={storyId} onRecap={() => ne({ name: `player_recap`, input: `` })} />
      </div>
    );

  return (
    <div className="flex h-full flex-col">
      <h1 className="sr-only">{k.title}</h1>
      <button
        type="button"
        onClick={() => document.getElementById(`story-composer`)?.focus()}
        className="sr-only z-50 rounded-md bg-accent text-sm text-accent-fg focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:px-3 focus:py-1.5"
      >
        {msg("Skip to message box")}
      </button>
      <StoryHeader
        story={k}
        branches={k.branches}
        manifest={contextPreview.data?.manifest}
        view={E}
        setView={D}
        rightOpen={S}
        setRightOpen={C}
        reviewCount={reviewCount.data ?? 0}
        generating={de.generating}
        onOpen={(e) =>
          e === `context`
            ? ie(true)
            : ne({
                name: e,
                input: ``,
              })
        }
      />

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <div className={cn(`relative isolate min-h-0 flex-1 flex-col`, E === `story` ? `flex` : `hidden`)}>
            <Backdrop storyId={storyId} count={be.length} generating={de.generating} on={settings.data?.scene_backdrops !== false} />
            <AutoScroll messages={be} ready={!n.isLoading}>
              {n.isLoading && <Spinner />}
              {n.isError && <ErrorCallout error={n.error} onRetry={() => n.refetch()} />}
              {be.length === 0 && !n.isLoading && (
                <div className="mx-auto max-w-lg py-16 text-center">
                  <EmptyState title={msg("The page is blank")}>
                    {msg(
                      "Start with the opening scene from your chosen starter, or write the first move yourself below.",
                    )}
                  </EmptyState>
                  <div className="flex justify-center gap-2">
                    <Button onClick={() => ie(true)}>
                      <Icon.Eye className="size-4" /> {msg("Preview first context")}
                    </Button>
                    <Button
                      variant="primary"
                      loading={mutation.isPending || de.generating}
                      onClick={() => mutation.mutate()}
                    >
                      <Icon.Play className="size-4" /> {msg("Generate opening scene")}
                    </Button>
                  </div>
                </div>
              )}
              {be.map((t) => (
                <MessageItem
                  m={t}
                  storyId={storyId}
                  liveText={de.live?.messageId === t.id ? de.live.text : undefined}
                  liveStatus={de.live?.messageId === t.id ? de.live.status : undefined}
                  livePortraits={de.livePortraits[t.id]}
                  speaker={
                    t.speaker_character_id
                      ? (Te[t.speaker_character_id] ?? {
                          id: t.speaker_character_id,
                          name: t.speaker_character_id,
                          asset_id: null,
                        })
                      : null
                  }
                  busy={de.generating}
                  onChanged={() => invalidateStory(storyId)}
                  onRegenerate={_e}
                  onBranch={ve}
                  onSelectAlt={ye}
                  highlight={ae === t.id}
                  protagonist={k.avatar_name ?? null}
                  yearLabel={n.data?.chronology?.year_label}
                  onEditScene={
                    t.id === Ee
                      ? () =>
                          ne({
                            name: `scene`,
                            input: ``,
                          })
                      : undefined
                  }
                  key={t.id}
                />
              ))}
              {be.length > 0 && be[be.length - 1].id === scene.data?.message_id && (
                <TurnAnalysisBar
                  storyId={storyId}
                  scene={scene.data}
                  busy={de.generating}
                  onAct={he}
                  onSuggest={(e) => le.current?.offer(e)}
                />
              )}
              {(n.data?.deleted_hidden ?? 0) > 0 && (
                <p className="py-2 text-center text-[11px] text-faint">
                  {n.data.deleted_hidden} {msg("removed message(s) hidden ·")}{" "}
                  <button className="underline" onClick={() => ce(true)}>
                    {msg("review")}
                  </button>
                </p>
              )}
            </AutoScroll>
            {!de.generating && <SpeakersPanel scene={scene.data} onOpenCharacter={De} />}
            <ResumeOffer storyId={storyId} messages={be} onRecap={() => ne({ name: `player_recap`, input: `` })} />
            <Composer
              ref={le}
              storyId={storyId}
              branchId={k.active_branch_id}
              generating={de.generating}
              enterToSend={settings.data?.enter_to_send ?? true}
              onSend={he}
              onStop={de.stop}
              onQuick={(e) =>
                e === `journal`
                  ? fe()
                  : ne({
                      name: `player_recap`,
                      input: ``,
                    })
              }
              model={we}
              key={k.active_branch_id ?? `main`}
            />
          </div>
          {E === `journal` && <JournalView storyId={storyId} worldId={k.world_id} focus={O} onJump={pe} />}
        </div>
        {S &&
          (mediaQuery ? (
            <aside
              className="w-[340px] shrink-0 border-l border-line bg-panel"
              aria-label={msg("Player status and cast")}
            >
              {Oe}
            </aside>
          ) : (
            <>
              <div className="fixed inset-0 z-30 bg-black/40" onClick={() => C(false)} />
              <aside
                className={cn(
                  `fixed z-40 flex flex-col bg-panel shadow-2xl`,
                  // StoryCore mobile (Phase 2): on a phone the panel is a sheet rising from the bottom
                  phone
                    ? `sc-sheet inset-x-0 bottom-0 h-[86dvh] rounded-t-2xl border-t border-line`
                    : `inset-y-0 right-0 w-[min(360px,92vw)] border-l border-line`,
                )}
                aria-label={msg("Player status and cast")}
              >
                {/* StoryCore mobile: a visible close button (touch only, no Back key needed) */}
                <div className="flex shrink-0 items-center border-b border-line px-2 py-1">
                  {phone && <span className="ml-2 text-sm font-semibold text-muted">{msg("Player status and cast")}</span>}
                  <IconButton label={msg("Close")} onClick={() => C(false)} className={cn(`ml-auto`, phone && `size-10`)}>
                    <Icon.X className={phone ? `size-5` : `size-4`} />
                  </IconButton>
                </div>
                <div className="min-h-0 flex-1">{Oe}</div>
              </aside>
            </>
          ))}
      </div>
      <RecapDialog
        storyId={storyId}
        action={te}
        onClose={() => ne(null)}
        onOpenJournal={(tab) => (tab ? (ee({ tab }), D(`journal`)) : fe())}
        onFocusStatus={() => {
          (C(true), T(`status`));
        }}
        onJump={pe}
      />

      <ContextInspector
        storyId={storyId}
        open={re}
        onClose={() => ie(false)}
        exclusions={k.settings_json.context_exclusions}
      />

      {de.consent && (
        <Modal
          open
          onOpenChange={(e) => !e && de.setConsent(null)}
          title={
            <span className="flex items-center gap-2">
              <Icon.Cloud className="size-4" /> {msg("Send story context to")} {de.consent.providerName}?
            </span>
          }
          footer={
            <>
              <Button variant="ghost" onClick={() => de.setConsent(null)}>
                {msg("Cancel")}
              </Button>
              <Button variant="primary" onClick={() => de.acceptConsent().catch(ue)}>
                {msg("I understand — continue")}
              </Button>
            </>
          }
        >
          <p className="text-sm text-muted">{de.consent.notice}</p>
          <Callout tone="info" className="mt-3">
            {msg(
              "You are asked once per provider. You can switch back to a local model at any time from the model selector.",
            )}
          </Callout>
        </Modal>
      )}
      {se && <RemovedMessagesDialog storyId={storyId} onClose={() => ce(false)} />}
    </div>
  );
}

var ANALYSIS_DONE = new Set([`succeeded`, `failed`, `skipped`, `stale`]);

function useAnalysisWatcher(e, t, n, r) {
  let i = React.useRef(null);
  React.useEffect(() => {
    let a = i.current;
    if (
      ((i.current = {
        id: t,
        status: n,
      }),
      !a || !t || !ANALYSIS_DONE.has(n))
    )
      return;
    let o = a.id === t && !ANALYSIS_DONE.has(a.status),
      s = a.id !== t;
    (o || s) && r(e);
  }, [e, t, n, r]);
}

function firstVisibleArticle(e) {
  let t = e.querySelectorAll(`article`),
    n = e.getBoundingClientRect().top,
    r = 0,
    i = t.length - 1;
  for (; r < i;) {
    let e = (r + i) >> 1;
    t[e].getBoundingClientRect().bottom > n ? (i = e) : (r = e + 1);
  }
  let a = t[r];
  if (!a) return null;
  let o = a.getBoundingClientRect();
  return {
    id: a.id,
    into: o.height ? (n - o.top) / o.height : 0,
  };
}

// v0.6 (test report "30 tours", B12): images loading after the view moved used to leave it on an older message.
// v0.6.2 (Kurio's DeepSeek test): following the end of a reply while it was written forced the reader to scroll back
// up to read each new reply from its start. The view no longer follows the text. Rules now:
// - when the story opens, the view goes to the end and stays there while the portraits load, until the reader moves;
// - when a message is added (the player's turn, a new reply), the view moves ONCE so that the player's message (or,
//   without one, the first new message) sits at the top of the screen: the reply is then written below it and the
//   view never moves while it grows (the reader keeps their own framing);
// - the ↓ button goes to the end once; a jump to an older message (event "story-jump") stops everything.
// The browser's own "scroll anchoring" stays off (it moved the view when a portrait loaded).
function AutoScroll({ children, messages, ready }) {
  let n = React.useRef(null),
    content = React.useRef(null),
    [r, i] = React.useState(true),
    follow = React.useRef(true), // only while the story is opening
    count = React.useRef(null), // null until the story's messages have loaded
    o = React.useRef(null),
    toBottom = () => {
      let e = n.current;
      e && (e.scrollTop = e.scrollHeight);
    },
    toTop = (id) => {
      let e = n.current,
        a = id && document.getElementById(`msg-${id}`);
      if (!e || !a) return;
      e.scrollTop += a.getBoundingClientRect().top - e.getBoundingClientRect().top - 8;
    };
  React.useLayoutEffect(() => {
    let e = n.current,
      c = content.current;
    if (!e || !c || typeof ResizeObserver > `u`) return;
    let t = e.clientWidth,
      ro = new ResizeObserver(() => {
        if (follow.current) return toBottom();
        if (e.clientWidth !== t && o.current) {
          // the window was resized while reading: keep the same article in view
          let a = document.getElementById(o.current.id);
          if (a) {
            let b = a.getBoundingClientRect();
            e.scrollTop += b.top - e.getBoundingClientRect().top + o.current.into * b.height;
          }
        }
        t = e.clientWidth;
      });
    ro.observe(e);
    ro.observe(c);
    let jump = () => (follow.current = false);
    window.addEventListener(`story-jump`, jump);
    return () => (ro.disconnect(), window.removeEventListener(`story-jump`, jump));
  }, []);
  let gesture = () => (follow.current = false);
  React.useLayoutEffect(() => {
    if (!ready) return;
    let before = count.current,
      now = messages.length;
    count.current = now;
    if (before === null) return (follow.current && toBottom(), void i(true)); // the story just loaded
    if (now <= before) return;
    follow.current = false;
    // a new message: put the player's latest message at the top (it is at most 2 messages from the end), else the
    // first new message (a reply to "Continue", the opening scene)
    let tail = messages.slice(-2),
      mine = [...tail].reverse().find((m) => m.role === `user`);
    toTop((mine ?? messages[before])?.id);
  }, [messages, ready]);
  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={n}
        style={{ overflowAnchor: `none` }}
        onWheel={gesture}
        onTouchMove={gesture}
        onPointerDown={gesture}
        onKeyDown={(e) => [`ArrowUp`, `ArrowDown`, `PageUp`, `PageDown`, `Home`, `End`, ` `].includes(e.key) && gesture()}
        onScroll={(e) => {
          let t = e.currentTarget,
            atEnd = t.scrollHeight - t.scrollTop - t.clientHeight < 80;
          (i(atEnd), (o.current = firstVisibleArticle(t)));
        }}
        className="story-scroll h-full overflow-y-auto overflow-x-hidden px-3 pb-6 sm:px-6"
        aria-live="polite"
        aria-busy={false}
      >
        <div ref={content}>{children}</div>
      </div>
      {!r && (
        <IconButton
          label={msg("Scroll to latest")}
          className="absolute bottom-3 right-6 size-8 border border-line bg-raised shadow"
          onClick={() => {
            i(true);
            toBottom();
          }}
        >
          <Icon.ArrowDown className="size-4" />
        </IconButton>
      )}
    </div>
  );
}

// v0.6.2: the picture of the scene's place behind the story text (services/backdrops.py). Asked again after each reply
// (the place is updated just after it); a new place fades in.
function Backdrop({ storyId, count, generating, on }) {
  let query = useQuery({
      queryKey: [`backdrop`, storyId, count, generating],
      queryFn: () => apiGet(`/stories/${storyId}/backdrop`),
      enabled: on && !generating,
      staleTime: 5000,
      refetchInterval: 20000,
      placeholderData: (prev) => prev,
    }),
    url = on ? query.data?.url : null;
  return url ? <div aria-hidden className="sc-backdrop" style={{ backgroundImage: `url("${url}")` }} key={url} /> : null;
}

function RemovedMessagesDialog({ storyId, onClose }) {
  let invalidateStory = useInvalidateStory(),
    [r, i] = React.useState(null);
  React.useEffect(() => {
    fetch(`/api/stories/${storyId}/messages?include_deleted=true`)
      .then((e) => e.json())
      .then((e) => i(e.messages.filter((e) => e.deleted_at)));
  }, [storyId]);
  let a = React.useMemo(() => r ?? [], [r]);
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      title={msg("Removed messages")}
      description={msg("Removed messages are excluded from context but kept on disk.")}
    >
      {a.length === 0 && <p className="text-sm text-muted">{msg("None.")}</p>}
      {a.map((t) => (
        <div className="mb-2 rounded-md border border-line p-2 text-sm" key={t.id}>
          <p className="text-xs text-faint">
            #{t.seq} {t.role}
          </p>
          <p className="line-clamp-3 text-muted">{t.content}</p>
          <Button
            size="sm"
            className="mt-1"
            onClick={async () => {
              (await apiPost(`/stories/${storyId}/messages/${t.id}/restore`),
                invalidateStory(storyId),
                i(a.filter((e) => e.id !== t.id)));
            }}
          >
            {msg("Restore")}
          </Button>
        </div>
      ))}
    </Modal>
  );
}
