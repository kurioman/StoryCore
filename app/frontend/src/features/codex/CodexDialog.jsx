// Codex (v0.5): the in-story encyclopedia, opened from the play screen's header. Characters and places the protagonist
// has discovered on this branch; the others are locked "???" cards (no name, no spoiler). Data: GET /stories/:id/codex
// (backend services/codex.py). Only public lore: narrator-only notes never reach this screen.
import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Icon from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/legacy";
import { msg } from "@/i18n";
import { ErrorCallout, Portrait, Spinner } from "@/components/ui";
import { cn } from "@/lib/util";

var STATUS = {
    rumored: { label: msg("Heard of", {}), tone: `sc-cx-badge-rumor` },
    encountered: { label: msg("Met", {}), tone: `sc-cx-badge-met` },
    known: { label: msg("Known", {}), tone: `sc-cx-badge-known` },
    visited: { label: msg("Visited", {}), tone: `sc-cx-badge-met` },
  },
  FIELD_LABELS = {
    type: msg("Role", {}),
    title: msg("Title", {}),
    race: msg("Race", {}),
    affiliation: msg("Affiliation", {}),
    rank: msg("Rank", {}),
    occupation: msg("Occupation", {}),
    department: msg("Department", {}),
    year: msg("Year", {}),
    age: msg("Age", {}),
    appearance: msg("Appearance", {}),
    personality_traits: msg("Personality", {}),
    speech: msg("Way of speaking", {}),
    likes: msg("Likes", {}),
    dislikes: msg("Dislikes", {}),
    hobbies: msg("Hobbies", {}),
    location: msg("Located in", {}),
    region: msg("Region", {}),
    map_hint: msg("On the map", {}),
  };

function fieldValue(v) {
  if (Array.isArray(v)) return v.join(`, `);
  if (v && typeof v === `object`)
    return Object.entries(v)
      .map(([k, x]) => `${k.replace(/_/g, ` `)}: ${x}`)
      .join(` · `);
  return String(v);
}

export function CodexButton({ storyId, compact }) {
  let [open, setOpen] = React.useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="sc-cx-open flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium"
        title={msg("Codex: the characters and places you have discovered")}
      >
        <Icon.BookOpenText className="size-3.5" /> {compact ? <span className="sr-only">{msg("Codex")}</span> : msg("Codex")}
      </button>
      {open && <CodexDialog storyId={storyId} onClose={() => setOpen(false)} />}
    </>
  );
}

