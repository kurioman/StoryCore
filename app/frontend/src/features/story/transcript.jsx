// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { EXPRESSIONS, useSettings, useCommands } from "@/api/queries";
import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiPatch, errorMessage, apiDelete, apiPost, apiGet } from "@/api/legacy";
import * as Icon from "lucide-react";
import { msg } from "@/i18n";
import { Badge, Button, IconButton, Modal, Portrait, Spinner, Textarea, useUi } from "@/components/ui";
import { ChronoHeader } from "@/features/story/chrono";
import { ContextManifest } from "@/features/story/composer";
import { StoryMarkdown } from "@/features/story/prose";
import { cn, timeAgo } from "@/lib/util";
import { sceneKeys } from "@/features/story/api";
import { usePhoneLayout } from "@/lib/layout";
import { friendlyError, TechnicalDetails } from "@/lib/errors";

// v0.7.7 "clear errors": a stopped, incomplete or failed reply, said in plain words with the button that helps
function GenerationNotice({ status, error, cost, busy, onRetry }) {
  const failed = status === `failed` || error?.category === `budget`;
  const f = failed ? (friendlyError(error) ?? { title: msg("Generation failed."), text: ``, action: `retry`, technical: `` }) : null;
  return (
    <div
      className={cn(
        `mt-2 flex flex-wrap items-start gap-2 rounded-md px-2.5 py-1.5 text-xs`,
        failed ? `bg-danger-soft text-danger` : `bg-warn-soft text-warn`,
      )}
      role="status"
    >
      <Icon.CircleAlert className="mt-0.5 size-3.5 shrink-0" />
      <div className="min-w-0 flex-1">
        {status === `cancelled` && !failed && msg("Stopped — the text so far was kept.")}
        {status === `partial` && !failed && msg("Incomplete response — the text received so far was kept.")}
        {!failed && error && status !== `cancelled` && status !== `partial` && (
          <>
            <span className="font-medium">{friendlyError(error).title}</span> — {friendlyError(error).text}
          </>
        )}
        {f && (
          <>
            <span className="font-medium">{f.title}</span>
            {f.text ? <> — {f.text}</> : null}
          </>
        )}
        {typeof cost == `number` &&
          msg(" This attempt cost ${{v0}}.", {
            v0: cost.toFixed(4),
          })}
        {(f || error) && <TechnicalDetails text={(f ?? friendlyError(error)).technical} className="mt-1" />}
      </div>
      <div className="flex flex-wrap gap-1">
        {f?.action === `budget` && (
          <Button size="sm" variant="ghost" onClick={() => (window.location.hash = `#/settings/budget`)}>
            <Icon.Coins className="size-3" /> {msg("Budget settings")}
          </Button>
        )}
        {f?.action === `providers` && (
          <Button size="sm" variant="ghost" onClick={() => (window.location.hash = `#/settings/providers`)}>
            <Icon.Settings className="size-3" /> {msg("AI settings")}
          </Button>
        )}
        {!busy && (
          <Button size="sm" variant="ghost" onClick={onRetry} title={msg("Sends a new request; on a paid model it is billed again")}>
            <Icon.RefreshCw className="size-3" /> {msg("Retry")}
          </Button>
        )}
      </div>
    </div>
  );
}

function speakerColorIndex(e) {
  let t = 0;
  for (let n = 0; n < e.length; n++) t = (t * 31 + e.charCodeAt(n)) >>> 0;
  return t % 6;
}

function BeatPortrait({ b }) {
  let t = EXPRESSIONS()[b.expression - 1],
    n = b.beat === `speaking`,
    // StoryCore mobile (Phase 2): on a phone the portrait is a small card beside the text; a touch shows it in full
    phone = usePhoneLayout(),
    [zoom, setZoom] = React.useState(false);
  if (phone)
    return (
      <figure className="story-beat sc-beat-phone" aria-label={`${b.name}, ${t?.short ?? msg("Neutral", {})}`}>
        <button
          type="button"
          onClick={() => setZoom(true)}
          aria-label={msg("Show {{v0}}'s portrait", { v0: b.name })}
          className={cn(`sc-beat-thumb`, n ? `border-accent/70` : `border-line-strong`)}
        >
          <Portrait assetId={b.asset_id} name={b.name} variant="full" rounded="rounded-md" className="size-full" />
        </button>
        <figcaption className="sc-beat-name">
          {b.name}
          {t?.short ? ` · ${t.short}` : ``}
        </figcaption>
        {zoom && (
          <Modal open onOpenChange={(o) => !o && setZoom(false)} title={b.name} description={t?.short} size="md">
            <Portrait assetId={b.asset_id} name={b.name} variant="full" rounded="rounded-lg" className="mx-auto max-h-[70dvh] w-full object-contain" />
          </Modal>
        )}
      </figure>
    );
  return (
    <figure
      className="story-beat"
      aria-label={`${b.name}, ${t?.short ?? msg("Neutral", {})}, ${n ? `speaking` : `reacting`}`}
    >
      <div className="story-beat-frame">
        <Portrait
          assetId={b.asset_id}
          name={b.name}
          variant="full"
          rounded="rounded-lg"
          className={cn(
            `story-beat-fallback border`,
            n ? `border-accent/60` : `border-dashed border-line-strong opacity-95`,
          )}
        />
      </div>
      <figcaption className="mt-1 flex min-w-0 flex-wrap items-center gap-x-1.5 font-sans text-[11px] text-faint">
        <span className="font-medium text-muted">{b.name}</span>
        <span>
          {"· "}
          {t?.short ?? msg("Neutral")}
        </span>
        <span className={n ? `text-accent` : undefined}>
          {"· "}
          {n ? msg("speaks") : msg("reacts")}
        </span>
      </figcaption>
    </figure>
  );
}

function PresentChips({ beats }) {
  return (
    <div
      className="story-present"
      aria-label={msg("Also present: {{v0}}", {
        v0: beats.map((e) => e.name).join(`, `),
      })}
    >
      <span className="text-faint">{msg("Also present")}</span>
      {beats.map((e) => (
        <span className="story-present-chip" key={e.character_id}>
          <Portrait assetId={e.asset_id} name={e.name} className="size-6 shrink-0" rounded="rounded-full" />
          <span className="truncate">{e.name}</span>
        </span>
      ))}
    </div>
  );
}

