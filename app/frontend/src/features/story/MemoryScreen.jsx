// The "Memory" screen (26 Nov 2026, OOC.AI as the model), opened from the play screen's side menu. What the narrator
// remembers, in four tabs the player can read and correct; every change reaches the AI on the next turn:
//   Long-term   chapter / whole-story summaries (services/summaries.py) + memories pinned by the player (facts)
//   Short-term  the latest scene summaries, not merged into a chapter yet
//   Relations   the relationship gauges and their memories (panels/RelationsPanel)
//   Goals       open threads found by the AI + quests, goals, promises, mysteries, clues (panels/ItemsQuests)
// The full journal (timeline, review, maintenance...) stays one touch away: "Advanced options".
import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Icon from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPatch, apiPost, errorMessage } from "@/api/legacy";
import { msg } from "@/i18n";
import { Button, IconButton, Spinner, Textarea, useUi } from "@/components/ui";
import { cn } from "@/lib/util";
import { memoryKey } from "@/features/story/MemoryTab";
import { QuestsPanel } from "@/features/story/panels/ItemsQuests";
import { RelationsPanel } from "@/features/story/panels/RelationsPanel";

const TABS = [
  [`long`, () => msg("Long-term")],
  [`short`, () => msg("Short-term")],
  [`relations`, () => msg("Relationships")],
  [`goals`, () => msg("Goals")],
];

