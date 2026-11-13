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

function speakerColorIndex(e) {
  let t = 0;
  for (let n = 0; n < e.length; n++) t = (t * 31 + e.charCodeAt(n)) >>> 0;
  return t % 6;
}

function BeatPortrait({ b }) {
  let t = EXPRESSIONS[b.expression - 1],
    n = b.beat === `speaking`;
  return (
    <figure className="story-beat" aria-label={`${b.name}, ${t?.short ?? `Neutral`}, ${n ? `speaking` : `reacting`}`}>
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
          {n ? `speaks` : `reacts`}
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
  if (dialogueStyle === `emphasis`) for (let e of presentation?.paragraphs ?? []) f.set(e.paragraph, e);
  let p = dialogueStyle === `emphasis` ? `full` : `verified`;
  if (!d.length && !f.size)
    return <StoryMarkdown text={text} className={className} dialogue={u} reading={p} streaming={streaming} />;
  let g = text.split(/\n\s*\n/).filter((e) => e.trim()),
    _ = new Set(),
    v = new Map(),
    y = [];
  for (let e of d) {
    if (_.has(e.character_id)) continue;
    _.add(e.character_id);
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
          i = r === `protagonist` ? protagonist || `You` : (n?.name ?? null),
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
    re = settings.data?.dialogue_style ?? `emphasis`,
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
          toast(se ? `Message edited. Regenerate the reply to use the new text.` : `Message edited`));
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
      className={cn(
        `story-column group relative mx-auto w-full scroll-mt-24 py-3`,
        ue && `opacity-50`,
        highlight && `rounded-md ring-2 ring-accent/60`,
      )}
      aria-label={msg("{{v0}}, message {{v1}}", {
        v0: se ? `You` : ce ? `Out of character` : `Narrator`,
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
          se && !ie && `ml-auto w-fit max-w-[90%] min-w-0 rounded-lg border border-line bg-user px-3.5 py-2.5`,
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
              presentation={ae === `streaming` ? undefined : e.presentation}
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
      {!se && (ae !== `complete` || fe) && ae !== `streaming` && (
        <div
          className={cn(
            `mt-2 flex flex-wrap items-center gap-2 rounded-md px-2.5 py-1.5 text-xs`,
            ae === `failed` ? `bg-danger-soft text-danger` : `bg-warn-soft text-warn`,
          )}
          role="status"
        >
          <Icon.CircleAlert className="size-3.5" />
          <span>
            {ae === `cancelled` && msg("Stopped — the text so far was kept.")}
            {ae === `partial` && msg("Incomplete response — the text received so far was kept.")}
            {ae === `failed` && msg("Generation failed.")} {fe?.message}
            {typeof pe == `number` &&
              msg(" This attempt cost ${{v0}}.", {
                v0: pe.toFixed(4),
              })}
          </span>
          {!busy && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onRegenerate(e.id)}
              title={msg("Sends a new request; on a paid model it is billed again")}
            >
              <Icon.RefreshCw className="size-3" /> {msg("Retry")}
            </Button>
          )}
        </div>
      )}
      <div className={cn(`mt-1 flex min-h-6 items-center gap-1 text-[11px] text-faint`, se && `justify-end`)}>
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
            className="opacity-0 group-hover:opacity-100"
            title={msg(
              "Cost of this reply as reported by OpenRouter. Scene analysis and memory capture are separate requests.",
            )}
          >
            · ${pe.toFixed(4)}
          </span>
        ) : null}
        {e.edited_at && <span>{msg("· edited")}</span>}
        <span className="opacity-0 group-hover:opacity-100">
          · #{e.seq}
          {" · "}
          {timeAgo(e.created_at)}
        </span>
        <div
          className={cn(
            `flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100`,
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
        </div>
      </div>
      {te && me && <DiagnosticsTable d={me} />}
      {w && <VersionsDialog storyId={storyId} m={e} onClose={() => T(false)} onRestored={onChanged} />}
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
    [`Model`, d.model],
    [`Route`, d.provider],
    [`Generation`, d.generation_id],
    [`Ended with`, d.finish_reason],
    [`Provider's reason`, d.native_finish_reason],
    [`Reasoning`, d.reasoning],
    [`Output limit`, d.max_tokens],
    [`Input tokens`, d.input_tokens],
    [`Output tokens`, d.output_tokens],
    [`Hidden reasoning tokens`, d.reasoning_tokens],
    [`Visible tokens`, d.visible_tokens],
    [`First text after (s)`, d.first_text_s],
    [`Total time (s)`, d.duration_s],
    [`Characters saved`, d.chars],
    [`Error`, d.error],
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
              a = EXPRESSIONS[n.expression - 1];
            return (
              <li key={n.character_id}>
                <button
                  onClick={() => onOpenCharacter(n.character_id)}
                  title={`${n.name} — ${a?.name ?? `Neutral`}${n.evidence ? ` (“${n.evidence}”)` : ``}`}
                  aria-label={`${r + 1}. ${n.name}, ${a?.short ?? `Neutral`}${i ? `, speaking` : ``}`}
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
            let n = EXPRESSIONS[e.expression - 1];
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

function analysisKey({ text }) {
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
      className="story-column mx-auto mb-4 mt-1 rounded-lg border border-line bg-panel/50 p-2.5"
    >
      <div className="mb-1.5 flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-faint">
        <Icon.Sparkles className="size-3" /> {msg("What do you do next?")}
        <span className="normal-case tracking-normal">
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
                      <analysisKey text={e.label} />
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
