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
import { navigate } from "@/lib/router";

export function AvatarsPage({ selectedId }) {
  let avatars = useAvatars(),
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
            <Button size="sm" variant="primary" onClick={() => navigate(`/avatars/new`)}>
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
              onClick={() => navigate(`/avatars/${t.id}`)}
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
      <div className="min-w-0 flex-1">
        {o ? (
          <AvatarEditor avatar={a} key={selectedId} />
        ) : (
          <div className="hidden h-full items-center justify-center md:flex">
            <EmptyState title={msg("Select or create an avatar")} />
          </div>
        )}
      </div>
    </div>
  );
}

var AVATAR_STORY_FIELDS = [
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
  ],
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

function AvatarEditor({ avatar }) {
  let queryClient = useQueryClient(),
    { toast, confirm } = useUi(),
    [i, a] = React.useState(`identity`),
    [o, s] = React.useState(avatar?.name ?? ``),
    [c, l] = React.useState(() =>
      structuredClone(
        avatar?.profile_json ?? {
          appearance: {
            description: ``,
            structured: {},
          },
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
          avatar || navigate(`/avatars/${r.id}`));
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
  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <Input
          value={o}
          onChange={(e) => {
            (s(e.target.value), v(true));
          }}
          placeholder={msg("Avatar name")}
          className="h-8 w-64 text-[15px] font-semibold"
          aria-label={msg("Avatar name")}
        />

        <IconButton
          label={u ? msg("Unfavourite") : msg("Favourite")}
          active={u}
          onClick={() => {
            (d(!u), v(true));
          }}
        >
          <Icon.Star className={cn(`size-4`, u && `fill-current`)} />
        </IconButton>
        <span className="text-xs text-faint">
          ≈{T} {msg("tokens of profile data")}
        </span>
        {avatar?.used_by.length ? (
          <Badge>
            {msg("Used by:")} {avatar.used_by.join(`, `)}
          </Badge>
        ) : null}
        <div className="ml-auto flex gap-1.5">
          {avatar && (
            <>
              <Button
                size="sm"
                variant="ghost"
                onClick={async () =>
                  downloadJson(`${avatar.name}.avatar.json`, await apiGet(`/avatars/${avatar.id}/export`))
                }
              >
                <Icon.Download className="size-3.5" /> {msg("Export")}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={async () => {
                  (await confirm({
                    title: msg("Delete avatar “{{v0}}”?", {
                      v0: avatar.name,
                    }),
                    body: avatar.used_by.length
                      ? msg("Stories using it keep a snapshot of the profile.", {})
                      : msg("This cannot be undone.", {}),

                    danger: true,
                    confirmLabel: msg("Delete"),
                  })) &&
                    (await apiDelete(`/avatars/${avatar.id}?confirm=true`),
                    queryClient.invalidateQueries({
                      queryKey: queryKeys.avatars,
                    }),
                    navigate(`/avatars`));
                }}
              >
                <Icon.Trash className="size-3.5" />
              </Button>
            </>
          )}
          <Button size="sm" variant="primary" loading={mutation.isPending} onClick={() => mutation.mutate()}>
            {g ? msg("Save changes") : msg("Saved")}
          </Button>
        </div>
      </div>
      <Tabs
        value={i}
        onValueChange={a}
        className="min-h-0 flex-1"
        listClassName="px-4"
        tabs={[
          {
            value: `identity`,
            label: msg("Identity"),
          },
          {
            value: `appearance`,
            label: msg("Appearance"),
          },
          {
            value: `story`,
            label: msg("Background & personality"),
          },
          {
            value: `abilities`,
            label: msg("Abilities"),
          },
          {
            value: `sheet`,
            label: msg("Stats & inventory"),
          },
          {
            value: `extra`,
            label: msg("Additional info"),
          },
          {
            value: `preview`,
            label: msg("Prompt preview"),
          },
        ]}
      >
        <TabPanel value="identity" className="p-5">
          <div className="grid max-w-3xl gap-3 sm:grid-cols-2">
            <Field label={msg("Display name")}>
              <Input
                value={c.display_name ?? ``}
                onChange={(e) =>
                  b({
                    display_name: e.target.value,
                  })
                }
              />
            </Field>
            <Field label={msg("Name NPCs use")} hint={msg("Nickname or how they're addressed.")}>
              <Input
                value={c.called_name ?? ``}
                onChange={(e) =>
                  b({
                    called_name: e.target.value,
                  })
                }
              />
            </Field>
            <Field label={msg("Pronunciation")}>
              <Input
                value={c.pronunciation ?? ``}
                onChange={(e) =>
                  b({
                    pronunciation: e.target.value,
                  })
                }
              />
            </Field>
            <Field label={msg("Age")} hint={msg("Stored exactly as entered; never inferred from the portrait.")}>
              <Input
                value={String(c.age ?? ``)}
                onChange={(e) =>
                  b({
                    age: e.target.value,
                  })
                }
              />
            </Field>
            <Field label={msg("Pronouns")}>
              <Input
                value={c.pronouns ?? ``}
                onChange={(e) =>
                  b({
                    pronouns: e.target.value,
                  })
                }
              />
            </Field>
            <Field label={msg("Gender (optional)")}>
              <Input
                value={c.gender ?? ``}
                onChange={(e) =>
                  b({
                    gender: e.target.value,
                  })
                }
              />
            </Field>
            <Field label={msg("Title / epithet")}>
              <Input
                value={c.title ?? ``}
                onChange={(e) =>
                  b({
                    title: e.target.value,
                  })
                }
              />
            </Field>
            <Field label={msg("Occupation")}>
              <Input
                value={c.occupation ?? ``}
                onChange={(e) =>
                  b({
                    occupation: e.target.value,
                  })
                }
              />
            </Field>
            <Field label={msg("Social status")}>
              <Input
                value={c.social_status ?? ``}
                onChange={(e) =>
                  b({
                    social_status: e.target.value,
                  })
                }
              />
            </Field>
            <Field label={msg("Affiliations")}>
              <Input
                value={c.affiliations ?? ``}
                onChange={(e) =>
                  b({
                    affiliations: e.target.value,
                  })
                }
              />
            </Field>
            <Field label={msg("Tags")} className="sm:col-span-2">
              <Input
                value={f}
                onChange={(e) => {
                  (p(e.target.value), v(true));
                }}
                placeholder={msg("comma separated")}
              />
            </Field>
          </div>
        </TabPanel>
        <TabPanel value="appearance" className="p-5">
          <div className="grid max-w-4xl gap-5 lg:grid-cols-[220px_1fr]">
            <div>
              <div className="relative h-72 w-52 overflow-hidden rounded-lg border border-line bg-panel-2">
                {avatar?.portrait_path ? (
                  <img
                    src={`/api/uploads/${avatar.portrait_path}`}
                    alt={msg("Portrait")}
                    className="absolute inset-0 h-full w-full object-cover"
                    style={{
                      objectPosition: `${w.x}% ${w.y}%`,
                      transform: `scale(${w.zoom})`,
                      transformOrigin: `${w.x}% ${w.y}%`,
                    }}
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-xs text-faint">{msg("No portrait")}</div>
                )}
              </div>
              <input
                ref={y}
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && C(e.target.files[0])}
              />

              <Button size="sm" className="mt-2 w-52" onClick={() => y.current?.click()}>
                <Icon.ImagePlus className="size-3.5" />{" "}
                {avatar?.portrait_path ? msg("Replace portrait") : msg("Upload portrait")}
              </Button>
              {avatar?.portrait_path && (
                <div className="mt-2 w-52 space-y-1 text-[11px] text-muted">
                  <label className="block">
                    {msg("Horizontal focus")}
                    <input
                      type="range"
                      min={0}
                      max={100}
                      value={w.x}
                      onChange={(e) =>
                        b({
                          portrait_fit: {
                            ...w,
                            x: Number(e.target.value),
                          },
                        })
                      }
                      className="w-full accent-[var(--c-accent)]"
                    />
                  </label>
                  <label className="block">
                    {msg("Vertical focus")}
                    <input
                      type="range"
                      min={0}
                      max={100}
                      value={w.y}
                      onChange={(e) =>
                        b({
                          portrait_fit: {
                            ...w,
                            y: Number(e.target.value),
                          },
                        })
                      }
                      className="w-full accent-[var(--c-accent)]"
                    />
                  </label>
                  <label className="block">
                    {msg("Zoom")}
                    <input
                      type="range"
                      min={1}
                      max={2.5}
                      step={0.05}
                      value={w.zoom}
                      onChange={(e) =>
                        b({
                          portrait_fit: {
                            ...w,
                            zoom: Number(e.target.value),
                          },
                        })
                      }
                      className="w-full accent-[var(--c-accent)]"
                    />
                  </label>
                </div>
              )}
              {!avatar && (
                <p className="mt-2 w-52 text-[11px] text-faint">
                  {msg("Save the avatar once to enable portrait upload.")}
                </p>
              )}
              <p className="mt-2 w-52 text-[11px] text-faint">
                {msg("The written profile is authoritative; nothing is inferred from the image.")}
              </p>
            </div>
            <div className="space-y-3">
              <Field label={msg("Appearance (free-form)")}>
                <Textarea
                  value={c.appearance?.description ?? ``}
                  onChange={(e) =>
                    b({
                      appearance: {
                        ...c.appearance,
                        description: e.target.value,
                      },
                    })
                  }
                  className="min-h-32"
                />
              </Field>
              <div className="grid gap-3 sm:grid-cols-2">
                {APPEARANCE_KEYS.map((e) => (
                  <Field label={e[0].toUpperCase() + e.slice(1)} key={e}>
                    <Input
                      value={c.appearance?.structured?.[e] ?? ``}
                      onChange={(t) =>
                        b({
                          appearance: {
                            ...c.appearance,
                            structured: {
                              ...(c.appearance?.structured ?? {}),
                              [e]: t.target.value,
                            },
                          },
                        })
                      }
                    />
                  </Field>
                ))}
              </div>
            </div>
          </div>
        </TabPanel>
        <TabPanel value="story" className="p-5">
          <div className="grid max-w-4xl gap-3">
            {AVATAR_STORY_FIELDS.map((e) => (
              <Field label={e.label} hint={e.hint} key={e.key}>
                <Textarea
                  value={String(c[e.key] ?? ``)}
                  onChange={(t) =>
                    b({
                      [e.key]: t.target.value,
                    })
                  }
                  style={{
                    minHeight: `${(e.rows ?? 3) * 1.6}rem`,
                  }}
                />
              </Field>
            ))}
          </div>
        </TabPanel>
        <TabPanel value="abilities" className="p-5">
          <div className="grid max-w-4xl gap-3">
            {AVATAR_ABILITY_FIELDS.map((e) => (
              <Field label={e.label} key={e.key}>
                <Textarea
                  value={String(c[e.key] ?? ``)}
                  onChange={(t) =>
                    b({
                      [e.key]: t.target.value,
                    })
                  }
                />
              </Field>
            ))}
          </div>
        </TabPanel>
        <TabPanel value="sheet" className="p-5">
          <AvatarStatsEditor p={c} upd={b} />
        </TabPanel>
        <TabPanel value="extra" className="p-5">
          <div className="grid max-w-4xl gap-3">
            <Field
              label={msg("Additional character information")}
              hint={msg("Anything else the narrator should know.")}
            >
              <Textarea
                value={c.additional_info ?? ``}
                onChange={(e) =>
                  b({
                    additional_info: e.target.value,
                  })
                }
                className="min-h-60"
              />
            </Field>
            <Field label={msg("Private notes (not sent to the model)")}>
              <Textarea
                value={c.notes ?? ``}
                onChange={(e) =>
                  b({
                    notes: e.target.value,
                  })
                }
              />
            </Field>
          </div>
        </TabPanel>
        <TabPanel value="preview" className="p-5">
          <div className="max-w-3xl">
            <p className="mb-2 text-xs text-muted">
              {msg("This is how the profile is injected into the model's context (≈")}
              {query.data?.tokens ?? `…`} {msg("tokens). Stats and inventory become the story's starting state.")}
            </p>
            <pre className="whitespace-pre-wrap rounded-md border border-line bg-panel-2 p-4 text-[12px] text-muted">
              {query.data?.text || msg("Nothing to inject yet.")}
            </pre>
            {T > 6e3 && (
              <Callout tone="warn" className="mt-3">
                {msg("This profile is large; it will take a big share of smaller models' context budgets.")}
              </Callout>
            )}
          </div>
        </TabPanel>
      </Tabs>
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
