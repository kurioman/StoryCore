// Portraits page (#/portraits). Reconstructed from the v1.7.0 bundle (DEVONLY/13_FRONTEND_SOURCE.md); v0.5: per world.
import * as React from "react";
import { useQueryClient, useQuery, useMutation } from "@tanstack/react-query";
import { apiGet, apiPost, apiPatch, errorMessage, apiDelete, apiUpload } from "@/api/legacy";
import { useWorlds } from "@/api/queries";
import { useLocalState } from "@/lib/hooks";
import { EXPRESSIONS } from "@/api/queries";
import * as Icon from "lucide-react";
import { msg, msgKey } from "@/i18n";
import {
  Badge,
  Button,
  Callout,
  EmptyState,
  Input,
  Modal,
  Portrait,
  SectionTitle,
  Select,
  Spinner,
  TabPanel,
  Tabs,
  useUi,
} from "@/components/ui";
import { cn, fmtBytes } from "@/lib/util";

// v0.5: portraits are separate for each story world. The same character can look different from one story to the
// next (a teenager in one, an adult in another), so the page shows one world at a time and each folder belongs to one
// world (or is shared by every story).
export function PortraitsPage() {
  let worlds = useWorlds(),
    [tab, setTab] = React.useState(`characters`),
    [chosenWorldId, setChosenWorldId] = useLocalState(`portraits-world`, ``),
    world = worlds.data?.find((w) => w.id === chosenWorldId) ?? worlds.data?.[0],
    worldId = world?.id ?? null,
    queryClient = useQueryClient(),
    characters = useQuery({
      queryKey: [`portrait-chars`, worldId],
      enabled: !!worldId,
      queryFn: () => apiGet(`/assets/characters?world_id=${encodeURIComponent(worldId)}`).then((d) => d.characters),
    }),
    problems = useQuery({
      queryKey: [`assets`, `problems`, worldId],
      enabled: !!worldId,
      queryFn: () =>
        apiGet(
          `/assets/manifest?status=unmatched,ambiguous,duplicate,invalid,ignored&world_id=${encodeURIComponent(worldId)}`,
        ).then((d) => d.assets),
    }),
    refresh = () => {
      for (let key of [`portrait-chars`, `assets`, `portrait-map`, `roots`]) queryClient.invalidateQueries({ queryKey: [key] });
    },
    withPortraits = characters.data?.filter((c) => Object.keys(c.slots).length > 0) ?? [],
    withoutPortraits = characters.data?.filter((c) => Object.keys(c.slots).length === 0) ?? [];
  if (worlds.isLoading) return <Spinner />;
  if (!worlds.data?.length)
    return (
      <div className="p-8">
        <EmptyState title={msg("No story yet")}>{msg("Portraits belong to a story: add a lore pack first.")}</EmptyState>
      </div>
    );
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2">
        <Icon.BookOpen className="size-4 text-accent" />
        <Select
          value={worldId ?? ``}
          onChange={(e) => setChosenWorldId(e.target.value)}
          className="w-auto min-w-48"
          aria-label={msg("Story")}
        >
          {worlds.data.map((w) => (
            <option value={w.id} key={w.id}>
              {w.name}
            </option>
          ))}
        </Select>
        <span className="text-xs text-faint">
          {msg("Portraits are separate for each story: the same character can look different in another one.")}
        </span>
      </div>
      <div className="min-h-0 flex-1">
        <Tabs
          value={tab}
          onValueChange={setTab}
          className="h-full"
          listClassName="px-4"
          tabs={[
            { value: `characters`, label: msg("Characters ({{v0}})", { v0: withPortraits.length }) },
            {
              value: `mapping`,
              label: msg("Needs mapping"),
              badge: problems.data?.length ? <Badge tone="warn">{problems.data.length}</Badge> : undefined,
            },
            { value: `folders`, label: msg("Folders") },
          ]}
        >
          <TabPanel value="characters" className="p-5">
            <h1 className="sr-only">{msg("Portraits")}</h1>
            <p className="mb-4 max-w-3xl text-xs text-muted">
              {msg("Six expressions per character:")} {EXPRESSIONS().map((e) => `${e.slot} ${e.short}`).join(` · `)}
              {msg(
                ". Image 1 is the fallback when an expression is missing. Original files are never modified; thumbnails are cached in the app data folder.",
              )}
            </p>
            {characters.isLoading && <Spinner />}
            {characters.data && withPortraits.length === 0 && (
              <EmptyState title={msg("No portraits mapped yet")}>{msg("Add an image folder in the Folders tab.")}</EmptyState>
            )}
            <div className="space-y-4">
              {withPortraits.map((c) => (
                <PortraitCharacterCard c={c} worldId={worldId} onChanged={refresh} key={c.id} />
              ))}
            </div>
            {withoutPortraits.length > 0 && (
              <p className="mt-6 text-xs text-faint">
                {msg("Characters without portraits:")} {withoutPortraits.map((c) => c.name).join(`, `)}
                {msg(". They show an initials placeholder.")}
              </p>
            )}
          </TabPanel>
          <TabPanel value="mapping" className="p-5">
            <NeedsMappingList assets={problems.data ?? []} chars={characters.data ?? []} onChanged={refresh} />
          </TabPanel>
          <TabPanel value="folders" className="p-5">
            <PortraitFolders worldId={worldId} worlds={worlds.data} onChanged={refresh} />
          </TabPanel>
        </Tabs>
      </div>
    </div>
  );
}

