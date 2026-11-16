// Story library (v0.5, roadmap phase 3) at #/library, where "Start your next adventure" leads.
// "Resume": the latest story in a big card, then the other stories in progress. "Stories": one card per lore pack
// (cover, name, tags, summary from pack.json format 2, in the interface language). A card opens the story sheet:
// openings, "New game" (wizard with the world and opening chosen) and the games already started in that world.
import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Icon from "lucide-react";
import { useStories, useWorlds } from "@/api/queries";
import { msg, packText, shownLanguage } from "@/i18n";
import { Spinner } from "@/components/ui";
import { SetupNotices } from "@/features/home/SetupNotices";
import { navigate } from "@/lib/router";
import { cn, timeAgo } from "@/lib/util";

export function lastStory(stories) {
  return [...(stories ?? [])]
    .filter((s) => s.status === `active`)
    .sort((a, b) => String(b.last_activity ?? b.updated_at).localeCompare(String(a.last_activity ?? a.updated_at)))[0];
}

function coverUrl(world) {
  return world?.data_json?.library?.cover ? `/api/worlds/${world.id}/cover` : null;
}

function Cover({ world, className }) {
  let url = coverUrl(world);
  return url ? (
    <img src={url} alt="" className={cn(`object-cover`, className)} draggable={false} />
  ) : (
    <div className={cn(`sc-lib-nocover flex items-center justify-center p-3 text-center`, className)}>
      <span className="sc-brand text-lg text-[#f3dca0]">{world?.name ?? msg("Free-form story")}</span>
    </div>
  );
}

function Tags({ world, className }) {
  let t = world?.data_json?.library?.tags ?? {},
    tags = t[shownLanguage()] || t.en || t.default || Object.values(t)[0] || [];
  if (!tags.length) return null;
  return (
    <div className={cn(`flex flex-wrap gap-1.5`, className)}>
      {tags.map((t) => (
        <span key={t} className="sc-lib-tag">
          {t}
        </span>
      ))}
    </div>
  );
}

