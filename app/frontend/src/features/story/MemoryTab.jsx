// "AI memory" tab of the Journal (v1.8 phase 7.4): what the narrator remembers of the story (services/summaries.py):
// the story so far, chapters and scenes (editable, can be pinned as a memory), open threads (settle / reopen),
// what each character remembers, and two buttons: summarise now, close the chapter here.
import * as React from "react";
import * as Icon from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPatch, apiPost, errorMessage } from "@/api/legacy";
import { msg } from "@/i18n";
import { Badge, Button, Callout, EmptyState, ErrorCallout, Input, SectionTitle, Spinner, Textarea, useUi } from "@/components/ui";

function levelLabel(l) {
  return l === `story` ? msg("Story so far") : l === `chapter` ? msg("Chapter") : msg("Scene");
}

export function memoryKey(storyId) {
  return [`memory`, storyId];
}

/** Close the current chapter now (also the /chapter command). */
export function useCloseChapter(storyId) {
  let queryClient = useQueryClient(),
    { toast } = useUi();
  return useMutation({
    mutationFn: (title) => apiPost(`/stories/${storyId}/memory/summarise`, { chapter: true, title: title || `` }),
    onSuccess: (r) => {
      queryClient.setQueryData(memoryKey(storyId), r.memory);
      toast(r.merged ? msg("Chapter closed: the AI's memory is up to date.") : msg("Nothing new to put in a chapter."));
    },
    onError: (e) => toast(errorMessage(e), `danger`),
  });
}

function Layer({ storyId, row, onSaved }) {
  let { toast } = useUi(),
    [editing, setEditing] = React.useState(false),
    [text, setText] = React.useState(row.content),
    [busy, setBusy] = React.useState(false);
  async function save() {
    setBusy(true);
    try {
      onSaved(await apiPatch(`/stories/${storyId}/memory/${row.id}`, { content: text }));
      setEditing(false);
    } catch (e) {
      toast(errorMessage(e), `danger`);
    } finally {
      setBusy(false);
    }
  }
  async function pin() {
    try {
      await apiPost(`/stories/${storyId}/facts`, {
        content: row.content,
        category: `memory`,
        fact_kind: `established`,
        pinned: true,
        importance: 4,
      });
      toast(msg("Pinned: it is now a permanent memory (Memories & facts tab)."));
    } catch (e) {
      toast(errorMessage(e), `danger`);
    }
  }
  return (
    <li className="rounded-lg border border-line bg-panel p-3">
      <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-faint">
        <Badge tone={row.level === `scene` ? `neutral` : `accent`}>{levelLabel(row.level)}</Badge>
        {row.title && <span className="font-medium text-fg">“{row.title}”</span>}
        <span>
          {msg("messages #{{v0}}–#{{v1}}", { v0: row.start_seq, v1: row.end_seq })}
          {row.parts ? ` · ${msg("{{v0}} part(s)", { v0: row.parts })}` : ``}
        </span>
        {row.source === `edited` && <Badge>{msg("edited")}</Badge>}
        <span className="ml-auto flex gap-1">
          {!editing && (
            <>
              <Button size="sm" variant="ghost" onClick={() => setEditing(true)} title={msg("Correct this summary")}>
                <Icon.Pencil className="size-3.5" />
              </Button>
              <Button size="sm" variant="ghost" onClick={pin} title={msg("Pin as a permanent memory")}>
                <Icon.Pin className="size-3.5" />
              </Button>
            </>
          )}
        </span>
      </div>
      {editing ? (
        <div className="space-y-2">
          <Textarea value={text} onChange={(e) => setText(e.target.value)} className="min-h-28 text-sm" />
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => (setText(row.content), setEditing(false))}>
              {msg("Cancel")}
            </Button>
            <Button size="sm" variant="primary" loading={busy} onClick={save} disabled={!text.trim()}>
              {msg("Save")}
            </Button>
          </div>
        </div>
      ) : (
        <p className="text-sm leading-relaxed">{row.content}</p>
      )}
    </li>
  );
}