export function MemoryScreen({ storyId, worldId, onClose, onAdvanced }) {
  let [tab, setTab] = React.useState(`long`),
    [adding, setAdding] = React.useState(false),
    queryClient = useQueryClient(),
    memory = useQuery({ queryKey: memoryKey(storyId), queryFn: () => apiGet(`/stories/${storyId}/memory`) }),
    facts = useQuery({ queryKey: [`memory-pinned`, storyId], queryFn: () => apiGet(`/stories/${storyId}/facts`) }),
    layers = memory.data?.layers ?? [],
    long = layers.filter((r) => r.level !== `scene`).sort((a, b) => b.end_seq - a.end_seq),
    short = layers.filter((r) => r.level === `scene` && !r.merged).sort((a, b) => b.end_seq - a.end_seq),
    pinned = (facts.data?.facts ?? []).filter((f) => f.pinned && f.status !== `superseded`),
    refresh = () => {
      queryClient.invalidateQueries({ queryKey: memoryKey(storyId) });
      queryClient.invalidateQueries({ queryKey: [`memory-pinned`, storyId] });
    },
    counts = { long: long.length + pinned.length, short: short.length };
  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/55" />
        <Dialog.Content
          aria-describedby={undefined}
          className="sc-memory fixed inset-0 z-50 flex flex-col bg-bg md:inset-x-auto md:left-1/2 md:top-[4vh] md:h-[92vh] md:w-[min(48rem,96vw)] md:-translate-x-1/2 md:rounded-2xl md:border md:border-line"
        >
          <div className="flex shrink-0 items-center gap-2 px-3 pt-2">
            <Dialog.Title className="text-[18px] font-semibold">{msg("Memory")}</Dialog.Title>
            <Dialog.Close asChild>
              <IconButton label={msg("Close")} className="ml-auto size-10">
                <Icon.X className="size-5" />
              </IconButton>
            </Dialog.Close>
          </div>
          <div className="flex shrink-0 gap-2 overflow-x-auto border-b border-line px-3 pb-3 pt-2" role="tablist">
            {TABS.map(([id, label]) => (
              <button
                key={id}
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className={cn(`sc-memory-tab`, tab === id && `sc-memory-tab-on`)}
              >
                {label()}
                {counts[id] != null && <span className="opacity-70"> {counts[id]}</span>}
              </button>
            ))}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-24 pt-2">
            {memory.isLoading && <Spinner />}
            {memory.isError && <p className="text-sm text-danger">{errorMessage(memory.error)}</p>}

            {tab === `long` && (
              <>
                <p className="sc-memory-hint">
                  {msg("What the AI keeps for the whole story: summaries of past chapters and the memories you pinned.")}
                </p>
                {adding && <NewMemory storyId={storyId} onDone={() => (setAdding(false), refresh())} />}
                {pinned.length > 0 && <p className="sc-menu-head">{msg("Pinned memories")}</p>}
                {pinned.map((f) => (
                  <FactItem key={f.id} storyId={storyId} fact={f} onChanged={refresh} />
                ))}
                {long.length > 0 && <p className="sc-menu-head">{msg("Chapters")}</p>}
                {long.map((r) => (
                  <SummaryItem key={r.id} storyId={storyId} row={r} onChanged={refresh} />
                ))}
                {!memory.isLoading && counts.long === 0 && !adding && (
                  <Empty>{msg("Nothing yet: chapters are summarised as the story goes on. You can pin a memory with +.")}</Empty>
                )}
              </>
            )}

            {tab === `short` && (
              <>
                <p className="sc-memory-hint">{msg("Summaries of the latest scenes. Older ones are merged into chapters.")}</p>
                {short.map((r) => (
                  <SummaryItem key={r.id} storyId={storyId} row={r} onChanged={refresh} />
                ))}
                {!memory.isLoading && short.length === 0 && (
                  <Empty>{msg("Nothing yet: scenes are summarised every few messages.")}</Empty>
                )}
              </>
            )}

            {tab === `relations` && <RelationsPanel storyId={storyId} worldId={worldId} onOpenCharacter={() => {}} />}

            {tab === `goals` && (
              <>
                {(memory.data?.threads ?? []).length > 0 && (
                  <>
                    <p className="sc-menu-head">{msg("Open threads found by the AI")}</p>
                    {memory.data.threads.map((t) => (
                      <ThreadItem key={t.key} storyId={storyId} thread={t} onChanged={refresh} />
                    ))}
                  </>
                )}
                <div className="mt-3">
                  <QuestsPanel storyId={storyId} />
                </div>
              </>
            )}
          </div>

          {tab === `long` && !adding && (
            <button type="button" onClick={() => setAdding(true)} aria-label={msg("Pin a memory")} className="sc-memory-fab">
              <Icon.Plus className="size-6" />
            </button>
          )}
          <div className="shrink-0 border-t border-line px-3 py-2">
            <button type="button" onClick={onAdvanced} className="mx-auto flex items-center gap-1.5 py-1.5 text-sm text-muted">
              <Icon.Settings className="size-4" /> {msg("Advanced options")} · {msg("Full journal")}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Empty({ children }) {
  return <p className="px-2 py-10 text-center text-sm text-faint">{children}</p>;
}

// One memory, OOC style: a title that opens it, then the text and round buttons (edit, lock / delete).
function Item({ title, badge, content, onSave, actions }) {
  let [open, setOpen] = React.useState(false),
    [editing, setEditing] = React.useState(false),
    [draft, setDraft] = React.useState(content),
    [busy, setBusy] = React.useState(false),
    { toast } = useUi();
  return (
    <div className="border-b border-line">
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 py-3.5 text-left" aria-expanded={open}>
        <span className="min-w-0 flex-1 truncate text-[16px] font-medium">{title}</span>
        {badge}
        <Icon.ChevronDown className={cn(`size-5 shrink-0 text-faint transition-transform`, open && `rotate-180`)} />
      </button>
      {open && (
        <div className="pb-4">
          {editing ? (
            <>
              <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={7} autoFocus />
              <div className="mt-2 flex justify-end gap-2">
                <Button size="sm" variant="ghost" onClick={() => (setEditing(false), setDraft(content))}>
                  {msg("Cancel")}
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  loading={busy}
                  disabled={!draft.trim()}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      await onSave(draft.trim());
                      setEditing(false);
                    } catch (e) {
                      toast(errorMessage(e), `danger`);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  <Icon.Check className="size-3.5" /> {msg("Save")}
                </Button>
              </div>
            </>
          ) : (
            <>
              <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-muted">{content}</p>
              <div className="mt-3 flex gap-2.5">
                <RoundButton label={msg("Edit")} onClick={() => setEditing(true)}>
                  <Icon.Pencil className="size-4" />
                </RoundButton>
                {actions}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function RoundButton({ label, onClick, children, active }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={cn(`flex size-10 items-center justify-center rounded-full border text-muted`, active ? `border-accent text-accent` : `border-line`)}
    >
      {children}
    </button>
  );
}

function SummaryItem({ storyId, row, onChanged }) {
  let { toast } = useUi(),
    title = row.title || (row.level === `story` ? msg("The story so far") : msg("Messages {{v0}}–{{v1}}", { v0: row.start_seq, v1: row.end_seq }));
  return (
    <Item
      title={title}
      badge={row.locked ? <Icon.Lock className="size-3.5 shrink-0 text-accent" aria-label={msg("locked")} /> : null}
      content={row.content}
      onSave={async (text) => (await apiPatch(`/stories/${storyId}/memory/${row.id}`, { content: text }), onChanged())}
      actions={
        <RoundButton
          label={row.locked ? msg("Unlock: the AI may write it again") : msg("Lock: never written again automatically")}
          active={row.locked}
          onClick={async () => {
            try {
              await apiPost(`/stories/${storyId}/memory/${row.id}/lock`, { locked: !row.locked });
              onChanged();
            } catch (e) {
              toast(errorMessage(e), `danger`);
            }
          }}
        >
          {row.locked ? <Icon.Lock className="size-4" /> : <Icon.LockOpen className="size-4" />}
        </RoundButton>
      }
    />
  );
}

function FactItem({ storyId, fact, onChanged }) {
  let { toast, confirm } = useUi();
  return (
    <Item
      title={fact.content.split(`\n`)[0].slice(0, 80)}
      badge={<Icon.Pin className="size-3.5 shrink-0 text-accent" aria-hidden />}
      content={fact.content}
      onSave={async (text) => (await apiPatch(`/stories/${storyId}/facts/${fact.id}`, { content: text }), onChanged())}
      actions={
        <RoundButton
          label={msg("Delete")}
          onClick={async () => {
            if (!(await confirm({ title: msg("Delete this memory?"), danger: true, confirmLabel: msg("Delete") }))) return;
            try {
              await apiDelete(`/stories/${storyId}/facts/${fact.id}`);
              onChanged();
            } catch (e) {
              toast(errorMessage(e), `danger`);
            }
          }}
        >
          <Icon.Trash2 className="size-4" />
        </RoundButton>
      }
    />
  );
}

function NewMemory({ storyId, onDone }) {
  let [text, setText] = React.useState(``),
    [busy, setBusy] = React.useState(false),
    { toast } = useUi();
  return (
    <div className="sc-av-card mb-3 mt-1">
      <p className="sc-av-label">{msg("New pinned memory")}</p>
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        autoFocus
        placeholder={msg("Something the AI must never forget, e.g. “Kai promised Isabel to train with her every evening.”")}
        className="mt-2"
      />
      <div className="mt-2 flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onDone}>
          {msg("Cancel")}
        </Button>
        <Button
          size="sm"
          variant="primary"
          loading={busy}
          disabled={!text.trim()}
          onClick={async () => {
            setBusy(true);
            try {
              await apiPost(`/stories/${storyId}/facts`, { content: text.trim(), pinned: true, importance: 5 });
              onDone();
            } catch (e) {
              toast(errorMessage(e), `danger`);
              setBusy(false);
            }
          }}
        >
          <Icon.Pin className="size-3.5" /> {msg("Pin")}
        </Button>
      </div>
    </div>
  );
}

function ThreadItem({ storyId, thread, onChanged }) {
  let { toast } = useUi();
  return (
    <div className="flex items-start gap-3 border-b border-line py-3">
      <p className="min-w-0 flex-1 text-[15px]">{thread.text}</p>
      <Button
        size="sm"
        onClick={async () => {
          try {
            await apiPost(`/stories/${storyId}/memory/threads/close`, { key: thread.key });
            onChanged();
          } catch (e) {
            toast(errorMessage(e), `danger`);
          }
        }}
      >
        <Icon.Check className="size-3.5" /> {msg("Done")}
      </Button>
    </div>
  );
}