function PortraitCharacterCard({ c, worldId, onChanged }) {
  let [n, r] = React.useState(null);
  return (
    <div className="rounded-lg border border-line p-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-sm font-medium">{c.name}</span>
        <span className="font-mono text-[11px] text-faint">{c.id}</span>
        {c.missing.length > 0 && (
          <Badge tone="warn">
            {msg("missing")} {c.missing.join(`, `)}
          </Badge>
        )}
      </div>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
        {EXPRESSIONS().map((t) => {
          let n = c.slots[String(t.slot)];
          return (
            <button onClick={() => n && r(n)} className="group text-left" title={t.name} key={t.slot}>
              {n ? (
                <Portrait assetId={n} name={`${c.name} – ${t.short}`} variant="card" className="aspect-[3/4] w-full" />
              ) : (
                <div className="flex aspect-[3/4] w-full items-center justify-center rounded-md border border-dashed border-line text-[10px] text-faint">
                  {msg("missing → #1")}
                </div>
              )}
              <p className="mt-0.5 truncate text-[11px] text-muted">
                {t.slot}
                {". "}
                {t.short}
              </p>
            </button>
          );
        })}
      </div>
      {n && <PortraitAssetDialog assetId={n} worldId={worldId} onClose={() => r(null)} onChanged={onChanged} />}
    </div>
  );
}

function PortraitAssetDialog({ assetId, worldId, onClose, onChanged }) {
  let query = useQuery({
      queryKey: [`assets`, `one`, assetId],
      queryFn: () => apiGet(`/assets/manifest`).then((t) => t.assets.find((t) => t.id === assetId)),
    }),
    i = useQuery({
      queryKey: [`portrait-chars`, worldId],
      queryFn: () => apiGet(`/assets/characters?world_id=${encodeURIComponent(worldId)}`).then((e) => e.characters),
    });
  return query.data ? (
    <Modal open onOpenChange={(e) => !e && onClose()} title={query.data.rel_path} size="lg">
      <div className="flex gap-4">
        <Portrait
          assetId={assetId}
          name={query.data.rel_path}
          variant="full"
          className="max-h-96 w-1/2 object-contain"
        />

        <div className="flex-1 space-y-2 text-xs">
          <p>
            {query.data.width}×{query.data.height}
            {" · "}
            {query.data.ext}
            {" · "}
            {fmtBytes(query.data.file_size)}
          </p>
          <p className="text-muted">{query.data.match_reason}</p>
          <MapAssetRow
            a={query.data}
            chars={i.data ?? []}
            onDone={() => {
              (onChanged(), onClose());
            }}
          />
        </div>
      </div>
    </Modal>
  ) : null;
}

