// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import * as React from "react";
import { useCommands, queryKeys, useContextPreview } from "@/api/queries";
import * as Icon from "lucide-react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { apiPost, apiGet } from "@/api/legacy";
import { msg, msgKey } from "@/i18n";
import {
  Badge,
  Button,
  Callout,
  IconButton,
  Kbd,
  Modal,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Spinner,
} from "@/components/ui";
import { cn, fmtK, uuid } from "@/lib/util";

var draftKey = (e, t) => `lsd:draft:${e}:${t ?? `main`}`;

function readDraft(e) {
  try {
    let t = localStorage.getItem(e);
    if (!t)
      return {
        text: ``,
        requestId: null,
      };
    let n = JSON.parse(t);
    return typeof n == `string`
      ? {
          text: n,
          requestId: null,
        }
      : {
          text: typeof n?.text == `string` ? n.text : ``,
          requestId: typeof n?.requestId == `string` ? n.requestId : null,
        };
  } catch {
    return {
      text: ``,
      requestId: null,
    };
  }
}

function writeDraft(e, t) {
  try {
    !t.text && !t.requestId ? localStorage.removeItem(e) : localStorage.setItem(e, JSON.stringify(t));
  } catch {}
}

function clearDraft(e) {
  try {
    localStorage.removeItem(e);
  } catch {}
}

