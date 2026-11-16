// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useWorlds, queryKeys } from "@/api/queries";
import * as React from "react";
import { useQueryClient, useQuery, useMutation } from "@tanstack/react-query";
import { apiGet, apiPost, errorMessage, apiUpload, apiPatch } from "@/api/legacy";
import { IS_REMOTE } from "@/lib/remote";
import * as Icon from "lucide-react";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { msg, msgKey } from "@/i18n";
import {
  Badge,
  Button,
  Callout,
  EmptyState,
  ErrorCallout,
  Input,
  Portrait,
  SectionTitle,
  Select,
  Spinner,
  useUi,
} from "@/components/ui";
import { cn } from "@/lib/util";
import { countOf, loreEntitiesSchema, loreEntityDetailSchema, loreWorldSummarySchema } from "@/features/lore/schemas";
import { portraitSlot, usePortraitMap } from "@/lib/portraits";

var LORE_CATEGORIES = [
    `character`,
    `faction`,
    `location`,
    `power_system`,
    `academy`,
    `department`,
    `organization`,
    `polity`,
    `region`,
    `world`,
    `scenario`,
    `plot_hook`,
    `glossary`,
    `calendar`,
    `source`,
  ],
  LORE_HIDDEN_KEYS = new Set([`id`, `name`, `source_ids`, `confidence`, `canon_status`, `aliases`, `type`]),
  humanizeKey = (e) => msg(String(e ?? ``).replace(/_/g, ` `)); // data keys (categories, fields) shown translated when known