export function LibraryPage() {
  let stories = useStories(),
    worlds = useWorlds(),
    [open, setOpen] = React.useState(null),
    byId = Object.fromEntries((worlds.data ?? []).map((w) => [w.id, w])),
    active = [...(stories.data ?? [])]
      .filter((s) => s.status === `active`)
      .sort((a, b) => String(b.last_activity ?? b.updated_at).localeCompare(String(a.last_activity ?? a.updated_at))),
    [latest, ...others] = active;
  return (
    <div className="sc-lib h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <header className="mb-6 flex items-center gap-3">
          <Icon.Library className="size-7 text-[#e2bd72]" />
          <h1 className="sc-brand text-3xl text-[#f3dca0]">{msg("Library")}</h1>
        </header>
        <SetupNotices />

        {(stories.isLoading || worlds.isLoading) && <Spinner />}

        {latest && (
          <section className="mb-10">
            <h2 className="sc-lib-h2">{msg("Resume")}</h2>
            <button className="sc-lib-resume group" onClick={() => navigate(`/story/${latest.id}`)}>
              <Cover world={byId[latest.world_id]} className="h-full w-full" />
              <div className="flex min-w-0 flex-1 flex-col p-5 text-left">
                <p className="text-xs uppercase tracking-wider text-[#e2bd72b0]">{msg("Your last adventure")}</p>
                <p className="sc-brand mt-1 truncate text-2xl text-[#f3dca0]">{latest.title}</p>
                <p className="mt-1 text-xs text-[#e2bd72aa]">
                  {[latest.world_name, latest.avatar_name, latest.last_activity && timeAgo(latest.last_activity)]
                    .filter(Boolean)
                    .join(` · `)}
                </p>
                {latest.last_snippet && (
                  <p className="mt-3 line-clamp-3 font-serif text-sm leading-relaxed text-[#ece6d8cc]">{latest.last_snippet}</p>
                )}
                <span className="sc-lib-cta mt-auto self-start">
                  <Icon.Play className="size-4" /> {msg("Continue")}
                </span>
              </div>
            </button>
            {others.length > 0 && (
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {others.slice(0, 9).map((s) => (
                  <button key={s.id} className="sc-lib-mini" onClick={() => navigate(`/story/${s.id}`)}>
                    <Cover world={byId[s.world_id]} className="h-full w-14 shrink-0" />
                    <div className="min-w-0 flex-1 px-3 py-2 text-left">
                      <p className="truncate text-sm font-semibold text-[#f3dca0]">{s.title}</p>
                      <p className="truncate text-xs text-[#e2bd72aa]">
                        {[s.world_name, s.last_activity && timeAgo(s.last_activity)].filter(Boolean).join(` · `)}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>
        )}

        <section>
          <h2 className="sc-lib-h2">{msg("Stories")}</h2>
          {worlds.data && !worlds.data.length && (
            <p className="text-sm text-[#e2bd72aa]">
              {msg("No lore pack yet. Put a pack folder in Lorepack and restart StoryCore.")}
            </p>
          )}
          <div className="grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-5">
            {(worlds.data ?? []).map((w) => {
              let n = active.filter((s) => s.world_id === w.id).length;
              return (
                <button key={w.id} className="sc-lib-card group" onClick={() => setOpen(w.id)}>
                  <div className="sc-lib-cover">
                    <Cover world={w} className="size-full" />
                    {n > 0 && (
                      <span className="sc-lib-count">
                        {msg("{{v0}} game(s)", { v0: n })}
                      </span>
                    )}
                  </div>
                  <div className="p-3 text-left">
                    <p className="sc-brand truncate text-lg text-[#f3dca0]">{w.name}</p>
                    <Tags world={w} className="mt-1.5" />
                    <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-[#ece6d8b3]">
                      {packText(w.data_json?.library?.summary, w.description)}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      </div>
      {open && byId[open] && (
        <StorySheet world={byId[open]} games={active.filter((s) => s.world_id === open)} onClose={() => setOpen(null)} />
      )}
    </div>
  );
}

function StorySheet({ world, games, onClose }) {
  let starters = world.data_json?.starters ?? [],
    [pick, setPick] = React.useState(starters[0]?.id ?? ``);
  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[#04061499] backdrop-blur-[2px]" />
        <Dialog.Content
          aria-describedby={undefined}
          className="sc-cx fixed left-1/2 top-1/2 z-50 flex max-h-[92vh] w-[min(96vw,1000px)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-2xl"
        >
          <div className="hidden w-[38%] shrink-0 sm:block">
            <Cover world={world} className="size-full" />
          </div>
          <div className="flex min-w-0 flex-1 flex-col overflow-y-auto p-7">
            <div className="flex items-start gap-3">
              <Dialog.Title className="sc-brand text-3xl leading-tight text-[#f3dca0]">{world.name}</Dialog.Title>
              <Dialog.Close asChild>
                <button className="ml-auto rounded-full p-2 text-[#e2bd72b0] hover:bg-[#e2bd721a] hover:text-[#fff0c4]" aria-label={msg("Close")}>
                  <Icon.X className="size-5" />
                </button>
              </Dialog.Close>
            </div>
            <Tags world={world} className="mt-2" />
            <p className="mt-4 text-sm leading-relaxed text-[#ece6d8e6]">
              {packText(world.data_json?.library?.summary, world.description)}
            </p>

            {starters.length > 0 && (
              <div className="mt-6">
                <p className="sc-lib-h3">{msg("Choose your opening")}</p>
                <div className="space-y-2">
                  {starters.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => setPick(s.id)}
                      className={cn(`sc-lib-opening`, pick === s.id && `sc-lib-opening-on`)}
                    >
                      <span className="sc-lib-radio" aria-hidden />
                      <span className="min-w-0 flex-1 text-left">
                        <span className="block text-sm font-semibold text-[#f3dca0]">{packText(s.i18n?.name, s.name)}</span>
                        <span className="mt-0.5 block text-xs leading-relaxed text-[#ece6d8b3]">
                          {packText(s.i18n?.purpose, s.purpose)}
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <button
              className="sc-lib-cta mt-6 self-start px-6 py-2.5 text-base"
              onClick={() => navigate(`/new?world=${encodeURIComponent(world.id)}${pick ? `&starter=${encodeURIComponent(pick)}` : ``}`)}
            >
              <Icon.Sparkles className="size-4" /> {msg("New game")}
            </button>

            {games.length > 0 && (
              <div className="mt-8">
                <p className="sc-lib-h3">{msg("Your games in this world")}</p>
                <div className="space-y-1.5">
                  {games.map((g) => (
                    <button key={g.id} onClick={() => navigate(`/story/${g.id}`)} className="sc-lib-game">
                      <Icon.BookOpen className="size-4 shrink-0 text-[#e2bd72]" />
                      <span className="min-w-0 flex-1 truncate text-left text-sm text-[#ece6d8]">{g.title}</span>
                      <span className="shrink-0 text-xs text-[#e2bd7299]">{g.last_activity ? timeAgo(g.last_activity) : ``}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