export var Composer = React.forwardRef(function (
  { storyId, branchId, generating, disabled, enterToSend, onSend, onStop, onQuick, model },
  l,
) {
  let u = draftKey(storyId, branchId),
    [d, f] = React.useState(() => readDraft(u).text),
    p = React.useRef(
      (() => {
        let e = readDraft(u);
        return e.requestId
          ? {
              requestId: e.requestId,
              text: e.text,
            }
          : null;
      })(),
    ),
    g = (e) => {
      (f(e),
        p.current && p.current.text !== e && (p.current = null),
        writeDraft(u, {
          text: e,
          requestId: p.current?.requestId ?? null,
        }));
    },
    [_, v] = React.useState(null),
    [y, b] = React.useState(false),
    [x, S] = React.useState(null),
    C = React.useRef(null),
    commands = useCommands(storyId),
    [T, E] = React.useState(null),
    [D, O] = React.useState(null),
    ee = (e) => {
      (O(d),
        g(e),
        E(null),
        S(null),
        setTimeout(() => {
          (C.current?.focus(), C.current?.setSelectionRange(e.length, e.length));
        }, 0));
    };
  React.useImperativeHandle(l, () => ({
    offer: (e) => (d.trim() ? E(e) : ee(e)),
  }));
  let te = React.useMemo(() => {
    if (!x) return [];
    let e = x.query.toLowerCase();
    return (commands.data ?? [])
      .filter((e) => e.enabled)
      .filter(
        (t) =>
          !e ||
          t.name.includes(e) ||
          t.aliases_json.some((t) => t.includes(e)) ||
          t.description.toLowerCase().includes(e),
      )
      .sort(
        (t, n) => Number(n.name.startsWith(e)) - Number(t.name.startsWith(e)) || Number(n.pinned) - Number(t.pinned),
      )
      .slice(0, 60);
  }, [x, commands.data]);
  React.useEffect(() => {
    let e = C.current;
    e && ((e.style.height = `auto`), (e.style.height = Math.min(e.scrollHeight, 260) + `px`));
  }, [d]);
  let ne = (e) => {
      (g(e), O(null));
      let t = /^\/([\w-]*)$/.exec(
        e.split(`
`)[0],
      );
      !_ && t && !e.includes(` `)
        ? S({
            query: t[1],
            index: 0,
          })
        : S(null);
    },
    re = (e) => {
      (v(e), g((d.replace(/^\/[\w-]*\s?/, ``) || ``).trimStart()), S(null), setTimeout(() => C.current?.focus(), 0));
    },
    ie = async () => {
      if (y || generating || disabled || (!d.trim() && !_)) return;
      let e = _,
        t = d;
      if (!e) {
        let n = /^\/([\w-]+)(?:\s+([\s\S]*))?$/.exec(d.trim());
        if (n) {
          let r = (commands.data ?? []).find(
            (e) => e.enabled && (e.name === n[1].toLowerCase() || e.aliases_json.includes(n[1].toLowerCase())),
          );
          r && ((e = r), (t = n[2] ?? ``));
        }
      }
      (p.current && p.current.text === d) ||
        (p.current = {
          requestId: uuid(),
          text: d,
        });
      let i = p.current.requestId;
      (writeDraft(u, {
        text: d,
        requestId: i,
      }),
        b(true));
      try {
        (await onSend({
          content: t,
          command: e,
          requestId: i,
        })) && (clearDraft(u), (p.current = null), f(``), v(null), O(null), E(null));
      } finally {
        b(false);
      }
    };
  return (
    <div className="shrink-0 border-t border-line bg-bg/95 px-3 pb-3 pt-2 sm:px-6">
      <div className="story-column relative mx-auto">
        {T !== null && (
          <div
            role="group"
            aria-label={msg("Your message box already has text")}
            className="mb-1.5 flex flex-wrap items-center gap-1.5 rounded-md border border-line bg-panel px-2.5 py-1.5 text-xs text-muted"
            onKeyDown={(e) => e.key === `Escape` && E(null)}
          >
            <span className="min-w-0 flex-1">{msg("You already have text here. Use this suggestion?")}</span>
            <Button size="sm" variant="ghost" onClick={() => ee(T)}>
              {msg("Replace")}
            </Button>
            <Button size="sm" autoFocus onClick={() => ee(`${d.trimEnd()}\n\n${T}`)}>
              {msg("Add after")}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => E(null)}>
              {msg("Cancel")}
            </Button>
          </div>
        )}
        {D !== null && T === null && (
          <p className="mb-1 flex flex-wrap items-center gap-1.5 px-1 text-[11px] text-faint" role="status">
            {msg("Suggestion placed. Edit it, then send when you are ready.")}
            <button
              type="button"
              className="inline-flex items-center gap-1 rounded px-1 text-muted underline hover:text-fg"
              onClick={() => {
                (g(D), O(null), C.current?.focus());
              }}
            >
              <Icon.Undo2 className="size-3" /> {msg("Undo")}
            </button>
          </p>
        )}
        {x && (
          <div
            className="absolute bottom-full left-0 right-0 mb-2 max-h-80 overflow-y-auto rounded-lg border border-line bg-raised p-1 shadow-2xl"
            role="listbox"
            aria-label={msg("Commands")}
          >
            {te.length === 0 && (
              <p className="px-3 py-2 text-xs text-faint">
                {msg("No command matches “/")}
                {x.query}”.
              </p>
            )}
            {te.map((e, t) => (
              <button
                role="option"
                aria-selected={t === x.index}
                onMouseDown={(t) => {
                  (t.preventDefault(), re(e));
                }}
                onMouseEnter={() =>
                  S({
                    ...x,
                    index: t,
                  })
                }
                className={cn(
                  `flex w-full items-start gap-3 rounded-md px-2.5 py-1.5 text-left`,
                  t === x.index && `bg-panel-2`,
                )}
                key={e.id}
              >
                <span className="w-28 shrink-0 font-mono text-[13px] text-accent">/{e.name}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] text-fg/90">{e.description}</span>
                  <span className="text-[11px] text-faint">
                    {e.kind === `local_action`
                      ? msg("app action · no model call")
                      : e.kind === `hybrid`
                        ? msg("app tool + model")
                        : msg("prompt")}
                    {e.aliases_json.length > 0 &&
                      msg(" · also {{v0}}", {
                        v0: e.aliases_json.map((e) => `/` + e).join(` `),
                      })}
                    {e.scope === `story` && msg(" · this story")}
                  </span>
                </span>
              </button>
            ))}
          </div>
        )}
        <div
          className={cn(
            `rounded-xl border border-line bg-panel transition-colors focus-within:border-accent/70`,
            disabled && `opacity-60`,
          )}
        >
          {_ && (
            <div className="flex items-center gap-2 px-3 pt-2">
              <CommandChip storyId={storyId} cmd={_} input={d} onRemove={() => v(null)} />
            </div>
          )}
          <textarea
            ref={C}
            value={d}
            onChange={(e) => ne(e.target.value)}
            onKeyDown={(e) => {
              if (x && te.length) {
                if (e.key === `ArrowDown`) {
                  (e.preventDefault(),
                    S({
                      ...x,
                      index: (x.index + 1) % te.length,
                    }));
                  return;
                }
                if (e.key === `ArrowUp`) {
                  (e.preventDefault(),
                    S({
                      ...x,
                      index: (x.index - 1 + te.length) % te.length,
                    }));
                  return;
                }
                if (e.key === `Enter` || e.key === `Tab`) {
                  (e.preventDefault(), re(te[x.index]));
                  return;
                }
                if (e.key === `Escape`) {
                  S(null);
                  return;
                }
              }
              e.key === `Backspace` && _ && !d
                ? v(null)
                : e.key === `Enter` &&
                  !e.shiftKey &&
                  (enterToSend || e.ctrlKey || e.metaKey) &&
                  (e.preventDefault(), ie());
            }}
            rows={2}
            disabled={disabled}
            placeholder={
              _
                ? _.kind === `local_action`
                  ? msg("Optional text for this action…", {})
                  : msg("Add instructions or text (optional)…", {})
                : msg("What do you do? Type / for commands")
            }
            className="block max-h-64 w-full resize-none bg-transparent px-3.5 py-2.5 font-serif text-base leading-relaxed text-fg placeholder:font-sans placeholder:text-sm placeholder:text-faint focus:outline-none"
            id="story-composer"
            aria-label={msg("Message")}
          />

          <div className="flex items-center gap-1 px-2 pb-2">
            <IconButton label={msg("Recap the story (/recap)")} onClick={() => onQuick(`recap`)}>
              <Icon.ScrollText className="size-4" />
            </IconButton>
            <IconButton label={msg("Open Journal & Memory")} onClick={() => onQuick(`journal`)}>
              <Icon.BookBookmark className="size-4" />
            </IconButton>
            <span className="ml-1 hidden text-[11px] text-faint sm:inline">
              {enterToSend ? (
                <>
                  <Kbd>{msg("Enter")}</Kbd> {msg("send ·")} <Kbd>{msg("Shift")}</Kbd>+<Kbd>{msg("Enter")}</Kbd>{" "}
                  {msg("newline")}
                </>
              ) : (
                <>
                  <Kbd>{msg("Ctrl")}</Kbd>+<Kbd>{msg("Enter")}</Kbd> {msg("send")}
                </>
              )}
            </span>
            {model && (
              <span
                className={cn(
                  `ml-auto min-w-0 max-w-[45%] truncate text-[11px]`,
                  model.cloud ? `text-warn` : `text-faint`,
                )}
                title={
                  model.cloud
                    ? msg("Remote model: story content is sent over the internet to this provider.")
                    : msg("Local model: nothing leaves this computer.")
                }
                aria-label={msg("Model: {{v0}} — {{v1}} — {{v2}}", {
                  v0: model.cloud ? `Cloud` : `Local`,
                  v1: model.provider,
                  v2: model.name,
                })}
              >
                {model.cloud ? msg("Cloud") : msg("Local")}
                {" — "}
                {model.provider}
                {" — "}
                {model.name}
              </span>
            )}
            <div className={model ? `ml-2` : `ml-auto`}>
              {generating ? (
                <Button variant="secondary" size="sm" onClick={onStop}>
                  <Icon.Square className="size-3 fill-current" /> {msg("Stop")}
                </Button>
              ) : (
                <Button variant="primary" size="sm" onClick={ie} loading={y} disabled={disabled || (!d.trim() && !_)}>
                  <Icon.Send className="size-3.5" />{" "}
                  {y ? msg("Saving…") : _?.kind === `local_action` ? msg("Run") : msg("Send")}
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
});

function CommandChip({ storyId, cmd, input, onRemove }) {
  let [i, a] = React.useState(false),
    query = useQuery({
      queryKey: [`expand`, cmd.id, input, storyId],
      enabled: i,
      queryFn: () =>
        apiPost(`/commands/expand`, {
          command_id: cmd.id,
          input,
          story_id: storyId,
        }),
    });
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-accent-soft py-0.5 pl-2 pr-0.5 text-[13px] text-accent">
      <span className="font-mono">/{cmd.name}</span>
      <Badge className="ml-1 border-none bg-transparent px-0 text-[10px] text-accent/80">
        {cmd.kind === `local_action`
          ? msg("app action")
          : cmd.output_target === `ooc`
            ? msg("out of character")
            : cmd.output_target === `utility`
              ? `utility`
              : `prompt`}
      </Badge>
      <Popover open={i} onOpenChange={a}>
        <PopoverTrigger asChild>
          <IconButton label={msg("Preview what will be sent")} className="size-5 text-accent">
            <Icon.Eye className="size-3" />
          </IconButton>
        </PopoverTrigger>
        <PopoverContent className="w-[min(32rem,90vw)]" align="start">
          <p className="mb-1 text-xs font-medium">
            {query.data?.sends_to_model === false
              ? msg("This command runs inside the app (no model call).")
              : msg("Instructions sent to the model with your text:")}
          </p>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded border border-line bg-panel-2 p-2 text-[11px] text-muted">
            {query.isLoading ? `…` : query.data?.expansion}
          </pre>
          <p className="mt-1 text-[11px] text-faint">{msg("Hidden from the story text, included in the request.")}</p>
        </PopoverContent>
      </Popover>
      <IconButton label={msg("Remove command")} className="size-5 text-accent" onClick={onRemove}>
        <Icon.X className="size-3" />
      </IconButton>
    </span>
  );
}

