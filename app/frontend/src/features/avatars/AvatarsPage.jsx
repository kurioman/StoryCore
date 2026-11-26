// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useAvatars, queryKeys } from "@/api/queries";
import { useQueryClient, useQuery, useMutation } from "@tanstack/react-query";
import * as React from "react";
import * as Icon from "lucide-react";
import { apiPost, errorMessage, apiPut, apiUpload, apiGet, apiDelete } from "@/api/legacy";
import { msg } from "@/i18n";
import {
  Badge,
  Button,
  Callout,
  EmptyState,
  Field,
  IconButton,
  Input,
  Select,
  TabPanel,
  Tabs,
  Textarea,
  UploadedImage,
  useUi,
} from "@/components/ui";
import { cn, downloadJson, estimateTokens, readFileText, shortId } from "@/lib/util";
import { navigate, useHashPath } from "@/lib/router";

// v1.8: the story sheet sends a player without an avatar here with ?back=<library address>. The address is kept while
// the avatar is created, and a banner then leads back to the new game with this avatar chosen.
function backTarget(hashPath) {
  let b = new URLSearchParams(hashPath.split(`?`)[1] ?? ``).get(`back`);
  return b && b.startsWith(`/library`) ? b : null;
}
const backQuery = (back) => (back ? `?back=${encodeURIComponent(back)}` : ``);

