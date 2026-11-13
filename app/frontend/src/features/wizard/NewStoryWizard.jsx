// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useWorlds, useAvatars, useProviders, useSettings, queryKeys } from "@/api/queries";
import { useQueryClient, useMutation } from "@tanstack/react-query";
import * as React from "react";
import { apiPost, apiGet, errorMessage } from "@/api/legacy";
import * as Icon from "lucide-react";
import { msg, msgKey } from "@/i18n";
import {
  Badge,
  Button,
  Callout,
  Field,
  Input,
  Portrait,
  Select,
  Textarea,
  UploadedImage,
  useUi,
} from "@/components/ui";
import { ContextManifest } from "@/features/story/composer";
import { cn } from "@/lib/util";
import { navigate } from "@/lib/router";
import { portraitSlot, usePortraitMap } from "@/lib/portraits";

var WIZARD_STEPS = [
    msg("Story", {}),
    msg("World & start", {}),
    msg("Protagonist", {}),
    msg("Tone & model", {}),
    msg("Review", {}),
  ],
  WIZARD_A = `medium (3–4 paragraphs)`,
  WIZARD_B = 3e3;

export function NewStoryWizard() {
  let worlds = useWorlds(),
    avatars = useAvatars(),
    providers = useProviders(),
    settings = useSettings(),
    portraitMap = usePortraitMap(),
    queryClient = useQueryClient(),
    { toast } = useUi(),
    [s, c] = React.useState(0),
    [l, u] = React.useState(null),
    [d, f] = React.useState(null),
    [p, g] = React.useState({
      title: ``,
      world_id: ``,
      starter_id: ``,
      starting_location: ``,
      starting_time: ``,
      avatar_id: ``,
      tone: ``,
      pacing: ``,
      output_length: WIZARD_A,
      max_tokens: WIZARD_B,
      agency_policy: ``,
      preset_id: `balanced`,
      model_profile_id: ``,
      stat_template: `world`,
      featured_characters: [],
      story_note: ``,
    }),
    v = worlds.data?.find((e) => e.id === p.world_id),
    y = React.useMemo(() => {
      let e = v?.data_json.starters ?? [],
        t = (settings.data?.starter_presets ?? []).filter((t) => !e.some((e) => e.name === t.name));
      return [
        ...e.map((e) => ({
          ...e,
          fromWorld: true,
        })),
        ...t.map((e) => ({
          ...e,
          fromWorld: false,
          confidence: undefined,
          canon_status: undefined,
          purpose: undefined,
        })),
      ];
    }, [v, settings.data]),
    b = y.find((e) => e.id === p.starter_id),
    mutation = useMutation({
      mutationFn: () =>
        apiPost(`/stories`, {
          ...p,
          world_id: p.world_id || null,
          avatar_id: p.avatar_id || null,
          model_profile_id: p.model_profile_id || null,
          starter_id: p.starter_id || null,
          starter_blueprint: b?.blueprint,
          stat_template: p.stat_template,
        }),
      onSuccess: async (e) => {
        (u(e),
          queryClient.invalidateQueries({
            queryKey: queryKeys.stories,
          }));
        let t = await apiGet(`/stories/${e.id}/context`);
        f(t.manifest);
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    }),
    S = async (e) => {
      if (l) {
        if (e)
          try {
            await apiPost(`/stories/${l.id}/start`);
          } catch (e) {
            toast(errorMessage(e), `danger`);
          }
        navigate(`/story/${l.id}`);
      }
    },
    C = () => c((e) => Math.min(e + 1, WIZARD_STEPS.length - 1)),
    w = s !== 0 || p.title.trim().length > 0;
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 py-8">
        <h1 className="mb-1 text-xl font-semibold">{msg("New story")}</h1>
        <ol className="mb-6 flex flex-wrap gap-1 text-xs" aria-label={msg("Steps")}>
          {WIZARD_STEPS.map((e, t) => (
            <li key={e}>
              <button
                onClick={() => !l && t <= s && c(t)}
                className={cn(
                  `rounded-full px-2.5 py-1`,
                  t === s ? `bg-accent text-accent-fg` : t < s ? `bg-panel-2 text-fg` : `text-faint`,
                )}
              >
                {t + 1}
                {". "}
                {e}
              </button>
            </li>
          ))}
        </ol>
        {l ? (
          <div className="space-y-4">
            <Callout
              tone="ok"
              title={msg("“{{v0}}” is ready", {
                v0: l.title,
              })}
            >
              {msg("This is the context the first request will use. Nothing has been sent to any model yet.")}
            </Callout>
            {d && <ContextManifest manifest={d} />}
            <div className="flex gap-2">
              <Button onClick={() => S(false)}>{msg("Open story and write the first move myself")}</Button>
              <Button variant="primary" onClick={() => S(true)}>
                <Icon.Play className="size-4" /> {msg("Generate the opening scene")}
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-5">
            {s === 0 && (
              <>
                <Field label={msg("Story title")}>
                  <Input
                    autoFocus
                    value={p.title}
                    onChange={(e) =>
                      g({
                        ...p,
                        title: e.target.value,
                      })
                    }
                    placeholder={msg("e.g. The Commoner's Gambit")}
                  />
                </Field>
                <Field
                  label={msg("Story note (optional)")}
                  hint={msg("Persistent instructions or facts for this story. Editable any time.")}
                >
                  <Textarea
                    value={p.story_note}
                    onChange={(e) =>
                      g({
                        ...p,
                        story_note: e.target.value,
                      })
                    }
                  />
                </Field>
              </>
            )}
            {s === 1 && (
              <>
                <Field label={msg("World")}>
                  <Select
                    value={p.world_id}
                    onChange={(e) =>
                      g({
                        ...p,
                        world_id: e.target.value,
                        starter_id: ``,
                        starting_location: ``,
                        featured_characters: [],
                      })
                    }
                  >
                    <option value="">{msg("No preset world (free-form)")}</option>
                    {worlds.data?.map((e) => (
                      <option value={e.id} key={e.id}>
                        {e.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                {v?.data_json.canon_note && <Callout tone="info">{v.data_json.canon_note}</Callout>}
                <div>
                  <p className="mb-1.5 text-xs font-medium text-muted">{msg("Starting mode")}</p>
                  <div className="grid gap-2 sm:grid-cols-3">
                    {y.map((e) => (
                      <button
                        onClick={() =>
                          g({
                            ...p,
                            starter_id: e.id,
                          })
                        }
                        className={cn(
                          `rounded-lg border p-3 text-left text-sm`,
                          p.starter_id === e.id
                            ? `border-accent bg-accent-soft`
                            : `border-line hover:border-line-strong`,
                        )}
                        key={e.id}
                      >
                        <p className="font-medium">{e.name}</p>
                        <p className="mt-1 line-clamp-3 text-xs text-muted">{e.purpose ?? e.blueprint}</p>
                        {e.canon_status && (
                          <Badge
                            tone="warn"
                            className="mt-1.5"
                            title={msg("From the lore pack; community-reconstructed, not official text")}
                          >
                            {msgKey(e.canon_status)}
                          </Badge>
                        )}
                      </button>
                    ))}
                  </div>
                  {b && (
                    <p className="mt-2 text-xs text-faint">
                      {msg("Opening blueprint (original scaffold, not quoted text):")} {b.blueprint}
                    </p>
                  )}
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label={msg("Starting location")}>
                    {v?.data_json.locations?.length ? (
                      <Select
                        value={p.starting_location}
                        onChange={(e) =>
                          g({
                            ...p,
                            starting_location: e.target.value,
                          })
                        }
                      >
                        <option value="">{msg("Let the narrator choose")}</option>
                        {v.data_json.locations.map((e) => (
                          <option key={e.id}>{e.name}</option>
                        ))}
                      </Select>
                    ) : (
                      <Input
                        value={p.starting_location}
                        onChange={(e) =>
                          g({
                            ...p,
                            starting_location: e.target.value,
                          })
                        }
                      />
                    )}
                  </Field>
                  <Field label={msg("Starting time")}>
                    <Input
                      value={p.starting_time}
                      onChange={(e) =>
                        g({
                          ...p,
                          starting_time: e.target.value,
                        })
                      }
                      placeholder={msg("e.g. early morning, first day of term")}
                    />
                  </Field>
                </div>
                {p.starter_id === `character_preview` && v && (
                  <Field label={msg("Featured characters")}>
                    <div className="grid max-h-56 grid-cols-3 gap-1.5 overflow-y-auto sm:grid-cols-4">
                      {v.data_json.characters?.map((e) => {
                        let t = p.featured_characters.includes(e.id);
                        return (
                          <button
                            onClick={() =>
                              g({
                                ...p,
                                featured_characters: t
                                  ? p.featured_characters.filter((t) => t !== e.id)
                                  : [...p.featured_characters, e.id],
                              })
                            }
                            className={cn(
                              `flex items-center gap-1.5 rounded-md border p-1 text-left text-xs`,
                              t ? `border-accent` : `border-line`,
                            )}
                            key={e.id}
                          >
                            <Portrait
                              assetId={portraitSlot(portraitMap.data?.[e.id])}
                              name={e.name}
                              className="size-7 shrink-0"
                            />

                            <span className="truncate">{e.name}</span>
                          </button>
                        );
                      })}
                    </div>
                  </Field>
                )}
              </>
            )}
            {s === 2 && (
              <>
                <div className="grid gap-2 sm:grid-cols-3">
                  <button
                    onClick={() =>
                      g({
                        ...p,
                        avatar_id: ``,
                      })
                    }
                    className={cn(
                      `rounded-lg border p-3 text-left text-sm`,
                      p.avatar_id ? `border-line` : `border-accent bg-accent-soft`,
                    )}
                  >
                    <p className="font-medium">{msg("No avatar")}</p>
                    <p className="text-xs text-muted">{msg("Describe yourself in play.")}</p>
                  </button>
                  {avatars.data?.map((e) => (
                    <button
                      onClick={() =>
                        g({
                          ...p,
                          avatar_id: e.id,
                        })
                      }
                      className={cn(
                        `flex gap-2 rounded-lg border p-3 text-left text-sm`,
                        p.avatar_id === e.id ? `border-accent bg-accent-soft` : `border-line`,
                      )}
                      key={e.id}
                    >
                      <UploadedImage path={e.portrait_path} name={e.name} className="size-10 shrink-0" />
                      <span className="min-w-0">
                        <span className="block truncate font-medium">{e.name}</span>
                        <span className="block truncate text-xs text-muted">
                          {e.profile_json.occupation || e.profile_json.title || msg("Avatar")}
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
                <Button variant="ghost" onClick={() => navigate(`/avatars/new`)}>
                  {msg("+ Create a new avatar (opens the editor)")}
                </Button>
                <Field
                  label={msg("Stat sheet")}
                  hint={msg("Ignored if the avatar defines its own stats. Fully editable later.")}
                >
                  <Select
                    value={p.stat_template}
                    onChange={(e) =>
                      g({
                        ...p,
                        stat_template: e.target.value,
                      })
                    }
                  >
                    <option value="world">{msg("World default (the world's own stats, or Fantasy basics)")}</option>
                    <option value="fantasy">{msg("Fantasy basics (HP, stamina, mana, level, XP, gold)")}</option>
                    <option value="minimal">{msg("Minimal")}</option>
                    <option value="none">{msg("None")}</option>
                  </Select>
                </Field>
              </>
            )}
            {s === 3 && (
              <>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label={msg("Narration preset")}>
                    <Select
                      value={p.preset_id}
                      onChange={(e) =>
                        g({
                          ...p,
                          preset_id: e.target.value,
                        })
                      }
                    >
                      {settings.data?.narration_presets.map((e) => (
                        <option value={e.id} key={e.id}>
                          {e.name}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label={msg("Model")}>
                    <Select
                      value={p.model_profile_id}
                      onChange={(e) =>
                        g({
                          ...p,
                          model_profile_id: e.target.value,
                        })
                      }
                    >
                      <option value="">{msg("Global default")}</option>
                      {providers.data?.profiles.map((e) => {
                        let t = providers.data.providers.find((t) => t.id === e.provider_id);
                        return (
                          <option value={e.id} key={e.id}>
                            {e.display_name}
                            {" — "}
                            {t?.display_name} {t?.is_cloud ? msg("(cloud)") : msg("(local)")}
                          </option>
                        );
                      })}
                    </Select>
                  </Field>
                  <Field label={msg("Tone")}>
                    <Input
                      value={p.tone}
                      onChange={(e) =>
                        g({
                          ...p,
                          tone: e.target.value,
                        })
                      }
                      placeholder={msg("e.g. hopeful with real danger")}
                    />
                  </Field>
                  <Field label={msg("Pacing")}>
                    <Select
                      value={p.pacing}
                      onChange={(e) =>
                        g({
                          ...p,
                          pacing: e.target.value,
                        })
                      }
                    >
                      <option value="">{msg("Narrator decides")}</option>
                      <option value="slow-burn, let scenes breathe">{msg("Slow-burn")}</option>
                      <option value="steady">{msg("Steady")}</option>
                      <option value="brisk, keep momentum">{msg("Brisk")}</option>
                    </Select>
                  </Field>
                  <Field label={msg("Output length")}>
                    <Select
                      value={p.output_length}
                      onChange={(e) =>
                        g({
                          ...p,
                          output_length: e.target.value,
                        })
                      }
                    >
                      <option value="">{msg("Model default")}</option>
                      <option value="short (1–2 paragraphs)">{msg("Short")}</option>
                      <option value={WIZARD_A}>{msg("Medium")}</option>
                      <option value="long (5–7 paragraphs)">{msg("Long")}</option>
                    </Select>
                  </Field>
                  <Field
                    label={msg("Max output tokens")}
                    hint={msg(
                      "A ceiling, not a target: you only pay for what is written. Applies to hosted models, and to local models with a window of 16,384 tokens or more; other local models keep their own setting.",
                    )}
                  >
                    <Input
                      type="number"
                      min={16}
                      max={32e3}
                      value={p.max_tokens ?? ``}
                      onChange={(e) =>
                        g({
                          ...p,
                          max_tokens: e.target.value ? Number(e.target.value) : null,
                        })
                      }
                    />
                  </Field>
                </div>
                <Field
                  label={msg("Player-agency note (optional)")}
                  hint={msg(
                    "Extra wishes for this story. The narrator's built-in rules against acting or speaking for your character always apply, so this can stay empty.",
                  )}
                >
                  <Textarea
                    value={p.agency_policy}
                    onChange={(e) =>
                      g({
                        ...p,
                        agency_policy: e.target.value,
                      })
                    }
                    className="min-h-14"
                    placeholder={msg("Leave empty unless you want something specific")}
                  />
                </Field>
                <p className="text-xs text-faint">
                  {msg(
                    "Content preferences (romance, violence, language) can be set in the story with /nsfw. The adult profile is off by default.",
                  )}
                </p>
              </>
            )}
            {s === 4 && (
              <div className="space-y-2 text-sm">
                <ReviewRow k={msg("Title")} v={p.title} />
                <ReviewRow k={msg("World")} v={v?.name ?? msg("None", {})} />
                <ReviewRow k={msg("Starting mode")} v={b?.name ?? msg("None", {})} />
                <ReviewRow
                  k={msg("Location / time")}
                  v={[p.starting_location, p.starting_time].filter(Boolean).join(` · `) || msg("Narrator decides", {})}
                />

                <ReviewRow
                  k={msg("Avatar")}
                  v={avatars.data?.find((e) => e.id === p.avatar_id)?.name ?? msg("None", {})}
                />
                <ReviewRow
                  k={msg("Preset")}
                  v={settings.data?.narration_presets.find((e) => e.id === p.preset_id)?.name ?? p.preset_id}
                />

                <ReviewRow
                  k={msg("Model")}
                  v={
                    providers.data?.profiles.find((e) => e.id === p.model_profile_id)?.display_name ??
                    msg("Global default", {})
                  }
                />
              </div>
            )}
            <div className="flex items-center gap-2 border-t border-line pt-4">
              {s > 0 && (
                <Button variant="ghost" onClick={() => c(s - 1)}>
                  <Icon.ArrowLeft className="size-4" /> {msg("Back")}
                </Button>
              )}
              <div className="ml-auto flex gap-2">
                {s < WIZARD_STEPS.length - 1 ? (
                  <Button variant="primary" onClick={C} disabled={!w}>
                    {msg("Next")} <Icon.ArrowRight className="size-4" />
                  </Button>
                ) : (
                  <Button
                    variant="primary"
                    loading={mutation.isPending}
                    disabled={!p.title.trim()}
                    onClick={() => mutation.mutate()}
                  >
                    <Icon.Eye className="size-4" /> {msg("Create & preview first context")}
                  </Button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ReviewRow({ k, v }) {
  return (
    <div className="flex gap-3 border-b border-line py-1.5">
      <span className="w-32 shrink-0 text-muted">{k}</span>
      <span>{v}</span>
    </div>
  );
}