export function ContextWarnings({ manifest, onClick }) {
  if (!manifest) return null;
  let n = Math.min(1, manifest.ratio),
    r =
      manifest.fixed_tokens !== undefined && manifest.budget_tokens > 0
        ? manifest.fixed_tokens / manifest.budget_tokens
        : n,
    i =
      manifest.hard_input_limit && manifest.total_tokens > manifest.hard_input_limit * 0.97
        ? `bg-danger`
        : r > 0.85 || manifest.trimmed_sections?.length
          ? `bg-warn`
          : `bg-accent`;
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 rounded-md px-2 py-1 text-xs text-muted hover:bg-panel-2"
      title={msg("Approximate context size (recent messages fill the remaining budget) — click to inspect")}
    >
      <span className="hidden sm:inline">
        ≈{fmtK(manifest.total_tokens)}
        {" / "}
        {fmtK(manifest.budget_tokens)}
      </span>
      <span className="h-1.5 w-14 overflow-hidden rounded-full bg-line" aria-hidden>
        <span
          className={cn(`block h-full`, i)}
          style={{
            width: `${n * 100}%`,
          }}
        />
      </span>
      {manifest.warnings.length > 0 && (
        <span className="size-1.5 rounded-full bg-warn" aria-label={msg("Context warnings")} />
      )}
    </button>
  );
}

