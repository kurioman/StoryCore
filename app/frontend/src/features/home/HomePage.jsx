// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { apiGet, apiPost, errorMessage } from "@/api/legacy";
import { useStories, useProviders, queryKeys } from "@/api/queries";
import * as React from "react";
import * as Icon from "lucide-react";
import { msg, msgKey } from "@/i18n";
import { Badge, Button, Callout } from "@/components/ui";
import { Logo } from "@/features/sidebar/Sidebar";
import { navigate } from "@/lib/router";
import { timeAgo } from "@/lib/util";

export function HomePage() {
  let query = useQuery({
      queryKey: [`onboarding`],
      queryFn: () => apiGet(`/onboarding`),
    }),
    stories = useStories(),
    n = useProviders(),
    queryClient = useQueryClient(),
    [i, a] = React.useState(null),
    [o, s] = React.useState(null),
    [c, l] = React.useState(null),
    mutation = useMutation({
      mutationFn: (e) =>
        apiPost(`/lore/import`, {
          path: e,
        }),
      onSuccess: (e) => {
        (a(e),
          queryClient.invalidateQueries({
            queryKey: [`onboarding`],
          }),
          queryClient.invalidateQueries({
            queryKey: queryKeys.worlds,
          }));
      },
      onError: (e) => l(errorMessage(e)),
    }),
    d = useMutation({
      mutationFn: (e) =>
        apiPost(`/assets/roots`, {
          path: e,
        }),
      onSuccess: (e) => {
        (s(e.report),
          queryClient.invalidateQueries({
            queryKey: [`onboarding`],
          }),
          queryClient.invalidateQueries({
            queryKey: [`portrait-map`],
          }));
      },
      onError: (e) => l(errorMessage(e)),
    }),
    f = (stories.data ?? []).filter((e) => e.status === `active`).slice(0, 6),
    p = (n.data?.providers ?? []).filter((e) => e.provider_type !== `mock`),
    g = query.data?.lore_candidates.filter((e) => !e.imported) ?? [],
    v = query.data?.image_folders.filter((e) => !e.registered) ?? [];
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-6 py-10">
        <div className="mb-8 flex items-center gap-3">
          <Logo />
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{msg("StoryCore")}</h1>
            <p className="text-sm text-muted">
              {msg("Your local storytelling workspace. Everything is stored on this computer.")}
            </p>
          </div>
        </div>
        {c && (
          <Callout tone="danger" className="mb-4">
            {c}
          </Callout>
        )}
        {(g.length > 0 || v.length > 0 || p.length === 0) && (
          <section className="mb-8 space-y-3">
            <h2 className="text-sm font-semibold text-muted">{msg("Get set up")}</h2>
            {g.map((e) => (
              <div className="flex items-center gap-3 rounded-lg border border-line bg-panel p-4" key={e.path}>
                <Icon.BookOpen className="size-5 text-accent" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">
                    {msg("Lore pack found:")} {e.name}
                  </p>
                  <p className="truncate text-xs text-faint">{e.path}</p>
                </div>
                <Button variant="primary" loading={mutation.isPending} onClick={() => mutation.mutate(e.path)}>
                  {msg("Import lore")}
                </Button>
              </div>
            ))}
            {v.map((t) => (
              <div className="flex items-center gap-3 rounded-lg border border-line bg-panel p-4" key={t.path}>
                <Icon.Images className="size-5 text-accent" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">
                    {msg("Portrait folder found:")} {t.name}
                    {" ("}
                    {t.image_count} {msg("images)")}
                  </p>
                  <p className="truncate text-xs text-faint">
                    {t.path} {msg("· files are read in place, never modified")}
                  </p>
                </div>
                <Button
                  variant="primary"
                  loading={d.isPending}
                  onClick={() => d.mutate(t.path)}
                  disabled={query.data?.worlds === 0 && g.length > 0}
                  title={
                    query.data?.worlds === 0
                      ? msg("Import the lore first so images can be matched to characters")
                      : undefined
                  }
                >
                  {msg("Scan portraits")}
                </Button>
              </div>
            ))}
            {p.length === 0 && (
              <div className="flex items-center gap-3 rounded-lg border border-line bg-panel p-4">
                <Icon.Cpu className="size-5 text-accent" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{msg("Connect a model")}</p>
                  <p className="text-xs text-faint">
                    {msg(
                      "Only the built-in offline mock provider is set up. Add local Ollama or a cloud API to write real stories.",
                    )}
                  </p>
                </div>
                <Button onClick={() => navigate(`/settings/providers`)}>{msg("Add provider")}</Button>
              </div>
            )}
          </section>
        )}
        {i && (
          <Callout tone={i.status === `succeeded` ? `ok` : `warn`} className="mb-4" title={msg("Lore import report")}>
            <p>
              {i.report.entity_total} {msg("records imported. Parse errors:")} {i.report.parse_errors.length}
              {msg(", unresolved references:")} {i.report.unresolved_references.length}
              {msg(", missing IDs:")} {i.report.missing_ids.length}
              {msg(", duplicates:")} {i.report.duplicate_ids.length}.
            </p>
            <div className="mt-1 flex flex-wrap gap-1">
              {Object.entries(i.report.entities_by_category).map(([e, t]) => (
                <Badge key={e}>
                  {msgKey(e)}
                  {": "}
                  {t}
                </Badge>
              ))}
            </div>
            <button className="mt-1 text-xs underline" onClick={() => navigate(`/lore`)}>
              {msg("Open the lore library")}
            </button>
          </Callout>
        )}
        {o && (
          <Callout tone="ok" className="mb-4" title={msg("Portrait scan")}>
            {o.characters_matched} {msg("characters matched.")}{" "}
            {Object.entries(o.by_status)
              .map(([e, t]) => `${t} ${e}`)
              .join(`, `)}
            {". "}
            <button className="underline" onClick={() => navigate(`/portraits`)}>
              {msg("Review mapping")}
            </button>
          </Callout>
        )}
        <section className="mb-8 grid gap-3 sm:grid-cols-3">
          <button
            onClick={() => navigate(`/new`)}
            className="flex flex-col items-start gap-2 rounded-lg border border-line bg-panel p-4 text-left hover:border-accent/50"
          >
            <Icon.Plus className="size-5 text-accent" />
            <span className="text-sm font-medium">{msg("New story")}</span>
            <span className="text-xs text-faint">{msg("Pick a world, avatar and starter.")}</span>
          </button>
          <button
            onClick={() => navigate(`/avatars`)}
            className="flex flex-col items-start gap-2 rounded-lg border border-line bg-panel p-4 text-left hover:border-accent/50"
          >
            <Icon.UserRound className="size-5 text-accent" />
            <span className="text-sm font-medium">{msg("Create an avatar")}</span>
            <span className="text-xs text-faint">{msg("Your reusable protagonists.")}</span>
          </button>
          <button
            onClick={() => navigate(`/lore`)}
            className="flex flex-col items-start gap-2 rounded-lg border border-line bg-panel p-4 text-left hover:border-accent/50"
          >
            <Icon.BookOpen className="size-5 text-accent" />
            <span className="text-sm font-medium">{msg("Browse lore")}</span>
            <span className="text-xs text-faint">{msg("Characters, factions, places, systems.")}</span>
          </button>
        </section>
        <section>
          <h2 className="mb-2 text-sm font-semibold text-muted">{msg("Continue")}</h2>
          {f.length === 0 ? (
            <p className="text-sm text-faint">{msg("No stories yet.")}</p>
          ) : (
            <div className="grid gap-2 sm:grid-cols-2">
              {f.map((e) => (
                <button
                  onClick={() => navigate(`/story/${e.id}`)}
                  className="rounded-lg border border-line bg-panel p-3 text-left hover:border-line-strong"
                  key={e.id}
                >
                  <p className="truncate text-sm font-medium">{e.title}</p>
                  <p className="text-xs text-faint">
                    {timeAgo(e.last_activity)} {e.world_name && `· ${e.world_name}`}{" "}
                    {e.avatar_name && `· ${e.avatar_name}`}
                  </p>
                  {e.last_snippet && (
                    <p className="mt-1 line-clamp-2 font-serif text-xs text-muted">{e.last_snippet}</p>
                  )}
                </button>
              ))}
            </div>
          )}
        </section>
        {query.data && query.data.worlds > 0 && g.length === 0 && (
          <p className="mt-8 flex items-center gap-1.5 text-xs text-faint">
            <Icon.CircleCheck className="size-3.5 text-ok" /> {msg("Lore imported ·")} {query.data.asset_roots}{" "}
            {msg("portrait folder(s) registered")}
          </p>
        )}
      </div>
    </div>
  );
}