function Beats({ beats }) {
  let t = beats.filter((e) => e.beat !== `present`),
    n = beats.filter((e) => e.beat === `present`);
  return (
    <>
      {t.length > 0 && (
        <div className={cn(`story-beats`, t.length > 1 && `story-beats-multi`)}>
          {t.map((e) => (
            <BeatPortrait b={e} key={e.character_id} />
          ))}
        </div>
      )}
      {n.length > 0 && <PresentChips beats={n} />}
    </>
  );
}

function MessageProse({
  text,
  presentation,
  inline,
  className,
  dialogueStyle = `emphasis`,
  protagonist,
  paragraphOffset = 0,
  showTopBeats = true,
  slice = false,
  streaming = false,
}) {
  let u = (presentation?.dialogue ?? []).map((e) => e.text),
    d = inline ? (presentation?.beats ?? []) : [],
    f = new Map();
  // "cinematic" reads like "emphasis"; only its colours differ (styles.css, html[data-dialogue=cinematic])
  let emphasis = dialogueStyle === `emphasis` || dialogueStyle === `cinematic`;
  if (emphasis) for (let e of presentation?.paragraphs ?? []) f.set(e.paragraph, e);
  let p = emphasis ? `full` : `verified`;
  if (!d.length && !f.size)
    return <StoryMarkdown text={text} className={className} dialogue={u} reading={p} streaming={streaming} />;
  let g = text.split(/\n\s*\n/).filter((e) => e.trim()),
    _ = new Set(),
    v = new Map(),
    y = [];
  // v0.6: a character's portrait comes back when their expression changes or when they speak again after someone
  // else; two paragraphs in a row with the same face show it once. Decided over the whole reply (the same choice in
  // every slice of an immersive reply); silent "present" characters still appear once.
  let lastFace = new Map(),
    lastCharacter = null;
  for (let e of [...d].sort((a, b) => (a.paragraph ?? -1) - (b.paragraph ?? -1))) {
    let inText = e.beat !== `present` && e.paragraph != null;
    if (!inText) {
      if (_.has(e.character_id)) continue;
    } else if (lastCharacter === e.character_id && lastFace.get(e.character_id) === e.expression) continue;
    _.add(e.character_id);
    inText && (lastFace.set(e.character_id, e.expression), (lastCharacter = e.character_id));
    let t = e.paragraph == null ? -1 : e.paragraph - paragraphOffset;
    e.paragraph == null || e.paragraph < 0
      ? showTopBeats && y.push(e)
      : t >= 0 && t < g.length
        ? v.set(t, [...(v.get(t) ?? []), e])
        : !slice && t >= g.length && y.push(e);
  }
  let b = null;
  return (
    <div className={cn(`story-flow`, className)}>
      {y.length > 0 && <Beats beats={y} />}
      {g.map((e, t) => {
        let n = f.get(t + paragraphOffset),
          r = n?.character_id ?? null,
          i = r === `protagonist` ? protagonist || msg("You", {}) : (n?.name ?? null),
          s = !!r && r !== b;
        return (
          n && (b = r),
          (
            <React.Fragment key={t}>
              {(v.get(t) ?? []).length > 0 && <Beats beats={v.get(t)} />}
              {n ? (
                <div
                  className={cn(
                    `story-para-dialogue`,
                    !r && `story-para-unknown`,
                    r === `protagonist` && `story-para-protagonist`,
                  )}
                  data-speaker={r ?? `unknown`}
                  style={
                    r && r !== `protagonist`
                      ? {
                          "--speaker-accent": `var(--spk-${speakerColorIndex(r)})`,
                        }
                      : undefined
                  }
                >
                  {s && i && (
                    <span className="story-speaker">
                      <span className="story-speaker-dot" aria-hidden />
                      {i}
                    </span>
                  )}
                  <StoryMarkdown text={e} dialogue={u} reading={p} />
                </div>
              ) : (
                <StoryMarkdown text={e} dialogue={u} reading={p} />
              )}
            </React.Fragment>
          )
        );
      })}
    </div>
  );
}