export function ContextManifest({ manifest, storyId, exclusions }) {
  let queryClient = useQueryClient(),
    mutation = useMutation({
      mutationFn: (e) => apiPost(`/stories/${storyId}/context/exclusions`, e),
      onSuccess: () => {
        (queryClient.invalidateQueries({
          queryKey: queryKeys.context(storyId),
        }),
          queryClient.invalidateQueries({
            queryKey: queryKeys.story(storyId),
          }));
      },
    }),
    a = new Set(exclusions ?? []),
    o = (e, t) => (t && [`lore`, `fact`, `event`, `canon`].includes(e) ? `${e}:${t}` : null);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <span>
          ≈{manifest.total_tokens.toLocaleString()} {msg("tokens of a")} {manifest.budget_tokens.toLocaleString()}{" "}
          {msg("budget (")}
          {manifest.reserved_output_tokens} {msg("reserved for the reply)")}
        </span>
        <Badge>{msg("approximate (chars ÷ 4)")}</Badge>
      </div>
      {manifest.warnings.map((e, t) => (
        <Callout tone="warn" key={t}>
          {e}
        </Callout>
      ))}
      <p className="text-xs text-faint">
        {msg("Largest:")}{" "}
        {[...manifest.sections]
          .sort((e, t) => t.tokens - e.tokens)
          .slice(0, 3)
          .map((e) => `${e.title.split(` (`)[0]} ≈${fmtK(e.tokens)}`)
          .join(` · `)}
        {manifest.omitted_messages > 0 &&
          msg(" · {{v0}} older message(s) left out", {
            v0: manifest.omitted_messages,
          })}
      </p>
      {manifest.fixed_tokens !== undefined && (
        <p className="text-xs text-muted">
          {msg("Instructions, notes, lore and memories ≈")}
          {fmtK(manifest.fixed_tokens)} {msg("· recent messages ≈")}
          {fmtK(manifest.message_tokens ?? 0)} {msg("(they fill whatever is left, so a nearly full budget is normal)")}
          {manifest.trimmed_sections?.length
            ? msg(" · left out this turn: {{v0}}", {
                v0: manifest.trimmed_sections.join(`, `),
              })
            : ``}
        </p>
      )}
      <p className="text-xs text-faint">
        {manifest.effective_window
          ? msg("Model window ≈{{v0}}{{v1}}; this request is planned to stay below ≈{{v2}} input tokens. ", {
              v0: fmtK(manifest.effective_window),
              v1: manifest.reply_max_tokens ? ` (reply up to ${fmtK(manifest.reply_max_tokens)})` : ``,
              v2: fmtK(manifest.hard_input_limit ?? 0),
            })
          : manifest.model_context_limit
            ? msg("Model window ≈{{v0}} (the budget never exceeds it). ", {
                v0: fmtK(manifest.model_context_limit),
              })
            : ``}
        {manifest.analysis_output_budget
          ? msg("Scene analysis is a separate request (up to {{v0}} output tokens) and does not use this budget.", {
              v0: manifest.analysis_output_budget.toLocaleString(),
            })
          : ``}
      </p>
      <p className="text-xs text-faint">
        {msg("Precedence:")} {manifest.precedence}
      </p>
      {manifest.strategy && (
        <p className="text-xs text-faint">
          {msg("Trimming order:")} {manifest.strategy}
        </p>
      )}
      {manifest.prompt_profile && (
        <p className="text-xs text-faint">
          {msg("Player-agency prompt profile:")} {manifest.prompt_profile}
        </p>
      )}
      {manifest.sections.map((e) => (
        <details
          className="rounded-md border border-line bg-panel-2/40"
          open={e.key !== `messages` && e.items.length < 8}
          key={e.key}
        >
          <summary className="flex cursor-pointer items-center justify-between gap-2 px-3 py-2 text-sm">
            <span className="font-medium">{e.title}</span>
            <span className="text-xs text-faint">
              ≈{fmtK(e.tokens)}
              {" · "}
              {e.items.length} {msg("item(s)")}
            </span>
          </summary>
          <ul className="space-y-0.5 px-3 pb-2">
            {e.items.map((e, n) => {
              let r = o(e.type, e.id),
                s = r ? a.has(r) : false;
              return (
                <li
                  className={cn(`flex items-center gap-2 text-xs`, e.included === false && `text-faint line-through`)}
                  key={n}
                >
                  <Badge>{msgKey(e.type)}</Badge>
                  <span className="min-w-0 flex-1 truncate">{e.label}</span>
                  {e.canon_status && e.canon_status !== `recurring_reference` && (
                    <Badge tone="warn">{e.canon_status}</Badge>
                  )}
                  {e.confidence && e.confidence !== `high` && (
                    <Badge tone="warn">{msg("{{v0}} confidence", { v0: msgKey(e.confidence) })}</Badge>
                  )}
                  {e.reason && <span className="text-faint">({e.reason})</span>}
                  {storyId && r && (
                    <button
                      className="text-faint hover:text-fg"
                      title={s ? msg("Include again") : msg("Exclude from context")}
                      onClick={() =>
                        mutation.mutate({
                          key: r,
                          excluded: !s,
                        })
                      }
                    >
                      {s ? <Icon.EyeOff className="size-3.5" /> : <Icon.Eye className="size-3.5" />}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </details>
      ))}
    </div>
  );
}

export function ContextInspector({ storyId, open, onClose, exclusions }) {
  let contextPreview = useContextPreview(storyId, open),
    [a, o] = React.useState(false),
    query = useQuery({
      queryKey: [`context-full`, storyId],
      enabled: open && a,
      queryFn: () => apiGet(`/stories/${storyId}/context?full=true`),
    });
  return (
    <Modal
      open={open}
      onOpenChange={(e) => !e && onClose()}
      size="lg"
      title={msg("Context sent to model")}
      description={msg(
        "What the next request will contain. Excluded items stay in your records; they are just not sent.",
      )}
    >
      {contextPreview.isLoading && <Spinner />}
      {contextPreview.data && (
        <>
          {contextPreview.data.model && (
            <p className="mb-3 text-xs text-muted">
              {msg("Next request goes to")} <b>{contextPreview.data.model.model_id}</b> {msg("via")}{" "}
              {contextPreview.data.model.provider}{" "}
              {contextPreview.data.model.is_cloud ? (
                <Badge tone="warn">{msg("cloud")}</Badge>
              ) : (
                <Badge tone="ok">{msg("local")}</Badge>
              )}
            </p>
          )}
          <ContextManifest manifest={contextPreview.data.manifest} storyId={storyId} exclusions={exclusions} />
          <div className="mt-4">
            <Button size="sm" onClick={() => o(!a)}>
              {a ? msg("Hide") : msg("Show")} {msg("full prompt text")}
            </Button>
            {a && query.data && (
              <div className="mt-2 space-y-2">
                <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-md border border-line bg-panel-2 p-3 text-[11px] text-muted">
                  {query.data.system}
                </pre>
                {query.data.messages.map((e, t) => (
                  <pre className="whitespace-pre-wrap rounded-md border border-line p-2 text-[11px] text-muted" key={t}>
                    <b>{e.role}:</b> {e.content}
                  </pre>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </Modal>
  );
}
