// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
// v0.5: only the set-up notices are left (lore pack found, portrait folder found, connect a model, import reports);
// they are shown at the top of the story library (features/library). The old home page is gone.
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { apiGet, apiPost, errorMessage } from "@/api/legacy";
import { useProviders, queryKeys } from "@/api/queries";
import * as React from "react";
import * as Icon from "lucide-react";
import { msg, msgKey } from "@/i18n";
import { Badge, Button, Callout } from "@/components/ui";
import { navigate } from "@/lib/router";
import { IS_ANDROID_APP, IS_REMOTE } from "@/lib/remote";

export function SetupNotices() {
  let query = useQuery({
      queryKey: [`onboarding`],
      queryFn: () => apiGet(`/onboarding`),
    }),
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
    p = (n.data?.providers ?? []).filter((e) => e.provider_type !== `mock`),
    g = query.data?.lore_candidates.filter((e) => !e.imported) ?? [],
    v = query.data?.image_folders.filter((e) => !e.registered) ?? [];
  // setting up (lore, portraits, models) happens on the computer, not on a paired phone (v0.5)
  if (IS_REMOTE) return null;
  return (
    <div>
        {c && (
          <Callout tone="danger" className="mb-4">
            {c}
          </Callout>
        )}
        {(g.length > 0 || v.length > 0 || p.length === 0) && (
          <section className="mb-8 space-y-3">
            <h2 className="text-sm font-semibold text-muted">{msg("Get set up")}</h2>
            {g.map((e) => (
              <div className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-panel p-4" key={e.path}>
                <Icon.BookOpen className="size-5 text-accent" />
                <div className="min-w-[12rem] flex-1">
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
              <div className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-panel p-4" key={t.path}>
                <Icon.Images className="size-5 text-accent" />
                <div className="min-w-[12rem] flex-1">
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
              <div className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-panel p-4">
                <Icon.Cpu className="size-5 text-accent" />
                <div className="min-w-[12rem] flex-1">
                  <p className="text-sm font-medium">{msg("Connect a model")}</p>
                  <p className="text-xs text-faint">
                    {IS_ANDROID_APP
                      ? msg("Only the built-in offline demo narrator is set up. Connect an online AI (OpenRouter, DeepSeek…) to write real stories.")
                      : msg(
                          "Only the built-in offline mock provider is set up. Add local Ollama or a cloud API to write real stories.",
                        )}
                  </p>
                </div>
                <Button onClick={() => navigate(`/setup`)}>{msg("Open the first-run assistant")}</Button>
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
    </div>
  );
}