export function AvatarsPage({ selectedId }) {
  let avatars = useAvatars(),
    back = backTarget(useHashPath()),
    queryClient = useQueryClient(),
    { toast } = useUi(),
    i = React.useRef(null),
    a = selectedId === `new` ? null : (avatars.data?.find((t) => t.id === selectedId) ?? null),
    o = selectedId === `new` || !!a;
  return (
    <div className="flex h-full min-h-0">
      <div className={cn(`w-64 shrink-0 flex-col border-r border-line`, o ? `hidden md:flex` : `flex w-full md:w-64`)}>
        <div className="flex items-center gap-2 border-b border-line p-3">
          <h1 className="text-sm font-semibold">{msg("Avatars")}</h1>
          <div className="ml-auto flex gap-1">
            <IconButton label={msg("Import avatar JSON")} onClick={() => i.current?.click()}>
              <Icon.Upload className="size-4" />
            </IconButton>
            <Button size="sm" variant="primary" onClick={() => navigate(`/avatars/new${backQuery(back)}`)}>
              <Icon.Plus className="size-3.5" /> {msg("New")}
            </Button>
          </div>
          <input
            ref={i}
            type="file"
            accept=".json,application/json"
            className="hidden"
            onChange={async (e) => {
              let t = e.target.files?.[0];
              if (t) {
                try {
                  let e = await apiPost(`/avatars/import`, JSON.parse(await readFileText(t)));
                  (queryClient.invalidateQueries({
                    queryKey: queryKeys.avatars,
                  }),
                    navigate(`/avatars/${e.id}`),
                    toast(msg("Avatar imported")));
                } catch (e) {
                  toast(errorMessage(e), `danger`);
                }
                e.target.value = ``;
              }
            }}
          />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {avatars.data?.length === 0 && (
            <EmptyState title={msg("No avatars yet")}>
              {msg("Create a protagonist you can reuse across stories.")}
            </EmptyState>
          )}
          {avatars.data?.map((t) => (
            <button
              onClick={() => navigate(`/avatars/${t.id}${backQuery(back)}`)}
              className={cn(
                `mb-1 flex w-full items-center gap-2.5 rounded-md p-2 text-left hover:bg-panel-2`,
                t.id === selectedId && `bg-panel-2`,
              )}
              key={t.id}
            >
              <UploadedImage path={t.portrait_path} name={t.name} className="size-10 shrink-0" />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1 truncate text-sm font-medium">
                  {t.name} {t.favourite && <Icon.Star className="size-3 fill-accent text-accent" />}
                </span>
                <span className="block truncate text-xs text-faint">
                  {t.used_by.length
                    ? msg("In {{v0}} story(ies)", {
                        v0: t.used_by.length,
                      })
                    : msg("Not used yet")}
                </span>
              </span>
            </button>
          ))}
        </div>
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        {back && (
          <div className="flex flex-wrap items-center gap-3 border-b border-accent/40 bg-accent-soft px-4 py-2.5 text-sm">
            <Icon.Sparkles className="size-4 shrink-0 text-accent" />
            <span className="min-w-0 flex-1">
              {a
                ? msg("“{{v0}}” is saved. You can add a portrait now or later.", { v0: a.name })
                : msg("Create your avatar, then save it.")}
            </span>
            {a && (
              <Button size="sm" variant="primary" onClick={() => navigate(`${back}&avatar=${encodeURIComponent(a.id)}`)}>
                {msg("Continue my new game")} <Icon.ArrowRight className="size-3.5" />
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={() => navigate(back)}>
              {msg("Back to the story")}
            </Button>
          </div>
        )}
        <div className="min-h-0 flex-1">
        {o ? (
          <AvatarEditor avatar={a} key={selectedId} back={back} />
        ) : (
          <div className="hidden h-full items-center justify-center md:flex">
            <EmptyState title={msg("Select or create an avatar")} />
          </div>
        )}
        </div>
      </div>
    </div>
  );
}

var AVATAR_STORY_FIELDS = () => ([
    {
      key: `backstory`,
      label: msg("Backstory"),
      rows: 6,
    },
    {
      key: `personality`,
      label: msg("Personality"),
      rows: 4,
    },
    {
      key: `goals`,
      label: msg("Goals"),
    },
    {
      key: `motivations`,
      label: msg("Motivations"),
    },
    {
      key: `fears`,
      label: msg("Fears"),
    },
    {
      key: `values`,
      label: msg("Values"),
    },
    {
      key: `speech_style`,
      label: msg("Speech style"),
      hint: msg("How they talk — tone, vocabulary, verbal habits."),
    },
    {
      key: `secrets`,
      label: msg("Secrets"),
      hint: msg("Known to the narrator; NPCs only learn them through play."),
    },
  ]),
  AVATAR_ABILITY_FIELDS = [
    {
      key: `skills`,
      label: msg("Skills"),
    },
    {
      key: `powers`,
      label: msg("Power set"),
    },
    {
      key: `weaknesses`,
      label: msg("Weaknesses"),
    },
  ],
  APPEARANCE_KEYS = [`hair`, `eyes`, `height`, `build`, `clothing`, `distinctive`];

function AvatarEditor({ avatar, back }) {
  let queryClient = useQueryClient(),
    { toast, confirm } = useUi(),
    [i, a] = React.useState(`identity`),
    [o, s] = React.useState(avatar?.name ?? ``),
    [c, l] = React.useState(() =>
      structuredClone(
        avatar?.profile_json ?? {
          format: 2,
          appearance: { description: `` },
          abilities: ``,
          user_note: ``,
          stats: [],
          inventory: [],
        },
      ),
    ),
    [u, d] = React.useState(avatar?.favourite ?? false),
    [f, p] = React.useState((avatar?.tags_json ?? []).join(`, `)),
    [g, v] = React.useState(false),
    y = React.useRef(null),
    b = (e) => {
      (l({
        ...c,
        ...e,
      }),
        v(true));
    },
    query = useQuery({
      queryKey: [`avatar-preview`, o, JSON.stringify(c)],
      enabled: i === `preview`,
      placeholderData: (prev) => prev,
      queryFn: () =>
        apiPost(`/avatars/preview`, {
          name: o,
          profile: c,
        }),
    });
  React.useEffect(() => {
    let e = (e) => g && e.preventDefault();
    return (window.addEventListener(`beforeunload`, e), () => window.removeEventListener(`beforeunload`, e));
  }, [g]);
  let mutation = useMutation({
      mutationFn: async () => {
        let t = {
          name: o.trim() || c.display_name || msg("Unnamed", {}),
          profile: c,
          favourite: u,
          tags: f
            .split(`,`)
            .map((e) => e.trim())
            .filter(Boolean),
        };
        return avatar ? apiPut(`/avatars/${avatar.id}`, t) : apiPost(`/avatars`, t);
      },
      onSuccess: (r) => {
        (v(false),
          queryClient.invalidateQueries({
            queryKey: queryKeys.avatars,
          }),
          toast(msg("Avatar saved")),
          avatar || navigate(`/avatars/${r.id}${backQuery(back)}`));
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    }),
    C = async (r) => {
      if (!avatar) {
        toast(msg("Save the avatar first, then add a portrait."), `warn`);
        return;
      }
      let i = new FormData();
      i.append(`file`, r);
      try {
        (await apiUpload(`/avatars/${avatar.id}/portrait`, i),
          queryClient.invalidateQueries({
            queryKey: queryKeys.avatars,
          }),
          toast(msg("Portrait updated")));
      } catch (e) {
        toast(errorMessage(e), `danger`);
      }
    },
    w = c.portrait_fit ?? {
      x: 50,
      y: 30,
      zoom: 1,
    },
    T = estimateTokens(JSON.stringify(c));
  // Test report of 26 Nov 2026: the simple avatar. Name, portrait, appearance, abilities and a free player note;
  // the prompt preview (with its token count) and the advanced options (tags, starting stats and inventory, portrait
  // framing, export, delete) stay one touch away. Older avatars were folded into this shape by the engine
  // (services/avatar_profile.py): their other fields are in the player note.
  let [showPreview, setShowPreview] = [i === `preview`, (v) => a(v ? `preview` : `identity`)],
    [showAdvanced, setShowAdvanced] = React.useState(false),
    portraitInput = React.useRef(null),
    area = (key, label, hint, rows, placeholder) => (
      <section className="sc-av-card">
        <label className="sc-av-label" htmlFor={`av-${key}`}>
          {label}
        </label>
        <Textarea
          id={`av-${key}`}
          value={key === `appearance` ? (c.appearance?.description ?? ``) : (c[key] ?? ``)}
          onChange={(e) =>
            b(
              key === `appearance`
                ? { appearance: { ...(c.appearance ?? {}), description: e.target.value } }
                : { [key]: e.target.value },
            )
          }
          rows={rows}
          placeholder={placeholder}
          className="mt-1.5 min-h-20"
        />
        {hint && <p className="mt-1.5 text-[11px] text-faint">{hint}</p>}
      </section>
    );
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-2xl flex-col gap-3 p-4 pb-10">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() =>
              avatar ? portraitInput.current?.click() : toast(msg("Save the avatar first, then add a portrait."), `warn`)
            }
            className="relative shrink-0"
            aria-label={msg("Change portrait")}
          >
            <UploadedImage path={avatar?.portrait_path} name={o || `?`} className="size-16 rounded-full" />
            <span className="absolute -bottom-0.5 -right-0.5 flex size-6 items-center justify-center rounded-full border border-line bg-panel text-accent">
              <Icon.Camera className="size-3.5" />
            </span>
          </button>
          <input
            ref={portraitInput}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              let f = e.target.files?.[0];
              (f && C(f), (e.target.value = ``));
            }}
          />
          <div className="min-w-0 flex-1">
            <Input
              value={o}
              onChange={(e) => {
                (s(e.target.value), v(true));
              }}
              placeholder={msg("Name")}
              className="h-10 w-full text-[17px] font-semibold"
              aria-label={msg("Name")}
            />
            <p className="mt-1 text-[11px] text-faint">
              ≈{T} {msg("tokens of profile data")}
              {avatar?.used_by.length ? ` · ${msg("In {{v0}} story(ies)", { v0: avatar.used_by.length })}` : ``}
            </p>
          </div>
          <IconButton
            label={u ? msg("Unfavourite") : msg("Favourite")}
            active={u}
            onClick={() => {
              (d(!u), v(true));
            }}
            className="size-10"
          >
            <Icon.Star className={cn(`size-5`, u && `fill-current`)} />
          </IconButton>
        </div>

        {area(`appearance`, msg("Appearance"), null, 4, msg("Face, hair, build, clothes…"))}
        {area(`abilities`, msg("Abilities"), null, 3, msg("Skills, powers, magic…"))}
        {area(
          `user_note`,
          msg("Player note"),
          msg("Anything else the AI should know, kept up to date as your character changes: new powers, items, relationships, instructions…"),
          5,
          ``,
        )}

        <section className="sc-av-card">
          <button type="button" className="sc-av-toggle" onClick={() => setShowPreview(!showPreview)} aria-expanded={showPreview}>
            <Icon.ScanEye className="size-4" /> {msg("Prompt preview")}
            <span className="ml-auto text-[11px] text-faint">≈{query.data?.tokens ?? T} {msg("tokens")}</span>
            <Icon.ChevronDown className={cn(`size-4 transition-transform`, showPreview && `rotate-180`)} />
          </button>
          {showPreview && (
            <pre className="mt-2 whitespace-pre-wrap rounded-md border border-line bg-panel-2 p-3 text-[12px] text-muted">
              {query.data?.text || msg("Nothing to inject yet.")}
            </pre>
          )}
        </section>

        <section className="sc-av-card">
          <button type="button" className="sc-av-toggle" onClick={() => setShowAdvanced(!showAdvanced)} aria-expanded={showAdvanced}>
            <Icon.Settings className="size-4" /> {msg("Advanced options")}
            <Icon.ChevronDown className={cn(`ml-auto size-4 transition-transform`, showAdvanced && `rotate-180`)} />
          </button>
          {showAdvanced && (
            <div className="mt-3 space-y-4">
              <Field label={msg("Tags")} hint={msg("Comma-separated, only to sort your avatars.")}>
                <Input
                  value={f}
                  onChange={(e) => {
                    (p(e.target.value), v(true));
                  }}
                />
              </Field>
              {avatar?.portrait_path && (
                <div className="grid gap-2 text-xs text-muted sm:grid-cols-3">
                  {[
                    [`x`, msg("Horizontal framing"), 0, 100, 1],
                    [`y`, msg("Vertical framing"), 0, 100, 1],
                    [`zoom`, msg("Zoom"), 1, 2.5, 0.05],
                  ].map(([k, label, min, max, step]) => (
                    <label className="block" key={k}>
                      {label}
                      <input
                        type="range"
                        min={min}
                        max={max}
                        step={step}
                        value={w[k]}
                        onChange={(e) => b({ portrait_fit: { ...w, [k]: Number(e.target.value) } })}
                        className="w-full accent-[var(--c-accent)]"
                      />
                    </label>
                  ))}
                </div>
              )}
              <div>
                <p className="sc-av-label mb-2">{msg("Starting stats & inventory")}</p>
                <AvatarStatsEditor p={c} upd={b} />
              </div>
              {avatar && (
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    onClick={async () => downloadJson(`${avatar.name}.avatar.json`, await apiGet(`/avatars/${avatar.id}/export`))}
                  >
                    <Icon.Download className="size-3.5" /> {msg("Export")}
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={async () => {
                      (await confirm({
                        title: msg("Delete avatar “{{v0}}”?", { v0: avatar.name }),
                        body: avatar.used_by.length
                          ? msg("Stories using it keep a snapshot of the profile.", {})
                          : msg("This cannot be undone.", {}),
                        danger: true,
                        confirmLabel: msg("Delete"),
                      })) &&
                        (await apiDelete(`/avatars/${avatar.id}?confirm=true`),
                        queryClient.invalidateQueries({ queryKey: queryKeys.avatars }),
                        navigate(`/avatars`));
                    }}
                  >
                    <Icon.Trash className="size-3.5" /> {msg("Delete")}
                  </Button>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
      <div className="sc-av-save">
        <Button variant="primary" loading={mutation.isPending} onClick={() => mutation.mutate()} disabled={!g && !!avatar} className="w-full max-w-2xl">
          {g || !avatar ? (
            <>
              <Icon.Check className="size-4" /> {msg("Save")}
            </>
          ) : (
            msg("Saved")
          )}
        </Button>
      </div>
    </div>
  );
}

function AvatarStatsEditor({ p, upd }) {
  let n = p.stats ?? [],
    r = p.inventory ?? [],
    i = (e, r) =>
      upd({
        stats: n.map((t, n) =>
          n === e
            ? {
                ...t,
                ...r,
              }
            : t,
        ),
      });
  return (
    <div className="grid max-w-4xl gap-6 lg:grid-cols-2">
      <section>
        <h3 className="mb-2 text-sm font-medium">{msg("Starting stats")}</h3>
        <p className="mb-2 text-xs text-faint">
          {msg("Leave empty to use the story's stat template. Values can be numbers, text, yes/no or current/max.")}
        </p>
        <div className="space-y-1.5">
          {n.map((e, r) => (
            <div className="flex gap-1" key={e.id}>
              <Input
                value={e.label}
                onChange={(e) =>
                  i(r, {
                    label: e.target.value,
                  })
                }
                className="h-7"
                aria-label={msg("Stat")}
              />

              <Select
                value={e.type}
                onChange={(e) =>
                  i(r, {
                    type: e.target.value,
                  })
                }
                className="h-7 w-28"
                aria-label={msg("Type")}
              >
                <option value="number">{msg("Number")}</option>
                <option value="current_max">{msg("Current/max")}</option>
                <option value="text">{msg("Text")}</option>
                <option value="boolean">{msg("Yes/no")}</option>
              </Select>
              <Input
                value={String(e.value ?? ``)}
                onChange={(t) =>
                  i(r, {
                    value:
                      e.type === `text`
                        ? t.target.value
                        : e.type === `boolean`
                          ? t.target.value === `true`
                          : Number(t.target.value),
                  })
                }
                className="h-7 w-20"
                aria-label={msg("Value")}
              />

              {e.type === `current_max` && (
                <Input
                  value={String(e.max ?? ``)}
                  onChange={(e) =>
                    i(r, {
                      max: Number(e.target.value),
                    })
                  }
                  className="h-7 w-16"
                  placeholder="max"
                  aria-label={msg("Max")}
                />
              )}
              <Input
                value={e.unit ?? ``}
                onChange={(e) =>
                  i(r, {
                    unit: e.target.value,
                  })
                }
                className="h-7 w-14"
                placeholder="unit"
                aria-label={msg("Unit")}
              />

              <IconButton
                label={msg("Remove")}
                onClick={() =>
                  upd({
                    stats: n.filter((e, t) => t !== r),
                  })
                }
              >
                <Icon.Trash className="size-3.5" />
              </IconButton>
            </div>
          ))}
          <Button
            size="sm"
            onClick={() =>
              upd({
                stats: [
                  ...n,
                  {
                    id: shortId(),
                    label: msg("New stat"),
                    type: `number`,
                    value: 0,
                  },
                ],
              })
            }
          >
            <Icon.Plus className="size-3.5" /> {msg("Add stat")}
          </Button>
        </div>
      </section>
      <section>
        <h3 className="mb-2 text-sm font-medium">{msg("Starting inventory & equipment")}</h3>
        <div className="space-y-1.5">
          {r.map((e, n) => (
            <div className="flex gap-1" key={e.id}>
              <Input
                value={e.name}
                onChange={(e) =>
                  upd({
                    inventory: r.map((t, r) =>
                      r === n
                        ? {
                            ...t,
                            name: e.target.value,
                          }
                        : t,
                    ),
                  })
                }
                className="h-7"
                aria-label={msg("Item")}
              />

              <Input
                type="number"
                value={e.qty}
                onChange={(e) =>
                  upd({
                    inventory: r.map((t, r) =>
                      r === n
                        ? {
                            ...t,
                            qty: Number(e.target.value),
                          }
                        : t,
                    ),
                  })
                }
                className="h-7 w-16"
                aria-label={msg("Quantity")}
              />

              <Input
                value={e.note ?? ``}
                onChange={(e) =>
                  upd({
                    inventory: r.map((t, r) =>
                      r === n
                        ? {
                            ...t,
                            note: e.target.value,
                          }
                        : t,
                    ),
                  })
                }
                className="h-7"
                placeholder="note"
                aria-label={msg("Note")}
              />

              <IconButton
                label={msg("Remove")}
                onClick={() =>
                  upd({
                    inventory: r.filter((e, t) => t !== n),
                  })
                }
              >
                <Icon.Trash className="size-3.5" />
              </IconButton>
            </div>
          ))}
          <Button
            size="sm"
            onClick={() =>
              upd({
                inventory: [
                  ...r,
                  {
                    id: shortId(),
                    name: msg("New item", {}),
                    qty: 1,
                  },
                ],
              })
            }
          >
            <Icon.Plus className="size-3.5" /> {msg("Add item")}
          </Button>
        </div>
      </section>
    </div>
  );
}