export function MessageItem({
  m: e,
  storyId,
  liveText,
  liveStatus,
  livePortraits,
  speaker,
  speakerName,
  busy,
  onChanged,
  onRegenerate,
  onBranch,
  onSelectAlt,
  highlight,
  protagonist,
  yearLabel,
  onEditScene,
}) {
  let { toast, confirm } = useUi(),
    settings = useSettings(),
    [b, x] = React.useState(false),
    [S, C] = React.useState(e.content),
    [w, T] = React.useState(false),
    [E, D] = React.useState(false),
    [O, ee] = React.useState(false),
    [te, ne] = React.useState(false),
    [rewriting, setRewriting] = React.useState(false),
    // StoryCore mobile (Phase 2): no mouse hover on a phone. Touching a message (or its "⋯" button) shows its actions.
    phone = usePhoneLayout(),
    [tapped, setTapped] = React.useState(false),
    re = settings.data?.dialogue_style ?? `cinematic`,
    ie = isPlayerStory(e) && !!e.immersive_reply_id,
    ae = liveStatus ?? e.status,
    oe = liveText ?? e.content,
    se = e.role === `user`,
    ce = e.kind === `ooc`,
    le = e.kind === `utility`,
    ue = !!e.deleted_at,
    de = e.generation ?? {},
    fe = de.error ?? null,
    pe = de.usage?.cost,
    me = de.diagnostics ?? null,
    mutation = useMutation({
      mutationFn: () =>
        apiPatch(`/stories/${storyId}/messages/${e.id}`, {
          content: S,
        }),
      onSuccess: () => {
        (x(false),
          onChanged(),
          toast(se ? msg("Message edited. Regenerate the reply to use the new text.", {}) : msg("Message edited", {})));
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    }),
    ge = useMutation({
      mutationFn: () => apiDelete(`/stories/${storyId}/messages/${e.id}`),
      onSuccess: () => {
        (onChanged(), toast(msg("Message removed from the transcript (restorable from “Show deleted”).")));
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    }),
    _e = useMutation({
      mutationFn: () => apiPost(`/stories/${storyId}/messages/${e.id}/restore`),
      onSuccess: onChanged,
    });
  if (le) {
    let t = e.command_json?.result ?? {};
    return (
      <div className="mx-auto my-3 max-w-[72ch] rounded-md border border-dashed border-line bg-panel px-3 py-2 text-[13px]">
        <div className="mb-1 flex items-center gap-2 text-xs text-faint">
          <Icon.SquareSlash className="size-3.5" />
          {" /"}
          {String(e.command_json?.name ?? `utility`)} {msg("result · not part of the story ·")} {timeAgo(e.created_at)}
        </div>
        {t.summary && <p className="text-muted">{t.summary}</p>}
        {t.issues?.length ? (
          <ul className="mt-1 list-disc pl-5 text-muted">
            {t.issues.map((e, t) => (
              <li key={t}>
                {e.description}
                {e.suggested_fix && (
                  <span className="text-faint">
                    {" "}
                    {msg("— fix:")} {e.suggested_fix}
                  </span>
                )}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    );
  }
  let ve = e.alternatives,
    ye = e.command_json;
  return (
    <article
      id={`msg-${e.id}`}
      onClick={
        phone
          ? (ev) => {
              // a touch on a button, link or field keeps its own meaning; selecting text does not toggle either
              if (ev.target.closest?.(`button,a,input,textarea,select,label,[role=button],[role=dialog]`)) return;
              if (window.getSelection?.()?.toString()) return;
              setTapped(!tapped);
            }
          : undefined
      }
      className={cn(
        `story-column group relative mx-auto w-full scroll-mt-24`,
        phone ? `sc-msg-phone py-2` : `py-3`,
        phone && tapped && `sc-msg-tapped`,
        ue && `opacity-50`,
        highlight && `rounded-md ring-2 ring-accent/60`,
      )}
      aria-label={msg("{{v0}}, message {{v1}}", {
        v0: se ? msg("You") : ce ? msg("Out of character") : msg("Narrator"),
        v1: e.seq,
      })}
    >
      {e.role === `assistant` && e.kind === `story` && e.chrono && !ue && (
        <ChronoHeader c={e.chrono} yearLabel={yearLabel} onEdit={onEditScene} pending={ae === `streaming`} />
      )}
      {!se && speaker && !ce && (
        <div className="mb-1.5 flex items-center gap-2">
          <Portrait assetId={speaker.asset_id} name={speaker.name} className="size-7" rounded="rounded-full" />
          <span className="text-xs font-medium text-muted">{speakerName ?? speaker.name}</span>
        </div>
      )}
      <div
        className={cn(
          se && !ie && `sc-user-bubble ml-auto w-fit max-w-[90%] min-w-0 rounded-lg border border-line bg-user px-3.5 py-2.5`,
          ie && !O && `ml-auto w-fit max-w-[90%]`,
          ie &&
            O &&
            `ml-auto w-fit max-w-[90%] min-w-0 rounded-lg border border-dashed border-line bg-user px-3.5 py-2.5`,
          ce && `rounded-lg border border-ooc-line bg-ooc px-3.5 py-2.5`,
        )}
      >
        {(ce || ye?.name) && (
          <div className="mb-1 flex flex-wrap items-center gap-1.5">
            {ce && <Badge tone="info">{msg("OOC")}</Badge>}
            {se && ye?.name && (
              <Badge tone="accent" title={ye.expansion}>
                /{ye.name}
              </Badge>
            )}
          </div>
        )}
        {b ? (
          <div className="space-y-2">
            <Textarea
              autoFocus
              value={S}
              onChange={(e) => C(e.target.value)}
              className="min-h-40 font-serif text-[15px]"
              aria-label={msg("Edit message")}
            />

            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => x(false)}>
                <Icon.X className="size-3.5" /> {msg("Cancel")}
              </Button>
              <Button variant="primary" size="sm" loading={mutation.isPending} onClick={() => mutation.mutate()}>
                <Icon.Check className="size-3.5" /> {msg("Save edit")}
              </Button>
            </div>
          </div>
        ) : oe ? (
          ie && !O ? (
            <p className="text-xs text-faint">
              {msg("Your turn is shown inside the scene below, exactly as you wrote it.")}{" "}
              <button type="button" className="underline" onClick={() => ee(true)}>
                {msg("Show original message")}
              </button>
            </p>
          ) : se || ce ? (
            <>
              <StoryMarkdown text={oe} className="prose-ui" />
              {ie && (
                <button type="button" className="mt-1 text-[11px] text-faint underline" onClick={() => ee(false)}>
                  {msg("Hide (shown in the scene below)")}
                </button>
              )}
            </>
          ) : e.immersive && ae !== `streaming` ? (
            <ImmersiveReply
              m={e}
              inline={settings.data?.inline_portraits ?? true}
              dialogueStyle={re}
              protagonist={protagonist}
            />
          ) : (
            <MessageProse
              text={oe}
              presentation={
                // v0.6: the portraits found while writing show at once, until the saved ones replace them
                ae === `streaming`
                  ? livePortraits?.length
                    ? { beats: livePortraits }
                    : undefined
                  : (e.presentation ?? (livePortraits?.length && !e.edited_at ? { beats: livePortraits } : undefined))
              }
              inline={settings.data?.inline_portraits ?? true}
              className={cn(`prose-story`, ae === `streaming` && `caret`)}
              dialogueStyle={re}
              protagonist={protagonist}
              streaming={ae === `streaming`}
            />
          )
        ) : ae === `streaming` ? (
          <p className="caret text-sm text-faint">{msg("Writing")}</p>
        ) : null}
      </div>
      {!se && !ue && ae !== `streaming` && <LoreConflicts items={de.lore_conflicts} />}
      {!se && !ue && ae !== `streaming` && (
        <ContinuityAlerts items={de.continuity_alerts} onRegenerate={busy ? undefined : () => onRegenerate(e.id)} />
      )}
      {!se && !ue && ae !== `streaming` && de.info_table?.lines?.length > 0 && (
        <InfoTable storyId={storyId} messageId={e.id} info={de.info_table} busy={busy} onChanged={onChanged} />
      )}
      {!se && (ae !== `complete` || fe) && ae !== `streaming` && (
        <GenerationNotice status={ae} error={fe} cost={pe} busy={busy} onRetry={() => onRegenerate(e.id)} />
      )}
      <div className={cn(`sc-msg-meta mt-1 flex min-h-6 items-center gap-1 text-[11px] text-faint`, se && `justify-end`)}>
        {ve && ve.ids.length > 1 && (
          <span className="mr-1 flex items-center gap-0.5" aria-label={msg("Alternative replies")}>
            <IconButton
              label={msg("Previous alternative")}
              className="size-5"
              disabled={busy || ve.index === 0 || !ve.leaf[ve.index - 1]}
              onClick={() => onSelectAlt(ve.ids[ve.index - 1])}
            >
              <Icon.ChevronLeft className="size-3" />
            </IconButton>
            {ve.index + 1}/{ve.ids.length}
            <IconButton
              label={msg("Next alternative")}
              className="size-5"
              disabled={busy || ve.index >= ve.ids.length - 1 || !ve.leaf[ve.index + 1]}
              onClick={() => onSelectAlt(ve.ids[ve.index + 1])}
            >
              <Icon.ChevronRight className="size-3" />
            </IconButton>
          </span>
        )}
        {!se && de.model_id ? <span title={`${de.provider_name ?? ``}`}>{String(de.model_id)}</span> : null}
        {!se && typeof pe == `number` ? (
          <span
            className={phone ? (tapped ? `` : `hidden`) : `opacity-0 group-hover:opacity-100`}
            title={msg(
              "Cost of this reply as reported by OpenRouter. Scene analysis and memory capture are separate requests.",
            )}
          >
            · ${pe.toFixed(4)}
          </span>
        ) : null}
        {e.edited_at && <span>{msg("· edited")}</span>}
        <span className={phone ? (tapped ? `` : `hidden`) : `opacity-0 group-hover:opacity-100`}>
          · #{e.seq}
          {" · "}
          {timeAgo(e.created_at)}
        </span>
        {phone && !tapped && (
          <button
            type="button"
            onClick={() => setTapped(true)}
            aria-label={msg("Message actions")}
            className={cn(`flex size-8 items-center justify-center rounded-md text-faint`, !se && `ml-auto`)}
          >
            <Icon.Ellipsis className="size-4" />
          </button>
        )}
        <div
          className={cn(
            phone
              ? cn(`sc-msg-actions flex-wrap items-center gap-0.5`, tapped ? `flex` : `hidden`)
              : `flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100`,
            !se && `ml-auto`,
          )}
        >
          {ue ? (
            <Button size="sm" variant="ghost" onClick={() => _e.mutate()}>
              <Icon.RotateCcw className="size-3" /> {msg("Restore")}
            </Button>
          ) : (
            <>
              <IconButton
                label={msg("Copy")}
                onClick={() => navigator.clipboard.writeText(oe).then(() => toast(msg("Copied")))}
              >
                <Icon.Copy className="size-3.5" />
              </IconButton>
              <IconButton
                label={msg("Edit")}
                disabled={busy || ae === `streaming`}
                onClick={() => {
                  (C(e.content), x(true));
                }}
              >
                <Icon.Pencil className="size-3.5" />
              </IconButton>
              {!se && !ce && e.content?.trim() && (
                <IconButton
                  label={msg("Rewrite one paragraph")}
                  disabled={busy || ae === `streaming`}
                  onClick={() => setRewriting(true)}
                >
                  <Icon.WandSparkles className="size-3.5" />
                </IconButton>
              )}
              {(e.version_count ?? 0) > 0 && (
                <IconButton label={msg("Edit history")} onClick={() => T(true)}>
                  <Icon.RotateCcwClock className="size-3.5" />
                </IconButton>
              )}
              {!se && e.has_context && (
                <IconButton label={msg("Context sent to the model")} onClick={() => D(true)}>
                  <Icon.Layers className="size-3.5" />
                </IconButton>
              )}
              {!se && me && (
                <IconButton label={msg("How this reply was generated")} active={te} onClick={() => ne(!te)}>
                  <Icon.Info className="size-3.5" />
                </IconButton>
              )}
              <IconButton
                label={se ? msg("Generate a new reply from here") : msg("Regenerate")}
                disabled={busy}
                onClick={() => onRegenerate(e.id)}
              >
                <Icon.RefreshCw className="size-3.5" />
              </IconButton>
              <IconButton label={msg("Branch from here")} disabled={busy} onClick={() => onBranch(e.id)}>
                <Icon.GitBranch className="size-3.5" />
              </IconButton>
              <IconButton
                label={msg("Delete")}
                disabled={busy || ae === `streaming`}
                onClick={async () => {
                  (await confirm({
                    title: msg("Remove this message?"),
                    body: msg(
                      "It is hidden from the transcript and from future context. Journal records that cite it are flagged as possibly stale. You can restore it later.",
                    ),
                    confirmLabel: msg("Remove"),
                    danger: true,
                  })) && ge.mutate();
                }}
              >
                <Icon.Trash className="size-3.5" />
              </IconButton>
            </>
          )}
          {phone && (
            <IconButton label={msg("Hide actions")} onClick={() => setTapped(false)}>
              <Icon.X className="size-3.5" />
            </IconButton>
          )}
        </div>
      </div>
      {te && me && <DiagnosticsTable d={me} />}
      {w && <VersionsDialog storyId={storyId} m={e} onClose={() => T(false)} onRestored={onChanged} />}
      {rewriting && (
        <RewriteDialog storyId={storyId} m={e} onClose={() => setRewriting(false)} onSaved={onChanged} />
      )}
      {E && <MessageContextDialog storyId={storyId} messageId={e.id} onClose={() => D(false)} />}
    </article>
  );
}

function isPlayerStory(e) {
  return e.role === `user` && e.kind === `story`;
}

function ImmersiveReply({ m: e, inline, dialogueStyle, protagonist }) {
  let i = e.immersive?.items ?? [],
    a = 0,
    o = true;
  return (
    <div className="prose-story story-flow">
      {i.map((i, s) => {
        if (i.source === `player_authored`)
          return (
            <div
              className="story-player"
              aria-label={msg("{{v0}} (your words)", {
                v0: protagonist || `You`,
              })}
              key={s}
            >
              <span className="story-speaker">
                <span
                  className="story-speaker-dot"
                  aria-hidden
                  style={{
                    background: `var(--c-accent)`,
                  }}
                />

                {protagonist || msg("You")}
              </span>
              {i.text}
            </div>
          );

        let c = a;
        a += i.text.split(/\n\s*\n/).filter((e) => e.trim()).length;
        let l = o;
        return (
          (o = false),
          (
            <MessageProse
              text={i.text}
              presentation={e.presentation}
              inline={inline}
              dialogueStyle={dialogueStyle}
              protagonist={protagonist}
              paragraphOffset={c}
              showTopBeats={l}
              slice
              key={s}
            />
          )
        );
      })}
    </div>
  );
}

function DiagnosticsTable({ d }) {
  let t = [
    [msg("Model", {}), d.model],
    [msg("Route", {}), d.provider],
    [msg("Generation", {}), d.generation_id],
    [msg("Ended with", {}), d.finish_reason],
    [msg("Provider's reason", {}), d.native_finish_reason],
    [msg("Reasoning", {}), d.reasoning],
    [msg("Output limit", {}), d.max_tokens],
    [msg("Input tokens", {}), d.input_tokens],
    [msg("Output tokens", {}), d.output_tokens],
    [msg("Hidden reasoning tokens", {}), d.reasoning_tokens],
    [msg("Visible tokens", {}), d.visible_tokens],
    [msg("First text after (s)", {}), d.first_text_s],
    [msg("Total time (s)", {}), d.duration_s],
    [msg("Characters saved", {}), d.chars],
    [msg("Error", {}), d.error],
  ];

  return (
    <dl
      className="mt-1 grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)] gap-x-2 rounded-md bg-panel-2 px-2.5 py-1.5 text-[11px] text-muted"
      aria-label={msg("How this reply was generated")}
    >
      {t
        .filter(([, e]) => e != null)
        .map(([e, t]) => (
          <div className="contents" key={e}>
            <dt className="text-faint">{e}</dt>
            <dd className="[overflow-wrap:anywhere]">{t}</dd>
          </div>
        ))}
    </dl>
  );
}

function LoreConflicts({ items }) {
  let t = (Array.isArray(items) ? items : []).filter((e) => !!e && typeof e.message == `string`);
  return t.length ? (
    <div
      className="mt-2 rounded-md bg-warn-soft px-2.5 py-1.5 text-xs text-warn"
      role="note"
      aria-label={msg("Possible lore conflict")}
    >
      <p className="font-medium">{msg("Possible lore conflict — the reply was not changed:")}</p>
      <ul className="mt-0.5 list-disc pl-4">
        {t.map((e) => (
          <li key={e.text}>{e.message}</li>
        ))}
      </ul>
      <p className="mt-0.5 text-faint">{msg("Regenerate or edit the reply if this was not intended.")}</p>
    </div>
  ) : null;
}

// Phase 2 (step 4): what the narrator's info block changed (place, time, relationships, HP, mana...), shown under the
// reply as a reminder and a safety net: each line can be cancelled or corrected (backend services/info_table.py)
const INFO_ICONS = { place: `📍`, time: `🕒`, days: `📅`, present: `👥`, relationship: `❤️`, stat: `⚡`, condition: `🩹`,
  item: `🎒`, mood: `🙂`, fact: `📜` };

function InfoTable({ storyId, messageId, info, busy, onChanged }) {
  let { toast } = useUi(),
    [open, setOpen] = React.useState(false),
    [editing, setEditing] = React.useState(null),
    [value, setValue] = React.useState(``),
    lines = info.lines.filter((l) => l.status !== `unchanged`),
    mutation = useMutation({
      mutationFn: ({ line, value }) => apiPost(`/stories/${storyId}/messages/${messageId}/info`, { line, value }),
      onSuccess: () => {
        setEditing(null);
        onChanged();
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    }),
    statusText = (l) =>
      l.status === `proposed`
        ? msg("to review")
        : l.status === `dropped`
          ? msg("ignored")
          : null;
  if (!lines.length) return null;
  return (
    <div className="mt-2 rounded-md border border-line bg-panel-2/50 px-2.5 py-1.5 text-xs" role="note"
      aria-label={msg("What changed")}>
      <button type="button" className="flex w-full items-center gap-1.5 text-left font-medium text-muted"
        onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <Icon.ClipboardList className="size-3.5" />
        <span className="min-w-0 flex-1 truncate">
          {msg("What changed")}
          {!open && `: ` + lines.filter((l) => l.status !== `dropped`).map((l) => l.label).slice(0, 3).join(` · `)}
          {!open && lines.length > 3 && ` …`}
        </span>
        {info.edited_by_player && <Badge>{msg("corrected")}</Badge>}
        <Icon.ChevronDown className={cn(`size-3.5 transition-transform`, open && `rotate-180`)} />
      </button>
      {open && (
        <ul className="mt-1 space-y-1">
          {lines.map((l) => (
            <li key={l.i} className={cn(`flex flex-wrap items-center gap-1.5`, l.status === `dropped` && `text-faint`)}>
              {editing === l.i ? (
                <form className="flex w-full flex-wrap items-center gap-1.5"
                  onSubmit={(ev) => { ev.preventDefault(); mutation.mutate({ line: l.i, value }); }}>
                  <input className="min-w-0 flex-1 rounded border border-line bg-panel px-2 py-1 text-xs"
                    value={value} onChange={(ev) => setValue(ev.target.value)} autoFocus
                    aria-label={msg("Corrected line")} />
                  <Button size="sm" variant="primary" type="submit" loading={mutation.isPending}>{msg("Save")}</Button>
                  <Button size="sm" variant="ghost" type="button" onClick={() => setEditing(null)}>{msg("Cancel")}</Button>
                </form>
              ) : (
                <>
                  <span aria-hidden="true">{INFO_ICONS[l.kind] ?? `•`}</span>
                  <span className={cn(`min-w-0 flex-1`, l.status === `dropped` && `line-through`)}>{l.label}</span>
                  {statusText(l) && (
                    <span className={l.status === `proposed` ? `text-warn` : `text-faint`} title={l.reason || undefined}>
                      {statusText(l)}
                    </span>
                  )}
                  {!busy && l.status !== `dropped` && (
                    <>
                      <IconButton label={msg("Correct this line")}
                        onClick={() => { setEditing(l.i); setValue(l.text); }}>
                        <Icon.Pencil className="size-3.5" />
                      </IconButton>
                      <IconButton label={msg("Cancel this change")}
                        onClick={() => mutation.mutate({ line: l.i, value: null })}>
                        <Icon.X className="size-3.5" />
                      </IconButton>
                    </>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// v0.5 phase 7.6: continuity notices found after the reply (no model call, or inside the scene analysis)
function ContinuityAlerts({ items, onRegenerate }) {
  let all = (Array.isArray(items) ? items : []).filter((e) => e && typeof e.kind == `string`),
    // v0.6 (test report "30 tours", B9): most of the reply repeated earlier replies and was removed
    repeated = all.find((e) => e.kind === `mostly_repeated`),
    list = all.filter((e) => e.kind !== `mostly_repeated`),
    text = (e) =>
      e.kind === `dead_speaks`
        ? msg("{{v0}} speaks, but the journal records their death.", { v0: e.name })
        : e.kind === `time_back`
          ? msg("The time goes back from “{{v0}}” to “{{v1}}” on the same day.", { v0: e.from, v1: e.to })
          : e.kind === `contradiction`
            ? msg("May contradict a pinned memory: {{v0}}", { v0: e.text })
            : null;
  list = list.filter((e) => text(e));
  let repeatedNote = repeated ? (
    <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md bg-warn-soft px-2.5 py-1.5 text-xs text-warn"
      role="note" aria-label={msg("Repetitive reply")}>
      <span className="font-medium">
        {repeated.nothing_left
          ? msg("Repetitive reply: it only repeats earlier replies.")
          : msg("Repetitive reply: {{v0}} of the {{v1}} characters written repeated earlier replies and were removed.", {
              v0: Math.max(0, (repeated.generated ?? 0) - (repeated.kept ?? 0)),
              v1: repeated.generated ?? 0,
            })}
      </span>
      {onRegenerate && (
        <Button size="sm" variant="ghost" onClick={onRegenerate}>
          <Icon.RefreshCw className="size-3" /> {msg("Regenerate")}
        </Button>
      )}
    </div>
  ) : null;
  if (!list.length) return repeatedNote;
  return (
    <>
      {repeatedNote}
      {list.length ? (
    <div className="mt-2 rounded-md bg-warn-soft px-2.5 py-1.5 text-xs text-warn" role="note"
      aria-label={msg("Possible continuity problem")}>
      <p className="font-medium">{msg("Possible continuity problem — the reply was not changed:")}</p>
      <ul className="mt-0.5 list-disc pl-4">
        {list.map((e, i) => (
          <li key={i}>{text(e)}</li>
        ))}
      </ul>
      <p className="mt-0.5 text-faint">{msg("Regenerate or edit the reply if this was not intended.")}</p>
    </div>
      ) : null}
    </>
  );
}

function VersionsDialog({ storyId, m: t, onClose, onRestored }) {
  let query = useQuery({
      queryKey: [`versions`, t.id],
      queryFn: () => apiGet(`/stories/${storyId}/messages/${t.id}/versions`),
    }),
    { toast } = useUi();
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      title={msg("Edit history")}
      description={msg(
        "Earlier versions are kept. Restoring creates a new edit (the current text is kept in history too).",
      )}
      size="lg"
    >
      <div className="space-y-3">
        {query.data?.versions.map((i) => (
          <div className="rounded-md border border-line p-3" key={i.id}>
            <div className="mb-1 flex items-center justify-between text-xs text-faint">
              <span>
                {msg("Saved")} {timeAgo(i.created_at)}
              </span>
              <Button
                size="sm"
                onClick={async () => {
                  (await apiPost(`/stories/${storyId}/messages/${t.id}/versions/${i.id}/restore`),
                    toast(msg("Version restored")),
                    onRestored(),
                    onClose());
                }}
              >
                {msg("Restore")}
              </Button>
            </div>
            <p className="whitespace-pre-wrap text-sm text-muted">{i.content}</p>
          </div>
        ))}
      </div>
    </Modal>
  );
}

function MessageContextDialog({ storyId, messageId, onClose }) {
  let query = useQuery({
    queryKey: [`msgctx`, messageId],
    queryFn: () => apiGet(`/stories/${storyId}/messages/${messageId}/context`),
  });
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      title={msg("Context sent for this reply")}
      description={msg("Exactly what was included when this reply was generated (API keys are never part of context).")}
      size="lg"
    >
      {query.data?.context ? (
        <ContextManifest manifest={query.data.context} />
      ) : (
        <p className="text-sm text-muted">{msg("No context record for this message.")}</p>
      )}
      {query.data?.params && (
        <p className="mt-3 text-xs text-faint">
          {msg("Parameters sent:")} {JSON.stringify(query.data.params)}
        </p>
      )}
    </Modal>
  );
}

export function SpeakersPanel({ scene, onOpenCharacter }) {
  if (!scene || !scene.settings.show_scene_portraits) return null;
  let n = scene.status === `pending` || scene.status === `running`,
    r = scene.beats.filter(
      (t) => t.beat === `reacting` && !scene.speakers.some((e) => e.character_id === t.character_id),
    );
  return !scene.speakers.length && !r.length && !n ? null : (
    <div
      className="border-t border-line bg-panel/60 px-3 py-1.5 sm:px-6"
      aria-label={msg("Speakers in the latest reply")}
    >
      <div className="story-column mx-auto flex items-center gap-2 overflow-x-auto">
        <span className="shrink-0 text-[10px] uppercase tracking-wide text-faint">{msg("Scene")}</span>
        <ol className="flex items-center gap-2">
          {scene.speakers.map((n, r) => {
            let i = n.character_id === scene.active_speaker_id,
              a = EXPRESSIONS()[n.expression - 1];
            return (
              <li key={n.character_id}>
                <button
                  onClick={() => onOpenCharacter(n.character_id)}
                  title={`${n.name} — ${a?.name ?? msg("Neutral", {})}${n.evidence ? ` (“${n.evidence}”)` : ``}`}
                  aria-label={`${r + 1}. ${n.name}, ${a?.short ?? msg("Neutral", {})}${i ? `, speaking` : ``}`}
                  className={cn(
                    `flex items-center gap-1.5 rounded-md border p-1 pr-2 text-left`,
                    i ? `border-accent/70 bg-accent/10` : `border-line hover:border-line-strong`,
                  )}
                >
                  <Portrait
                    assetId={n.asset_id}
                    name={n.name}
                    className={cn(`size-9 shrink-0`, i && `ring-2 ring-accent`)}
                  />

                  <span className="min-w-0">
                    <span className="block max-w-28 truncate text-[12px] font-medium">{n.name}</span>
                    <span className="block text-[10px] text-faint">
                      {a?.short ?? msg("Neutral")}
                      {i && <span className="text-accent"> {msg("· speaking")}</span>}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
          {r.map((e) => {
            let n = EXPRESSIONS()[e.expression - 1];
            return (
              <li key={e.character_id}>
                <button
                  onClick={() => onOpenCharacter(e.character_id)}
                  title={msg("{{v0}} — {{v1}}, reacting without speaking{{v2}}", {
                    v0: e.name,
                    v1: n?.name ?? `Neutral`,
                    v2: e.anchor ? ` (“${e.anchor}”)` : ``,
                  })}
                  aria-label={msg("{{v0}}, {{v1}}, reacting", {
                    v0: e.name,
                    v1: n?.short ?? `Neutral`,
                  })}
                  className="flex items-center gap-1.5 rounded-md border border-dashed border-line p-1 pr-2 text-left hover:border-line-strong"
                >
                  <Portrait assetId={e.asset_id} name={e.name} className="size-9 shrink-0 opacity-90" />
                  <span className="min-w-0">
                    <span className="block max-w-28 truncate text-[12px] font-medium">{e.name}</span>
                    <span className="block text-[10px] text-faint">
                      {n?.short ?? msg("Neutral")} {msg("· reacting")}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
        {n && (
          <span className="flex shrink-0 items-center gap-1 text-[11px] text-faint">
            <Spinner className="size-3" /> {msg("reading the scene…")}
          </span>
        )}
        {scene.source === `heuristic` && scene.speakers.length > 0 && (
          <Badge title={msg("Rule-based guess; scene analysis did not run for this reply")}>{msg("guess")}</Badge>
        )}
      </div>
    </div>
  );
}

function InlineEmphasis({ text }) {
  return (
    <>
      {text
        .split(/(\*[^*\n]+\*)/)
        .map((e, t) =>
          e.length > 2 && e.startsWith(`*`) && e.endsWith(`*`) ? (
            <em key={t}>{e.slice(1, -1)}</em>
          ) : (
            <span key={t}>{e}</span>
          ),
        )}
    </>
  );
}

export function TurnAnalysisBar({ storyId, scene, busy, onAct, onSuggest }) {
  let queryClient = useQueryClient(),
    commands = useCommands(storyId),
    [s, c] = React.useState(null),
    [l, u] = React.useState(null);
  if (!scene || !scene.message_id || !scene.is_head || busy) return null;
  let d = scene.message_id,
    f = (commands.data ?? []).find((e) => e.name === `continue` && e.enabled) ?? null,
    p = scene.settings.action_suggestions_enabled,
    g = scene.status === `skipped`,
    v = async (e, t) => {
      c(e);
      try {
        return await onAct(t);
      } finally {
        c(null);
      }
    },
    y = async () => {
      u(null);
      try {
        await apiPost(`/messages/${d}/analysis`);
      } catch (e) {
        u(errorMessage(e));
      }
      queryClient.invalidateQueries({
        queryKey: sceneKeys.scene(storyId),
      });
    },
    b = scene.status === `pending` || scene.status === `running`;
  return (
    <section
      aria-label={msg("Next action")}
      className="sc-next story-column mx-auto mb-4 mt-1 rounded-lg border border-line bg-panel/50 p-2.5"
    >
      <div className="mb-1.5 flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-faint">
        <Icon.Sparkles className="size-3" /> {msg("What do you do next?")}
        <span className="sc-next-hint normal-case tracking-normal">
          {msg("Pick one to edit it; nothing is sent until you press Send.")}
        </span>
      </div>
      {!p && scene.status === `failed` && (
        <p className="mb-2 flex flex-wrap items-center gap-2 text-[12px]">
          <span className="text-warn">
            {msg("Scene analysis failed:")} {scene.error}
          </span>
          <Button size="sm" variant="ghost" onClick={y}>
            <Icon.RotateCcw className="size-3.5" /> {msg("Retry")}
          </Button>
          {l && <span className="text-danger">{l}</span>}
        </p>
      )}
      {p && (
        <div className="mb-2">
          {b && (
            <div className="story-suggestions" aria-busy="true">
              {[0, 1, 2].map((e) => (
                <div className="h-12 animate-pulse rounded-md bg-panel-2" key={e} />
              ))}
            </div>
          )}
          {b && (
            <p className="mt-1 flex items-center gap-1 text-[11px] text-faint" role="status">
              <Spinner className="size-3" /> {msg("Preparing suggestions…")}
            </p>
          )}
          {!b && scene.suggestions.length > 0 && (
            <ul className="story-suggestions">
              {scene.suggestions.map((e) => (
                <li key={e.id}>
                  <button
                    disabled={!!s}
                    onClick={() => onSuggest(e.label)}
                    title={e.label}
                    aria-label={msg("Use this suggestion: {{v0}}", {
                      v0: e.label,
                    })}
                    className="h-full w-full rounded-md border border-line p-2 text-left text-[13px] leading-snug hover:border-accent/60 focus-visible:border-accent disabled:opacity-60"
                  >
                    {e.approach && (
                      <span className="mb-0.5 block text-[10px] uppercase tracking-wide text-faint">{e.approach}</span>
                    )}
                    <span className="line-clamp-5 [overflow-wrap:anywhere]">
                      <InlineEmphasis text={e.label} />
                    </span>
                    {e.description && <span className="mt-0.5 block text-[11px] text-muted">{e.description}</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {!b && scene.suggestions.length > 0 && scene.suggestions.some((e) => e.format !== `draft`) && !g && (
            <p className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-faint">
              {msg("These were written before suggestions became ready-to-edit drafts.")}
              <Button size="sm" variant="ghost" onClick={y}>
                <Icon.RefreshCw className="size-3" /> {msg("Refresh suggestions")}
              </Button>
            </p>
          )}
          {!b && scene.suggestions.length === 0 && (
            <p className="flex flex-wrap items-center gap-2 text-[12px] text-faint">
              {scene.status === `failed` || scene.suggestions_error ? (
                <span className="text-warn">
                  {msg("Suggestions unavailable:")} {scene.suggestions_error ?? scene.error}
                </span>
              ) : g ? (
                <span>{scene.error}</span>
              ) : (
                <span>{msg("No suggestions for this reply yet.")}</span>
              )}
              {!g && (
                <Button size="sm" variant="ghost" onClick={y}>
                  <Icon.RotateCcw className="size-3.5" />{" "}
                  {scene.status === `none` ? msg("Suggest actions") : msg("Retry")}
                </Button>
              )}
              {l && <span className="text-danger">{l}</span>}
            </p>
          )}
        </div>
      )}
      <RelationshipChanges changes={scene.relationship_changes} mode={scene.settings.relationship_mode} />
      <div className="flex flex-wrap items-center gap-1.5">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => document.getElementById(`story-composer`)?.focus()}
          title={msg("Type your own action, words or direction in the message box")}
        >
          <Icon.PenLine className="size-3.5" /> {msg("Write your own…")}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={!f || !!s}
          loading={s === `continue`}
          title={msg("Let the scene move on without your character taking a new action")}
          onClick={() =>
            f &&
            v(`continue`, {
              content: ``,
              command: f,
              requestId: `cont:${d}`,
            })
          }
        >
          <Icon.FastForward className="size-3.5" /> {msg("Continue scene")}
        </Button>
      </div>
    </section>
  );
}

var signed = (e) => (e > 0 ? `+${e}` : String(e)),
  capitalize = (e) => e.charAt(0).toUpperCase() + e.slice(1);

function RelationshipChanges({ changes, mode }) {
  if (!changes.length) return null;
  let n = changes.some((e) => e.impact === `major` || e.status === `proposed`),
    r = mode === `review` && changes.some((e) => e.status === `proposed`);
  return (
    <div
      role="status"
      aria-label={msg("Relationship changes")}
      className={cn(
        `mb-2 rounded-md px-2 py-1.5 text-[12px]`,
        n ? `border border-accent/50 bg-accent/10` : `bg-panel-2/60 text-muted`,
      )}
    >
      <span className="mr-1 inline-flex items-center gap-1 font-medium text-fg">
        <Icon.HeartHandshake className="size-3.5" /> {n ? msg("A notable shift") : msg("Relationships")}
      </span>
      <ul className="mt-0.5 space-y-0.5">
        {changes.map((e, t) => (
          <li key={t}>
            <span className="text-fg">{e.source_name}</span>
            {" → "}
            {e.target_name}
            {": "}
            {capitalize(e.dimension)} {signed(e.delta)}
            {e.status === `proposed` && (
              <Badge tone="accent" className="ml-1">
                {msg("awaiting your review")}
              </Badge>
            )}
            {e.evidence && (
              <span className="text-faint">
                {" — “"}
                {e.evidence}”
              </span>
            )}
          </li>
        ))}
      </ul>
      {r && (
        <p className="mt-1 text-[11px] text-faint">
          {msg(
            "“Review every change” is on, so nothing is applied automatically. Accept these in the review queue, or switch to Automatic (conservative) in Settings → Memory capture → Relationship changes.",
          )}
        </p>
      )}
    </div>
  );
}

// v0.6.2: rewrite one paragraph of a reply. Pick the paragraph, say what to change (optional), look at the proposal,
// then keep it (saved as an edit: "Edit history" brings the old text back) or try again.
function splitParagraphs(text) {
  return String(text ?? ``)
    .split(/\n\s*\n/)
    .filter((p) => p.trim());
}

function RewriteDialog({ storyId, m, onClose, onSaved }) {
  let { toast } = useUi(),
    parts = splitParagraphs(m.content),
    [pick, setPick] = React.useState(null),
    [wish, setWish] = React.useState(``),
    [proposal, setProposal] = React.useState(null),
    ask = useMutation({
      mutationFn: () => apiPost(`/stories/${storyId}/messages/${m.id}/rewrite`, { paragraph: pick, instruction: wish }),
      onSuccess: (r) => setProposal(r.text),
      onError: (err) => toast(errorMessage(err), `danger`),
    }),
    keep = useMutation({
      mutationFn: () => apiPost(`/stories/${storyId}/messages/${m.id}/rewrite`, { paragraph: pick, keep: proposal }),
      onSuccess: () => {
        (onSaved(), toast(msg("Paragraph replaced. “Edit history” brings the old text back.")), onClose());
      },
      onError: (err) => toast(errorMessage(err), `danger`),
    });
  return (
    <Modal
      open
      onOpenChange={(o) => !o && onClose()}
      title={msg("Rewrite one paragraph")}
      description={
        pick === null
          ? msg("Choose the paragraph to rewrite.")
          : msg("Say what to change (optional), then ask for a new version.")
      }
    >
      {pick === null ? (
        <div className="max-h-[60vh] space-y-1.5 overflow-y-auto">
          {parts.map((p, k) => (
            <button
              type="button"
              key={k}
              className="block w-full rounded-md border border-line px-2.5 py-1.5 text-left text-sm text-muted hover:border-accent/60 hover:text-fg"
              onClick={() => setPick(k)}
            >
              <span className="line-clamp-3">{p}</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          <p className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded-md border border-line bg-panel-2 p-2 text-sm text-muted">
            {parts[pick]}
          </p>
          <Textarea
            value={wish}
            onChange={(ev) => setWish(ev.target.value)}
            placeholder={msg("e.g. more tension, Lilia stays cold, shorter… (empty: just write it better)")}
            className="min-h-16 text-sm"
          />
          {proposal !== null && (
            <div>
              <p className="mb-1 text-xs font-semibold text-fg">{msg("New version")}</p>
              <Textarea
                value={proposal}
                onChange={(ev) => setProposal(ev.target.value)}
                className="min-h-32 font-serif text-[15px]"
              />
            </div>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => (setPick(null), setProposal(null))}
              disabled={ask.isPending || keep.isPending}
            >
              {msg("Another paragraph")}
            </Button>
            <Button
              size="sm"
              variant={proposal === null ? `primary` : `secondary`}
              loading={ask.isPending}
              disabled={keep.isPending}
              onClick={() => ask.mutate()}
              title={msg("Sends a new request; on a paid model it is billed again")}
            >
              <Icon.WandSparkles className="size-3.5" /> {proposal === null ? msg("Rewrite") : msg("Try again")}
            </Button>
            {proposal !== null && (
              <Button
                size="sm"
                variant="primary"
                loading={keep.isPending}
                disabled={ask.isPending || !proposal.trim()}
                onClick={() => keep.mutate()}
              >
                <Icon.Check className="size-3.5" /> {msg("Keep this version")}
              </Button>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}