export function MemoryTab({ storyId }) {
  let queryClient = useQueryClient(),
    { toast } = useUi(),
    query = useQuery({ queryKey: memoryKey(storyId), queryFn: () => apiGet(`/stories/${storyId}/memory`) }),
    set = (data) => queryClient.setQueryData(memoryKey(storyId), data),
    [title, setTitle] = React.useState(``),
    closeChapter = useCloseChapter(storyId),
    summarise = useMutation({
      mutationFn: () => apiPost(`/stories/${storyId}/memory/summarise`, {}),
      onSuccess: (r) => {
        set(r.memory);
        toast(
          r.written || r.merged
            ? msg("{{v0}} summary(ies) written.", { v0: r.written + r.merged })
            : msg("Nothing to summarise right now."),
        );
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    });

  async function thread(key, close) {
    try {
      set(await apiPost(`/stories/${storyId}/memory/threads/${close ? `close` : `reopen`}`, { key }));
    } catch (e) {
      toast(errorMessage(e), `danger`);
    }
  }

  if (query.isLoading) return <Spinner />;
  if (query.isError) return <ErrorCallout error={query.error} onRetry={() => query.refetch()} />;
  let m = query.data;
  return (
    <div className="max-w-3xl space-y-6">
      <Callout tone="info">
        {msg(
          "What the narrator remembers of the messages it no longer reads word for word. Written automatically while you play (in English, the language the AI understands best). You can correct a summary, pin it as a permanent memory, or settle a thread.",
        )}
      </Callout>
      {!m.enabled && (
        <Callout tone="warn">{msg("Automatic summaries are off (Settings > Memory capture).")}</Callout>
      )}
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted">
          {msg("{{v0}} of {{v1}} messages summarised", { v0: m.summarised_messages, v1: m.messages })}
        </span>
        <span className="ml-auto flex flex-wrap gap-2">
          <Button size="sm" loading={summarise.isPending} disabled={!m.pending_messages} onClick={() => summarise.mutate()}>
            <Icon.ScrollText className="size-3.5" /> {msg("Summarise now")}
          </Button>
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-panel p-3">
        <Icon.BookMarked className="size-4 text-accent" />
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={msg("Chapter title (optional)")}
          className="min-w-40 flex-1"
          maxLength={120}
        />
        <Button
          size="sm"
          variant="primary"
          loading={closeChapter.isPending}
          onClick={() => closeChapter.mutate(title, { onSuccess: () => setTitle(``) })}
        >
          {msg("Close the chapter here")}
        </Button>
      </div>

      <section>
        <SectionTitle>{msg("Story memory")}</SectionTitle>
        {m.layers.length === 0 ? (
          <EmptyState icon={<Icon.BookOpen className="size-6" />} title={msg("No summary yet")}>
            {msg("The first summaries are written after a few turns.")}
          </EmptyState>
        ) : (
          <ul className="space-y-2">
            {m.layers.map((r) => (
              <Layer key={r.id} storyId={storyId} row={r} onSaved={set} />
            ))}
          </ul>
        )}
      </section>

      <section>
        <SectionTitle>{msg("Open threads")}</SectionTitle>
        {m.threads.length === 0 ? (
          <p className="text-sm text-faint">{msg("No promise, quest or mystery pending.")}</p>
        ) : (
          <ul className="divide-y divide-line rounded-lg border border-line bg-panel">
            {m.threads.map((t) => (
              <li key={t.key} className="flex items-center gap-3 px-3 py-2 text-sm">
                <Icon.CircleDot className="size-3.5 shrink-0 text-accent" />
                <span className="flex-1">{t.text}</span>
                <span className="text-xs text-faint">#{t.seq}</span>
                <Button size="sm" variant="ghost" onClick={() => thread(t.key, true)}>
                  <Icon.Check className="size-3.5" /> {msg("Settled")}
                </Button>
              </li>
            ))}
          </ul>
        )}
        {m.closed_threads.length > 0 && (
          <details className="mt-2 text-sm">
            <summary className="cursor-pointer text-faint">
              {msg("Settled by you ({{v0}})", { v0: m.closed_threads.length })}
            </summary>
            <ul className="mt-1 space-y-1">
              {m.closed_threads.map((t) => (
                <li key={t.key} className="flex items-center gap-2 text-muted">
                  <span className="flex-1 line-through">{t.text}</span>
                  <Button size="sm" variant="ghost" onClick={() => thread(t.key, false)}>
                    {msg("Reopen")}
                  </Button>
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>

      <section>
        <SectionTitle>{msg("What the characters remember")}</SectionTitle>
        {m.characters.length === 0 ? (
          <p className="text-sm text-faint">{msg("Nothing yet.")}</p>
        ) : (
          <ul className="space-y-2">
            {m.characters.map((c) => (
              <li key={c.name} className="rounded-lg border border-line bg-panel p-3 text-sm">
                <p className="mb-1 font-medium">{c.name}</p>
                <ul className="space-y-0.5 text-muted">
                  {c.lines.map((l) => (
                    <li key={l}>{l}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
