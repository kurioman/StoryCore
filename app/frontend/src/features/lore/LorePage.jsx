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
import { AddRecordCard, EditableRecord } from "@/features/lore/editing";

// Kurio (24/11): the importer's categories gathered into 5 families (sub-filters inside each); "source" (where the
// lore was researched) is not shown, and any category a pack adds that is not listed here goes to "Other"
var LORE_FAMILIES = [
    { id: `characters`, label: `Characters`, cats: [`character`] },
    { id: `places`, label: `Places`, cats: [`location`, `region`] },
    { id: `groups`, label: `Groups`, cats: [`faction`, `organization`, `polity`, `department`] },
    { id: `world`, label: `World & rules`, cats: [`world`, `power_system`, `academy`, `glossary`, `calendar`] },
    { id: `story`, label: `Story`, cats: [`plot_hook`, `scenario`] },
  ],
  LORE_HIDDEN_CATEGORIES = new Set([`source`]),
  LORE_HIDDEN_KEYS = new Set([`id`, `name`, `source_ids`, `confidence`, `canon_status`, `aliases`, `type`]),
  humanizeKey = (e) => msg(String(e ?? ``).replace(/_/g, ` `)); // data keys (categories, fields) shown translated when known

export function LorePage() {
  let worlds = useWorlds(),
    [t, n] = React.useState(``),
    r = worlds.data?.find((e) => e.id === t) ?? worlds.data?.[0],
    [i, a] = React.useState(`characters`),
    [sub, setSub] = React.useState(``),
    [todo, setTodo] = React.useState(false),
    [o, s] = React.useState(``),
    [u, d] = React.useState(null),
    portraitMap = usePortraitMap(r?.id),
    queryClient = useQueryClient(),
    { toast } = useUi(),
    v = React.useRef(null),
    y = o.trim(),
    x = useQuery({
      queryKey: [`world`, r?.id],
      enabled: !!r,
      queryFn: () => apiGet(`/worlds/${r.id}`, loreWorldSummarySchema),
    }),
    C = React.useMemo(() => {
      let counts = x.data?.categories ?? {},
        known = new Set(LORE_FAMILIES.flatMap((f) => f.cats)),
        fams = LORE_FAMILIES.map((f) => ({ ...f, cats: f.cats.filter((c) => counts[c]) })),
        other = Object.keys(counts).filter((c) => counts[c] && !known.has(c) && !LORE_HIDDEN_CATEGORIES.has(c));
      if (other.length) fams.push({ id: `other`, label: `Other`, cats: other });
      return fams
        .filter((f) => f.cats.length)
        .map((f) => ({ ...f, count: f.cats.reduce((n, c) => n + counts[c], 0) }));
    }, [x.data]),
    fam = C.find((f) => f.id === i) ?? C[0],
    catParam = sub && fam?.cats.includes(sub) ? sub : (fam?.cats ?? []).join(`,`),
    query = useQuery({
      queryKey: [`lore`, r?.id, catParam, y],
      enabled: !!r && (!!y || !!fam || x.isError),
      queryFn: () =>
        apiGet(
          `/worlds/${r.id}/entities?category=${y ? `` : encodeURIComponent(catParam)}&q=${encodeURIComponent(y)}`,
          loreEntitiesSchema,
        ).then((e) => e.entities),
      placeholderData: (e) => e,
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
    });
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

  let w = x.data?.last_import?.report_json,
    shown = (query.data ?? []).filter((e) => !todo || (e.completeness && e.completeness.filled < e.completeness.total));
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
            <div className="space-y-1">
              <div className="flex flex-wrap gap-1" role="tablist" aria-label={msg("Lore families")}>
                {C.map((f) => (
                  <button
                    role="tab"
                    aria-selected={fam?.id === f.id && !y}
                    onClick={() => {
                      (a(f.id), setSub(``), s(``));
                    }}
                    className={cn(
                      `rounded px-2 py-0.5 text-xs`,
                      fam?.id === f.id && !y ? `bg-accent-soft text-accent` : `bg-panel-2 text-muted hover:text-fg`,
                    )}
                    key={f.id}
                  >
                    {msg(f.label)} {f.count}
                  </button>
                ))}
                <button
                  onClick={() => setTodo(!todo)}
                  aria-pressed={todo}
                  title={msg("Show only the records that miss some categories of their model")}
                  className={cn(
                    `ml-auto rounded px-2 py-0.5 text-xs`,
                    todo ? `bg-warn-soft text-warn` : `bg-panel-2 text-muted hover:text-fg`,
                  )}
                >
                  <Icon.ListTodo className="mr-1 inline size-3" />
                  {msg("To complete")}
                </button>
              </div>
              {fam && fam.cats.length > 1 && !y && (
                <div className="flex flex-wrap gap-1" role="tablist" aria-label={msg("Lore categories")}>
                  {[``, ...fam.cats].map((e) => (
                    <button
                      role="tab"
                      aria-selected={catParam === (e || fam.cats.join(`,`))}
                      onClick={() => setSub(e)}
                      className={cn(
                        `rounded px-1.5 py-0.5 text-[11px]`,
                        (sub && fam.cats.includes(sub) ? sub : ``) === e
                          ? `bg-panel-2 text-fg ring-1 ring-line`
                          : `text-muted hover:text-fg`,
                      )}
                      key={e || `all`}
                    >
                      {e ? `${humanizeKey(e)} ${x.data?.categories[e]}` : msg("All")}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2" aria-busy={query.isFetching}>
          {query.isLoading && <Spinner />}
          {query.isError && <ErrorCallout error={query.error} onRetry={() => query.refetch()} />}
          {todo && query.data && shown.length === 0 && query.data.length > 0 && (
            <EmptyState title={msg("Every record here follows its model")} />
          )}
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
          {shown.map((e) => {
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
                    {e.completeness && (
                      <Badge
                        tone={e.completeness.filled >= e.completeness.total ? `ok` : `warn`}
                        title={e.completeness.missing.length ? `${msg("Missing:")} ${e.completeness.missing.map((m) => msg(m)).join(`, `)}` : undefined}
                      >
                        {e.completeness.filled}/{e.completeness.total}
                      </Badge>
                    )}
                  </span>
                  <span className="line-clamp-2 text-[11px] text-faint">
                    {e.type && e.type !== e.category ? `${humanizeKey(e.type)} · ` : ``}
                    {e.summary}
                  </span>
                </span>
              </button>
            );
          })}
          {/* Kurio (24/11): add a record the pack does not have yet (computer and phone) */}
          {!y && !todo && fam && query.data && (
            <AddRecordCard
              worldId={r.id}
              cats={sub && fam.cats.includes(sub) ? [sub] : fam.cats}
              onWorldChange={(id) => n(id)}
              onAdded={(res) => d({ entityId: res.id, category: res.category })}
            />
          )}
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
            <Callout tone="info" title={msg("Edit the pack here")}>
              {msg(
                "Click a record's name or any of its fields to change it, and “Add” at the end of a list to create one. The first change to an original pack creates a renamed copy of it: the original is never changed.",
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
            <LoreRecordPanel worldId={r.id} sel={u} assetId={portraitSlot(portraitMap.data?.[u.entityId])} onWorldChange={(id) => n(id)} />
          </ErrorBoundary>
        )}
      </div>
    </div>
  );
}

function LoreRecordPanel({ worldId, sel, assetId, onWorldChange }) {
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
    <LoreRecordDetail d={query.data} worldId={worldId} assetId={assetId} sel={sel} onWorldChange={onWorldChange} />
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

function LoreRecordDetail({ d, worldId, assetId, sel, onWorldChange }) {
  let a = d.entity;
  return (
    <div className="mx-auto max-w-3xl">
      <EditableRecord
        worldId={worldId}
        sel={sel}
        onWorldChange={onWorldChange}
        header={({ name, aliases, file }) => (
          <div className="mb-4 flex gap-4">
            {a.category === `character` && (
              <Portrait assetId={assetId} name={a.name} variant="card" className="h-44 w-33 shrink-0" />
            )}
            <div className="min-w-0 flex-1 space-y-1">
              {name}
              <p className="text-sm text-muted">
                {humanizeKey(a.type || a.category)}
                {" · "}
                <span className="font-mono text-xs">{a.entity_id}</span>
              </p>
              <div className="flex flex-wrap gap-1">
                {file && <Badge>{file}</Badge>}
                {a.completeness && (
                  <Badge tone={a.completeness.filled >= a.completeness.total ? `ok` : `warn`}>
                    {a.completeness.filled}/{a.completeness.total} {msg("categories")}
                  </Badge>
                )}
              </div>
              {a.completeness?.missing.length > 0 && (
                <p className="text-xs text-warn">
                  {msg("Missing:")} {a.completeness.missing.map((m) => msg(m)).join(`, `)}
                </p>
              )}
              {aliases}
            </div>
          </div>
        )}
      />
    </div>
  );
}