function MapAssetRow({ a: e, chars, onDone }) {
  let { toast } = useUi(),
    [i, a] = React.useState(e.character_id ?? e.candidates_json[0] ?? ``),
    [o, s] = React.useState(String(e.slot ?? 1)),
    c = async (t = false) => {
      try {
        (await apiPost(`/assets/overrides`, {
          asset_id: e.id,
          character_id: t ? null : i || null,
          slot: t ? null : Number(o),
          ignored: t,
        }),
          toast(t ? msg("File ignored", {}) : msg("Mapping saved", {})),
          onDone());
      } catch (e) {
        toast(errorMessage(e), `danger`);
      }
    };
  return (
    <div className="space-y-2">
      <Select value={i} onChange={(e) => a(e.target.value)} aria-label={msg("Character")}>
        <option value="">{msg("Choose character…")}</option>
        {e.candidates_json.length > 0 && (
          <optgroup label={msg("Likely")}>
            {e.candidates_json.map((e) => (
              <option value={e} key={`c-${e}`}>
                {chars.find((t) => t.id === e)?.name ?? e}
              </option>
            ))}
          </optgroup>
        )}
        <optgroup label={msg("All characters")}>
          {chars.map((e) => (
            <option value={e.id} key={e.id}>
              {e.name}
            </option>
          ))}
        </optgroup>
      </Select>
      <Select value={o} onChange={(e) => s(e.target.value)} aria-label={msg("Expression")}>
        {EXPRESSIONS().map((e) => (
          <option value={e.slot} key={e.slot}>
            {e.slot}
            {". "}
            {e.name}
          </option>
        ))}
      </Select>
      <div className="flex flex-wrap gap-1">
        <Button size="sm" variant="primary" disabled={!i} onClick={() => c()}>
          {msg("Map this file")}
        </Button>
        {e.slug && (
          <Button
            size="sm"
            disabled={!i}
            onClick={async () => {
              e.slug &&
                i &&
                (await apiPost(`/assets/slug-overrides`, {
                  slug: e.slug,
                  character_id: i,
                }),
                toast(
                  msg("All files named “{{v0}}…” now map to {{v1}}", {
                    v0: e.slug,
                    v1: chars.find((e) => e.id === i)?.name ?? i,
                  }),
                ),
                onDone());
            }}
            title={msg("Applies to every file with this name prefix")}
          >
            {msg("Map all “")}
            {e.slug}
            {msg("” files")}
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={() => c(true)}>
          {msg("Ignore file")}
        </Button>
        {e.status === `override` && (
          <Button
            size="sm"
            variant="ghost"
            onClick={async () => {
              (await apiDelete(`/assets/overrides/${e.id}`), onDone());
            }}
          >
            {msg("Clear manual mapping")}
          </Button>
        )}
      </div>
    </div>
  );
}

function NeedsMappingList({ assets, chars, onChanged }) {
  return assets.length ? (
    <div className="grid gap-3 lg:grid-cols-2">
      {assets.map((e) => (
        <div className="flex gap-3 rounded-lg border border-line p-3" key={e.id}>
          {e.readable ? (
            <Portrait assetId={e.id} name={e.rel_path} variant="card" className="h-36 w-27 shrink-0" />
          ) : (
            <div className="flex h-36 w-27 items-center justify-center rounded-md border border-dashed border-danger/50 text-[10px] text-danger">
              {msg("unreadable")}
            </div>
          )}
          <div className="min-w-0 flex-1 text-xs">
            <p className="truncate font-mono">{e.rel_path}</p>
            <Badge tone={e.status === `invalid` ? `danger` : `warn`} className="my-1">
              {e.status}
            </Badge>
            <p className="mb-2 text-muted">{e.match_reason}</p>
            {e.readable && <MapAssetRow a={e} chars={chars} onDone={onChanged} />}
          </div>
        </div>
      ))}
    </div>
  ) : (
    <EmptyState title={msg("Every file is mapped")}>
      {msg("Unmatched, ambiguous, duplicate or unreadable files show up here.")}
    </EmptyState>
  );
}

function PortraitFolders({ worldId, worlds, onChanged }) {
  let query = useQuery({
      queryKey: [`roots`],
      queryFn: () => apiGet(`/assets/roots`).then((e) => e.roots),
    }),
    n = useQuery({
      queryKey: [`onboarding`],
      queryFn: () => apiGet(`/onboarding`),
    }),
    { toast, confirm } = useUi(),
    [a, o] = React.useState(``),
    s = React.useRef(null),
    [c, l] = React.useState(null),
    mutation = useMutation({
      mutationFn: (e) =>
        apiPost(`/assets/roots`, {
          path: e,
          world_id: worldId,
        }),
      onSuccess: (r) => {
        (l(r.report), o(``), query.refetch(), n.refetch(), onChanged());
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    }),
    d = async (n) => {
      try {
        (l(await apiPost(`/assets/roots/${n}/scan`)), onChanged(), query.refetch());
      } catch (e) {
        toast(errorMessage(e), `danger`);
      }
    };
  return (
    <div className="max-w-3xl space-y-5">
      <section>
        <SectionTitle>{msg("Registered folders")}</SectionTitle>
        {query.data?.length === 0 && <p className="text-xs text-faint">{msg("None yet.")}</p>}
        <div className="space-y-1.5">
          {query.data?.map((n) => (
            <div
              className="flex flex-wrap items-center gap-2 rounded-md border border-line px-3 py-2 text-xs"
              key={n.id}
            >
              <span className="min-w-0 flex-1 truncate font-mono" title={n.path}>
                {n.path}
              </span>
              <Select
                value={n.world_id ?? ``}
                className="h-7 w-auto text-xs"
                aria-label={msg("Story of this folder")}
                title={msg("Story of this folder")}
                onChange={async (e) => {
                  try {
                    (l((await apiPatch(`/assets/roots/${n.id}`, { world_id: e.target.value || null })).report),
                      query.refetch(),
                      onChanged());
                  } catch (err) {
                    toast(errorMessage(err), `danger`);
                  }
                }}
              >
                {worlds.map((w) => (
                  <option value={w.id} key={w.id}>
                    {w.name}
                  </option>
                ))}
                <option value="">{msg("Shared (stories without their own portrait)")}</option>
              </Select>
              <Badge>{msgKey(n.kind)}</Badge>
              <span className="text-faint">
                {n.file_count} {msg("files")}
              </span>
              {!n.exists && <Badge tone="danger">{msg("folder missing")}</Badge>}
              {n.links_file_info_json?.files?.length ? (
                <Badge tone="info" title={msg("Remote links are listed but never fetched automatically")}>
                  {msg("links file:")} {n.links_file_info_json.urls} {msg("URLs")}
                </Badge>
              ) : null}
              <Button size="sm" variant="ghost" onClick={() => d(n.id)}>
                <Icon.RefreshCw className="size-3.5" /> {msg("Rescan")}
              </Button>
              {n.kind === `folder` && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={async () => {
                    let i = await apiPost(`/assets/roots/${n.id}/copy-to-app-data`);
                    (toast(
                      msg("Copied {{v0}} images into app data. {{v1}}", {
                        v0: i.copied,
                        v1: i.note,
                      }),
                      `info`,
                    ),
                      query.refetch(),
                      onChanged());
                  }}
                >
                  {msg("Copy into app data")}
                </Button>
              )}
              <Button
                size="sm"
                variant="ghost"
                onClick={async () => {
                  (await confirm({
                    title: msg("Unregister this folder?"),
                    body: msg("Only the registration and mapping are removed — your image files stay where they are."),
                    confirmLabel: msg("Unregister"),
                  })) && (await apiDelete(`/assets/roots/${n.id}`), query.refetch(), onChanged());
                }}
              >
                <Icon.Trash className="size-3.5" />
              </Button>
            </div>
          ))}
        </div>
      </section>
      {n.data?.image_folders
        .filter((e) => !e.registered)
        .map((e) => (
          <Callout
            tone="info"
            title={msg("Found {{v0}} ({{v1}} images)", {
              v0: e.name,
              v1: e.image_count,
            })}
            key={e.path}
          >
            <Button size="sm" className="mt-1" loading={mutation.isPending} onClick={() => mutation.mutate(e.path)}>
              <Icon.FolderPlus className="size-3.5" /> {msg("Register and scan")}
            </Button>
          </Callout>
        ))}
      <section className="space-y-2">
        <SectionTitle>{msg("Add a folder")}</SectionTitle>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            (e.preventDefault(), a.trim() && mutation.mutate(a.trim()));
          }}
        >
          <Input
            value={a}
            onChange={(e) => o(e.target.value)}
            placeholder={msg(
              "Folder path on this computer, e.g. C:\\Users\\me\\Pictures\\portraits",
            )}
          />

          <Button type="submit" loading={mutation.isPending}>
            {msg("Scan folder")}
          </Button>
        </form>
        <p className="text-xs text-faint">
          {msg("Or upload a folder through the browser (the images are copied into the app data folder):")}
        </p>
        <input
          ref={s}
          type="file"
          multiple
          className="hidden"
          webkitdirectory=""
          onChange={async (n) => {
            let i = Array.from(n.target.files ?? []);
            if (!i.length) return;
            let a = new FormData();
            (i.forEach((e) => a.append(`files`, e)),
              worldId && a.append(`world_id`, worldId),
              a.append(
                `relative_paths`,
                i.map((e) => e.webkitRelativePath || e.name).join(`
`),
              ));
            try {
              let n = await apiUpload(`/assets/upload`, a);
              (l(n.report), query.refetch(), onChanged());
            } catch (e) {
              toast(errorMessage(e), `danger`);
            }
            n.target.value = ``;
          }}
        />

        <Button onClick={() => s.current?.click()}>
          <Icon.Upload className="size-4" /> {msg("Choose a folder to upload…")}
        </Button>
      </section>
      {c && (
        <Callout tone="ok" title={msg("Scan report")}>
          <pre className="whitespace-pre-wrap text-[11px]">
            {JSON.stringify(
              {
                files: c.files,
                by_status: c.by_status,
                characters_matched: c.characters_matched,
                missing_slots: c.missing_slots,
              },
              null,
              1,
            )}
          </pre>
        </Callout>
      )}
      <p className={cn(`text-xs text-faint`)}>
        {msg("Supported: WEBP, PNG, JPEG, GIF, BMP, AVIF. Files are verified by decoding, not by extension.")}
      </p>
    </div>
  );
}