export function CodexDialog({ storyId, onClose }) {
  let query = useQuery({
      queryKey: [`codex`, storyId],
      queryFn: () => apiGet(`/stories/${storyId}/codex`),
      staleTime: 0,
    }),
    [tab, setTab] = React.useState(`characters`),
    [selected, setSelected] = React.useState(null),
    data = query.data,
    items = data ? (tab === `characters` ? data.characters : data.places) : [],
    current = items.find((i) => i.id && i.id === selected) ?? null;
  React.useEffect(() => {
    // open on the first discovered entry of the tab
    setSelected(items.find((i) => i.status !== `locked`)?.id ?? null);
  }, [tab, data]);
  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[#04061499] backdrop-blur-[2px]" />
        <Dialog.Content
          aria-describedby={undefined}
          className="sc-cx fixed left-1/2 top-1/2 z-50 flex h-[min(92vh,860px)] w-[min(96vw,1180px)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl"
        >
          <header className="flex items-center gap-4 border-b border-[#e2bd7230] px-6 py-4">
            <Icon.BookOpenText className="size-6 text-[#e2bd72]" />
            <Dialog.Title className="sc-brand text-2xl text-[#f3dca0]">{msg("Codex")}</Dialog.Title>
            <div className="ml-4 flex gap-1" role="tablist">
              {[
                [`characters`, msg("Characters"), Icon.Users],
                [`places`, msg("Places"), Icon.MapPinned],
              ].map(([id, label, TabIcon]) => {
                let c = data?.counts?.[id];
                return (
                  <button
                    key={id}
                    role="tab"
                    aria-selected={tab === id}
                    onClick={() => setTab(id)}
                    className={cn(`sc-cx-tab`, tab === id && `sc-cx-tab-on`)}
                  >
                    <TabIcon className="size-4" /> {label}
                    {c && (
                      <span className="sc-cx-count">
                        {c.found}/{c.total}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
            <Dialog.Close asChild>
              <button className="ml-auto rounded-full p-2 text-[#e2bd72b0] hover:bg-[#e2bd721a] hover:text-[#fff0c4]" aria-label={msg("Close")}>
                <Icon.X className="size-5" />
              </button>
            </Dialog.Close>
          </header>
          {query.isLoading && (
            <div className="flex flex-1 items-center justify-center">
              <Spinner />
            </div>
          )}
          {query.isError && (
            <div className="p-6">
              <ErrorCallout error={query.error} onRetry={() => query.refetch()} />
            </div>
          )}
          {data && !data.enabled && (
            <p className="p-6 text-sm text-[#e2bd72b0]">{msg("This story's world has no codex.")}</p>
          )}
          {data?.enabled && (
            <div className="flex min-h-0 flex-1">
              <div className="min-h-0 flex-1 overflow-y-auto p-5">
                <Progress counts={data.counts[tab]} />
                <div className="grid grid-cols-[repeat(auto-fill,minmax(118px,1fr))] gap-3">
                  {items.map((it, i) =>
                    it.status === `locked` ? (
                      <div key={`l${i}`} className="sc-cx-card sc-cx-locked" aria-label={msg("Not discovered yet")}>
                        <div className="sc-cx-thumb flex items-center justify-center">
                          {tab === `characters` ? <Icon.User className="size-10 opacity-40" /> : <Icon.MapPin className="size-9 opacity-40" />}
                        </div>
                        <p className="sc-cx-name">???</p>
                      </div>
                    ) : (
                      <button
                        key={it.id}
                        onClick={() => setSelected(it.id)}
                        className={cn(`sc-cx-card`, selected === it.id && `sc-cx-card-on`, it.status === `rumored` && `sc-cx-rumor`)}
                      >
                        <div className="sc-cx-thumb">
                          {tab === `characters` && it.portrait ? (
                            <Portrait assetId={it.portrait} name={it.name} className="size-full" rounded="rounded-none" />
                          ) : (
                            <div className="flex size-full items-center justify-center">
                              {tab === `characters` ? <Icon.UserRound className="size-10 opacity-60" /> : <Icon.MapPin className="size-9 opacity-70" />}
                            </div>
                          )}
                        </div>
                        <p className="sc-cx-name">{it.name}</p>
                      </button>
                    ),
                  )}
                </div>
              </div>
              <aside className="sc-cx-detail w-[min(400px,40%)] shrink-0 overflow-y-auto border-l border-[#e2bd7230] p-6">
                {current ? (
                  <Detail item={current} kind={tab} />
                ) : (
                  <p className="text-sm text-[#e2bd7299]">{msg("Nothing discovered yet. Keep playing!")}</p>
                )}
              </aside>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Progress({ counts }) {
  if (!counts) return null;
  let pct = counts.total ? Math.round((counts.found / counts.total) * 100) : 0;
  return (
    <div className="mb-4 flex items-center gap-3 text-xs text-[#e2bd72c0]">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[#e2bd721f]">
        <div className="h-full rounded-full bg-gradient-to-r from-[#c9a25b] to-[#fbe4a3]" style={{ width: `${pct}%` }} />
      </div>
      <span>{msg("{{v0}} of {{v1}} discovered", { v0: counts.found, v1: counts.total })}</span>
    </div>
  );
}

function Detail({ item, kind }) {
  let st = STATUS[item.status],
    fields = Object.entries(item.fields || {}),
    shown = Object.entries(item.expressions || {}),
    hiddenCount = Math.max(0, (item.expressions_total || 0) - shown.length);
  return (
    <div>
      {kind === `characters` && (
        <div className="sc-cx-hero mb-4">
          {item.portrait ? (
            <Portrait assetId={item.portrait} name={item.name} variant="card" className="size-full" rounded="rounded-xl" />
          ) : (
            <div className="flex size-full items-center justify-center rounded-xl">
              <Icon.UserRound className="size-16 opacity-50" />
            </div>
          )}
        </div>
      )}
      <h3 className="sc-brand text-2xl leading-tight text-[#f3dca0]">{item.name}</h3>
      {st && <span className={cn(`sc-cx-badge mt-2 inline-block`, st.tone)}>{st.label}</span>}
      {item.summary && <p className="mt-4 text-sm leading-relaxed text-[#ece6d8e6]">{item.summary}</p>}
      {item.status === `rumored` && (
        <p className="mt-4 text-xs italic text-[#e2bd7299]">
          {kind === `characters`
            ? msg("You have only heard of this character. Meet them to learn more.")
            : msg("You have only heard of this place. Go there to learn more.")}
        </p>
      )}
      {fields.length > 0 && (
        <dl className="mt-4 space-y-2 text-sm">
          {fields.map(([k, v]) => (
            <div key={k} className="grid grid-cols-[7.5rem_1fr] gap-2">
              <dt className="text-[#e2bd72b0]">
                {kind === `places` && k === `type` ? msg("Type") : (FIELD_LABELS[k] ?? k.replace(/_/g, ` `))}
              </dt>
              <dd className="text-[#ece6d8]">{fieldValue(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {kind === `characters` && item.expressions_total > 0 && (
        <div className="mt-5">
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-[#e2bd72b0]">
            {msg("Expressions seen ({{v0}}/{{v1}})", { v0: shown.length, v1: item.expressions_total })}
          </p>
          <div className="flex flex-wrap gap-2">
            {shown.map(([slot, asset]) => (
              <Portrait key={slot} assetId={asset} name={item.name} className="size-14" rounded="rounded-lg" />
            ))}
            {Array.from({ length: hiddenCount }).map((_, i) => (
              <div key={i} className="sc-cx-lockslot flex size-14 items-center justify-center rounded-lg">
                <Icon.Lock className="size-4 opacity-50" />
              </div>
            ))}
          </div>
        </div>
      )}
      {item.first_met && (
        <div className="mt-5 rounded-lg border border-[#e2bd7226] bg-[#e2bd720d] p-3 text-xs text-[#ece6d8cc]">
          <p className="mb-1 font-medium text-[#e2bd72]">
            {item.first_met.seq ? msg("First met (message {{v0}})", { v0: item.first_met.seq }) : msg("First met")}
          </p>
          {item.first_met.evidence && <p className="italic">« {item.first_met.evidence} »</p>}
        </div>
      )}
    </div>
  );
}
