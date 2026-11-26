// Story library (v0.5, roadmap phase 3) at #/library, where "Start your next adventure" leads.
// "Resume": the latest story in a big card, then the other stories in progress. "Stories": one card per lore pack
// (cover, name, tags, summary from pack.json format 2, in the interface language). A card opens the story sheet:
// openings, who you play, and the whole new-game flow (StorySheet.jsx), plus the games already started in that world.
import * as React from "react";
import * as Icon from "lucide-react";
import { useStories, useWorlds } from "@/api/queries";
import { msg, packText, shownLanguage } from "@/i18n";
import { Spinner } from "@/components/ui";
import { ImportButton } from "@/features/creator/ImportButton";
import { IS_REMOTE } from "@/lib/remote";
import { SetupNotices } from "@/features/home/SetupNotices";
import { navigate, useHashPath } from "@/lib/router";
import { Cover, Tags } from "@/features/library/parts";
import { StorySheet } from "@/features/library/StorySheet";
import { cn, timeAgo } from "@/lib/util";

export function lastStory(stories) {
  return [...(stories ?? [])]
    .filter((s) => s.status === `active`)
    .sort((a, b) => String(b.last_activity ?? b.updated_at).localeCompare(String(a.last_activity ?? a.updated_at)))[0];
}

export function LibraryPage() {
  let stories = useStories(),
    worlds = useWorlds(),
    hashPath = useHashPath(),
    [open, setOpen] = React.useState(null),
    // where to reopen the sheet: after "Create my avatar", the avatar editor sends the player back here with
    // ?world=<id>&starter=<id>&avatar=<id>
    [resume, setResume] = React.useState(null),
    byId = Object.fromEntries((worlds.data ?? []).map((w) => [w.id, w])),
    active = [...(stories.data ?? [])]
      .filter((s) => s.status === `active`)
      .sort((a, b) => String(b.last_activity ?? b.updated_at).localeCompare(String(a.last_activity ?? a.updated_at))),
    [latest, ...others] = active;
  React.useEffect(() => {
    let q = new URLSearchParams(hashPath.split(`?`)[1] ?? ``),
      w = q.get(`world`);
    if (!w || !worlds.data) return;
    let found = worlds.data.find((x) => x.id === w || x.slug === w);
    navigate(`/library`);
    if (!found) return;
    let avatar = q.get(`avatar`);
    setResume({ starter: q.get(`starter`), avatar, step: avatar ? `title` : `pick` });
    setOpen(found.id);
  }, [hashPath, worlds.data]);
  return (
    <div className="sc-lib h-full overflow-y-auto">
      <div className="sc-lib-page mx-auto max-w-6xl px-6 py-8">
        <header className="mb-6 flex items-center gap-3">
          <Icon.Library className="size-7 text-[#e2bd72]" />
          <h1 className="sc-brand text-3xl text-[#f3dca0]">{msg("Library")}</h1>
          {!IS_REMOTE && (
            <div className="ml-auto flex flex-wrap gap-2">
              <ImportButton />
            </div>
          )}
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
              {msg("No world yet. Create one with the world creator, or import a shared world (.zip).")}
            </p>
          )}
          <div className="sc-lib-grid grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-5">
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
            {!IS_REMOTE && (
              <button className="sc-lib-card sc-lib-card-ghost group" onClick={() => navigate(`/creator`)}>
                <div className="sc-lib-cover sc-lib-ghost-cover">
                  <span className="sc-lib-ghost-icon">
                    <Icon.Plus className="size-8" />
                  </span>
                  <Icon.PencilRuler className="mt-4 size-6 text-[#e2bd72aa]" />
                </div>
                <div className="p-3 text-left">
                  <p className="sc-brand truncate text-lg text-[#f3dca0]">{msg("Create a world")}</p>
                  <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-[#ece6d8b3]">
                    {msg("Invent your own world, its characters and places, and play it like the others.")}
                  </p>
                </div>
              </button>
            )}
            <div className="sc-lib-card sc-lib-card-ghost sc-lib-card-soon" aria-disabled="true">
              <div className="sc-lib-cover sc-lib-ghost-cover">
                <Icon.Sparkles className="size-9 text-[#e2bd7288]" />
              </div>
              <div className="p-3 text-left">
                <p className="sc-brand text-lg text-[#f3dca0b0]">{msg("More stories to come soon…")}</p>
                <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-[#ece6d899]">
                  {msg("New worlds are on their way.")}
                </p>
              </div>
            </div>
          </div>
        </section>
      </div>
      {open && byId[open] && (
        <StorySheet
          world={byId[open]}
          games={active.filter((s) => s.world_id === open)}
          initial={resume}
          key={open}
          onClose={() => {
            setOpen(null);
            setResume(null);
          }}
        />
      )}
    </div>
  );
}