export function LorePage() {
  let worlds = useWorlds(),
    [t, n] = React.useState(``),
    r = worlds.data?.find((e) => e.id === t) ?? worlds.data?.[0],
    [i, a] = React.useState(`character`),
    [o, s] = React.useState(``),
    [c, l] = React.useState(``),
    [u, d] = React.useState(null),
    portraitMap = usePortraitMap(r?.id),
    queryClient = useQueryClient(),
    { toast } = useUi(),
    v = React.useRef(null),
    y = o.trim(),
    query = useQuery({
      queryKey: [`lore`, r?.id, i, y, c],
      enabled: !!r,
      queryFn: () =>
        apiGet(
          `/worlds/${r.id}/entities?category=${y ? `` : i}&q=${encodeURIComponent(y)}&confidence=${c}`,
          loreEntitiesSchema,
        ).then((e) => e.entities),
      placeholderData: (e) => e,
    }),
    x = useQuery({
      queryKey: [`world`, r?.id],
      enabled: !!r,
      queryFn: () => apiGet(`/worlds/${r.id}`, loreWorldSummarySchema),
    }),
    mutation = useMutation({
      mutationFn: () => apiPost(`/worlds/${r.id}/reimport`),
      onSuccess: (e) => {
        (queryClient.invalidateQueries({
          queryKey: [`lore`],
        }),
          queryClient.invalidateQueries({
            queryKey: [`world`],
          }),
          queryClient.invalidateQueries({
            queryKey: queryKeys.worlds,
          }),
          toast(
            msg("Re-imported {{v0}} records ({{v1}}). Local canon is untouched.", {
              v0: e.report.entity_total,
              v1: e.status,
            }),
          ));
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    }),
    C = React.useMemo(() => LORE_CATEGORIES.filter((e) => x.data?.categories[e]), [x.data]);
  if (worlds.isLoading)
    return (
      <div className="p-6">
        <Spinner />
      </div>
    );

  if (worlds.isError)
    return (
      <div className="mx-auto max-w-lg p-10">
        <ErrorCallout error={worlds.error} onRetry={() => worlds.refetch()} />
      </div>
    );

  if (!worlds.data?.length || !r)
    return (
      <div className="mx-auto max-w-lg p-10">
        <EmptyState icon={<Icon.BookOpen className="size-8" />} title={msg("No lore imported yet")}>
          {msg("The home page detects lore packs in the app folder. You can also import a pack as a .zip.")}
        </EmptyState>
        {!IS_REMOTE && (
          <div className="flex justify-center">
            <Button onClick={() => v.current?.click()}>
              <Icon.Upload className="size-4" /> {msg("Import lore .zip")}
            </Button>
          </div>
        )}
        <ImportReport r={v} />
      </div>
    );

  let w = x.data?.last_import?.report_json;
  return (
    <div className="flex h-full min-h-0">
      <div
        className={cn(
          `w-full min-w-0 flex-col md:flex md:w-[26rem] md:shrink-0 md:border-r md:border-line`,
          u ? `hidden` : `flex`,
        )}
      >
        <div className="space-y-2 border-b border-line p-3">
          <div className="flex items-center gap-2">
            {worlds.data.length > 1 ? (
              <Select
                value={r.id}
                onChange={(e) => {
                  (n(e.target.value), d(null));
                }}
                className="flex-1"
                aria-label={msg("World")}
              >
                {worlds.data.map((e) => (
                  <option value={e.id} key={e.id}>
                    {e.name}
                  </option>
                ))}
              </Select>
            ) : (
              <h1 className="flex-1 text-sm font-semibold">{r.name}</h1>
            )}
            {/* importing reads the computer's folders: offered on the computer only (v0.5) */}
            {!IS_REMOTE && (<>
            <Button
              size="sm"
              variant="ghost"
              loading={mutation.isPending}
              onClick={() => mutation.mutate()}
              title={msg("Re-scan the source folder (local canon and story data are kept)")}
            >
              <Icon.RefreshCw className="size-3.5" /> {msg("Re-import")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => v.current?.click()}
              title={msg("Import another lore pack (.zip)")}
              aria-label={msg("Import another lore pack")}
            >
              <Icon.Upload className="size-3.5" />
            </Button>
            </>)}
            <ImportReport r={v} />
          </div>
          <div className="relative">
            <Icon.Search className="absolute left-2 top-2.5 size-3.5 text-faint" />
            <Input
              value={o}
              onChange={(e) => s(e.target.value)}
              placeholder={msg("Search all lore (names, aliases, text)")}
              className="pl-7"
              aria-label={msg("Search lore")}
            />
          </div>
          {x.isError ? (
            <p className="text-xs text-danger">
              {msg("Categories unavailable.")}{" "}
              <button className="underline" onClick={() => x.refetch()}>
                {msg("Retry")}
              </button>
            </p>
          ) : (
            <div className="flex flex-wrap gap-1" role="tablist" aria-label={msg("Lore categories")}>
              {C.map((e) => (
                <button
                  role="tab"
                  aria-selected={i === e && !y}
                  onClick={() => {
                    (a(e), s(``));
                  }}
                  className={cn(
                    `rounded px-1.5 py-0.5 text-[11px]`,
                    i === e && !y ? `bg-accent-soft text-accent` : `bg-panel-2 text-muted hover:text-fg`,
                  )}
                  key={e}
                >
                  {humanizeKey(e)} {x.data?.categories[e]}
                </button>
              ))}
            </div>
          )}
          <Select
            value={c}
            onChange={(e) => l(e.target.value)}
            className="h-7 text-xs"
            aria-label={msg("Confidence filter")}
          >
            <option value="">{msg("Any source confidence")}</option>
            <option value="high">{msg("High confidence")}</option>
            <option value="medium">{msg("Medium confidence")}</option>
            <option value="low">{msg("Low confidence")}</option>
          </Select>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2" aria-busy={query.isFetching}>
          {query.isLoading && <Spinner />}
          {query.isError && <ErrorCallout error={query.error} onRetry={() => query.refetch()} />}
          {query.data?.length === 0 && (
            <EmptyState
              title={
                y
                  ? msg("Nothing matches “{{v0}}”", {
                      v0: y,
                    })
                  : msg("No records in this category")
              }
            />
          )}
          {query.data?.map((e) => {
            let t = u?.entityId === e.entity_id && u.category === e.category;
            return (
              <button
                onClick={() =>
                  d({
                    entityId: e.entity_id,
                    category: e.category,
                  })
                }
                aria-current={t || undefined}
                className={cn(
                  `mb-0.5 flex w-full gap-2.5 rounded-md p-2 text-left hover:bg-panel-2`,
                  t && `bg-panel-2`,
                )}
                key={e.id}
              >
                {e.category === `character` && (
                  <Portrait
                    assetId={portraitSlot(portraitMap.data?.[e.entity_id])}
                    name={e.name}
                    className="size-10 shrink-0"
                  />
                )}
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5">
                    <span className="truncate text-[13px] font-medium">{e.name}</span>
                    {y && <Badge>{humanizeKey(e.category)}</Badge>}
                    {e.confidence && e.confidence !== `high` && <Badge tone="warn">{e.confidence}</Badge>}
                  </span>
                  <span className="line-clamp-2 text-[11px] text-faint">
                    {e.type && e.type !== e.category ? `${humanizeKey(e.type)} · ` : ``}
                    {e.summary}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
      <div className={cn(`min-w-0 flex-1 overflow-y-auto p-4 md:block md:p-6`, u ? `block` : `hidden`)}>
        {u && (
          <Button size="sm" variant="ghost" className="mb-3 md:hidden" onClick={() => d(null)}>
            <Icon.ArrowLeft className="size-3.5" /> {msg("Back to list")}
          </Button>
        )}
        {!u && (
          <div className="mx-auto max-w-2xl space-y-4">
            <Callout tone="info" title={msg("Baseline lore is read-only")}>
              {r.data_json?.canon_note}{" "}
              {msg(
                "To change something for your campaign, use “Copy to local canon” on an entry or /addlore in a story.",
              )}
            </Callout>
            {w && (
              <section>
                <SectionTitle>
                  {msg("Last import report (")}
                  {x.data?.last_import?.status})
                </SectionTitle>
                <ul className="space-y-0.5 text-xs text-muted">
                  <li>
                    {msg("Files loaded:")} {countOf(w, `files_loaded`)}
                  </li>
                  <li>
                    {msg("Parse errors:")} {countOf(w, `parse_errors`)}
                  </li>
                  <li>
                    {msg("Duplicate IDs:")} {countOf(w, `duplicate_ids`)}
                  </li>
                  <li>
                    {msg("Missing IDs:")} {countOf(w, `missing_ids`)}
                  </li>
                  <li>
                    {msg("Unresolved references:")} {countOf(w, `unresolved_references`)}
                  </li>
                </ul>
                {Array.isArray(w.parse_errors) &&
                  w.parse_errors.map((e, t) => (
                    <p className="text-xs text-danger" key={t}>
                      {e?.file}
                      {": "}
                      {e?.error}
                    </p>
                  ))}
              </section>
            )}
          </div>
        )}
        {u && (
          <ErrorBoundary area={msg("This lore record")} resetKey={`${u.category}:${u.entityId}`} compact>
            <LoreRecordPanel worldId={r.id} sel={u} assetId={portraitSlot(portraitMap.data?.[u.entityId])} />
          </ErrorBoundary>
        )}
      </div>
    </div>
  );
}

function LoreRecordPanel({ worldId, sel, assetId }) {
  let query = useQuery({
    queryKey: [`lore-entity`, worldId, sel.category, sel.entityId],
    queryFn: () =>
      apiGet(
        `/worlds/${worldId}/entities/${encodeURIComponent(sel.entityId)}?category=${encodeURIComponent(sel.category)}`,
        loreEntityDetailSchema,
      ),
  });
  return query.isLoading ? (
    <Spinner />
  ) : query.isError ? (
    <ErrorCallout error={query.error} onRetry={() => query.refetch()} />
  ) : query.data ? (
    <LoreRecordDetail d={query.data} worldId={worldId} assetId={assetId} />
  ) : (
    <EmptyState title={msg("This record is unavailable")} />
  );
}

function ImportReport({ r: e }) {
  let queryClient = useQueryClient(),
    { toast } = useUi();
  return (
    <input
      ref={e}
      type="file"
      accept=".zip"
      className="hidden"
      onChange={async (e) => {
        let r = e.target.files?.[0];
        if (!r) return;
        let i = new FormData();
        i.append(`file`, r);
        try {
          let e = await apiUpload(`/lore/import-zip`, i);
          (queryClient.invalidateQueries({
            queryKey: queryKeys.worlds,
          }),
            queryClient.invalidateQueries({
              queryKey: [`lore`],
            }),
            toast(
              msg("Imported {{v0}} records ({{v1}})", {
                v0: e.report.entity_total,
                v1: e.status,
              }),
            ));
        } catch (e) {
          toast(errorMessage(e), `danger`);
        }
        e.target.value = ``;
      }}
    />
  );
}

function LoreRecordDetail({ d, worldId, assetId }) {
  let { toast } = useUi(),
    queryClient = useQueryClient(),
    a = d.entity,
    o = Object.entries(a.data).filter(([e]) => !LORE_HIDDEN_KEYS.has(e));
  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-4 flex gap-4">
        {a.category === `character` && (
          <Portrait assetId={assetId} name={a.name} variant="card" className="h-44 w-33 shrink-0" />
        )}
        <div className="min-w-0">
          <h2 className="text-xl font-semibold">{a.name}</h2>
          <p className="text-sm text-muted">
            {humanizeKey(a.type || a.category)}
            {" · "}
            <span className="font-mono text-xs">{a.entity_id}</span>
          </p>
          {a.aliases.length > 0 && (
            <p className="text-xs text-faint">
              {msg("Also:")} {a.aliases.join(`, `)}
            </p>
          )}
          <div className="mt-2 flex flex-wrap gap-1">
            {a.confidence && (
              <Badge tone={a.confidence === `high` ? `ok` : `warn`}>
                {msg("{{v0}} confidence", { v0: msgKey(a.confidence) })}
              </Badge>
            )}
            {a.canon_status && (
              <Badge tone={a.canon_status === `recurring_reference` ? `neutral` : `warn`}>
                {humanizeKey(a.canon_status)}
              </Badge>
            )}
            {a.file && <Badge>{a.file}</Badge>}
          </div>
          <Button
            size="sm"
            className="mt-3 h-auto! min-h-7 max-w-full whitespace-normal! py-1 text-left"
            onClick={async () => {
              try {
                (await apiPost(`/lore/copy-to-canon`, {
                  world_id: worldId,
                  entity_id: a.entity_id,
                }),
                  queryClient.invalidateQueries({
                    queryKey: [`lore-entity`],
                  }),
                  toast(msg("Copied to local canon as a pending override — edit and approve it below.")));
              } catch (e) {
                toast(errorMessage(e), `danger`);
              }
            }}
          >
            <Icon.Copy className="size-3.5" /> {msg("Copy to local canon (create override)")}
          </Button>
        </div>
      </div>
      <div className="space-y-3">
        {o.length === 0 && <p className="text-sm text-faint">{msg("No further details recorded for this entry.")}</p>}
        {o.map(([e, t]) => (
          <div key={e}>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-faint">{humanizeKey(e)}</h3>
            <LoreValue v={t} />
          </div>
        ))}
      </div>
      {d.local_canon.length > 0 && (
        <section className="mt-6">
          <SectionTitle>{msg("Local canon overrides")}</SectionTitle>
          {d.local_canon.map((e) => (
            <LocalCanonCard c={e} key={e.id} />
          ))}
        </section>
      )}
      <section className="mt-6">
        <SectionTitle>{msg("Sources")}</SectionTitle>
        {d.sources.length === 0 && <p className="text-xs text-faint">{msg("No sources listed.")}</p>}
        {d.sources.map((e) => (
          <p className="text-xs text-muted" key={e.id}>
            <b>{e.title || e.id}</b>{" "}
            {e.reliability && (
              <span className="text-faint">
                {"— "}
                {e.reliability}
              </span>
            )}{" "}
            {e.url && (
              <a href={e.url} target="_blank" rel="noreferrer noopener" className="text-accent underline">
                {msg("link")}
              </a>
            )}
          </p>
        ))}
      </section>
    </div>
  );
}

function LocalCanonCard({ c }) {
  let [t, n] = React.useState(c.content),
    queryClient = useQueryClient(),
    { toast } = useUi(),
    a = async (n) => {
      try {
        (await apiPatch(`/local-canon/${c.id}`, {
          content: t,
          ...(n
            ? {
                status: n,
              }
            : {}),
        }),
          queryClient.invalidateQueries({
            queryKey: [`lore-entity`],
          }));
      } catch (e) {
        toast(errorMessage(e), `danger`);
      }
    };
  return (
    <div className="mb-2 rounded-md border border-line p-3">
      <div className="mb-1 flex items-center gap-2 text-sm">
        <span className="font-medium">{c.title}</span>
        <Badge tone={c.status === `approved` ? `ok` : c.status === `rejected` ? `neutral` : `warn`}>
          {msgKey(c.status)}
        </Badge>
      </div>
      <textarea
        value={t}
        onChange={(e) => n(e.target.value)}
        className="min-h-24 w-full rounded-md border border-line bg-panel-2 p-2 text-xs"
        aria-label={msg("Override text")}
      />

      <div className="mt-1 flex gap-1">
        <Button size="sm" onClick={() => a()}>
          {msg("Save")}
        </Button>
        <Button size="sm" variant="primary" onClick={() => a(`approved`)}>
          {msg("Approve")}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => a(`rejected`)}>
          {msg("Reject")}
        </Button>
      </div>
    </div>
  );
}

var fmtValue = (e) => (e == null ? `—` : typeof e == `object` ? JSON.stringify(e) : String(e));

function LoreValue({ v }) {
  return v == null || v === `` ? (
    <p className="text-sm text-faint">—</p>
  ) : typeof v == `object` ? (
    Array.isArray(v) ? (
      v.length === 0 ? (
        <p className="text-sm text-faint">—</p>
      ) : v.every((e) => typeof e != `object` || !e) ? (
        <p className="text-sm text-fg/90">{v.map(fmtValue).join(` · `)}</p>
      ) : (
        <ul className="space-y-1">
          {v.map((e, t) => (
            <li className="rounded border border-line px-2 py-1 text-xs text-muted" key={t}>
              {typeof e == `object` && e && !Array.isArray(e)
                ? Object.entries(e).map(([e, t]) => (
                    <span className="mr-2" key={e}>
                      <span className="text-faint">{e}:</span> {fmtValue(t)}
                    </span>
                  ))
                : fmtValue(e)}
            </li>
          ))}
        </ul>
      )
    ) : (
      <dl className="grid grid-cols-[10rem_1fr] gap-x-2 text-sm">
        {Object.entries(v).map(([e, t]) => (
          <div className="contents" key={e}>
            <dt className="text-faint">{humanizeKey(e)}</dt>
            <dd className="text-fg/90">{Array.isArray(t) ? t.map(fmtValue).join(`, `) : fmtValue(t)}</dd>
          </div>
        ))}
      </dl>
    )
  ) : (
    <p className="text-sm text-fg/90">{String(v)}</p>
  );
}
