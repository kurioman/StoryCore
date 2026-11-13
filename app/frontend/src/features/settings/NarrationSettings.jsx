// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/legacy";
import { useSettings } from "@/api/queries";
import * as React from "react";
import * as Icon from "lucide-react";
import { msg } from "@/i18n";
import { Button, Field, IconButton, Input, SectionTitle, Select, Spinner, Textarea, Toggle } from "@/components/ui";
import { useSaveSettings } from "@/features/settings/SettingsPage";

function PromptProfilePicker({ value, onChange }) {
  let query = useQuery({
      queryKey: [`prompt-profiles`],
      queryFn: () => apiGet(`/prompt-profiles`),
    }),
    r = query.data?.profiles.find((e) => e.id === query.data?.default);
  return (
    <Field
      label={msg("Player-agency prompt profile")}
      hint={msg(
        "How the 'never act for the player / no options menu' rules are placed in each request. The active profile is shown in the context inspector.",
      )}
    >
      <Select value={value ?? ``} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">
          {msg("Built-in default")}
          {r ? ` (${r.label})` : ``}
        </option>
        {query.data?.profiles.map((e) => (
          <option value={e.id} key={e.id}>
            {e.label}
          </option>
        ))}
      </Select>
    </Field>
  );
}

// v1.8: language of the story text (the narrator writes in it; the interface language is separate)
function NarrationLanguagePicker({ value, onChange }) {
  const languages = useQuery({ queryKey: [`narration-languages`], queryFn: () => apiGet(`/narration-languages`) });
  return (
    <Field
      label={msg("Story language")}
      hint={msg(
        "The language the narrator writes the story in. Lore and instructions stay in English; character names and portrait tags are kept as they are. Each story can override it.",
      )}
    >
      <Select value={value ?? `en`} onChange={(e) => onChange(e.target.value)}>
        {(languages.data?.languages ?? [{ code: `en`, label: `English` }]).map((l) => (
          <option value={l.code} key={l.code}>
            {msg(l.label)}
          </option>
        ))}
      </Select>
    </Field>
  );
}

export function NarrationSettings() {
  let settings = useSettings(),
    saveSettings = useSaveSettings(),
    [n, r] = React.useState(null);
  return (
    React.useEffect(() => {
      settings.data && !n && r(structuredClone(settings.data));
    }, [settings.data, n]),
    n ? (
      <div className="max-w-3xl space-y-6">
        <section className="grid gap-3 sm:grid-cols-2">
          <Field
            label={msg("Context budget (tokens)")}
            hint={msg("Upper bound for each request; the model's own limit applies if smaller.")}
          >
            <Input
              type="number"
              value={n.context_budget_tokens}
              onChange={(e) =>
                r({
                  ...n,
                  context_budget_tokens: Number(e.target.value),
                })
              }
            />
          </Field>
          <Field
            label={msg("Reserved for the reply (tokens)")}
            hint={msg(
              "Kept free of story context when planning a request. It does not limit the reply: Max output tokens does.",
            )}
          >
            <Input
              type="number"
              value={n.reserve_output_tokens}
              onChange={(e) =>
                r({
                  ...n,
                  reserve_output_tokens: Number(e.target.value),
                })
              }
            />
          </Field>
          <Field label={msg("Always keep at least N recent messages")}>
            <Input
              type="number"
              value={n.recent_messages_min}
              onChange={(e) =>
                r({
                  ...n,
                  recent_messages_min: Number(e.target.value),
                })
              }
            />
          </Field>
          <Field label={msg("Warn when context reaches (%)")}>
            <Input
              type="number"
              value={Math.round(n.context_warning_ratio * 100)}
              onChange={(e) =>
                r({
                  ...n,
                  context_warning_ratio: Number(e.target.value) / 100,
                })
              }
            />
          </Field>
          <div className="sm:col-span-2">
            <Toggle
              checked={n.enter_to_send}
              onChange={(e) =>
                r({
                  ...n,
                  enter_to_send: e,
                })
              }
              label={msg("Enter sends the message")}
              description={msg("Off: Ctrl+Enter sends and Enter adds a new line.")}
            />
          </div>
        </section>
        <NarrationLanguagePicker
          value={n.narration_language ?? `en`}
          onChange={(e) =>
            r({
              ...n,
              narration_language: e,
            })
          }
        />
        <PromptProfilePicker
          value={n.narrator_prompt_profile ?? null}
          onChange={(e) =>
            r({
              ...n,
              narrator_prompt_profile: e,
            })
          }
        />
        <Field
          label={msg("Default narrator prompt")}
          hint={msg("Used for stories without a world prompt (a world's lore pack can ship its own narrative prompt).")}
        >
          <Textarea
            value={n.default_system_prompt}
            onChange={(e) =>
              r({
                ...n,
                default_system_prompt: e.target.value,
              })
            }
            className="min-h-36"
          />
        </Field>
        <section>
          <SectionTitle
            action={
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  r({
                    ...n,
                    narration_presets: [
                      ...n.narration_presets,
                      {
                        id: `preset_${Date.now()}`,
                        name: `New preset`,
                        instructions: ``,
                      },
                    ],
                  })
                }
              >
                <Icon.Plus className="size-3.5" /> {msg("Add preset")}
              </Button>
            }
          >
            {msg("Narration presets")}
          </SectionTitle>
          <div className="space-y-2">
            {n.narration_presets.map((e, t) => (
              <div className="flex gap-2 rounded-md border border-line p-2" key={e.id}>
                <Input
                  value={e.name}
                  onChange={(e) =>
                    r({
                      ...n,
                      narration_presets: n.narration_presets.map((n, r) =>
                        r === t
                          ? {
                              ...n,
                              name: e.target.value,
                            }
                          : n,
                      ),
                    })
                  }
                  className="w-40"
                  aria-label={msg("Preset name")}
                />
                <Textarea
                  value={e.instructions}
                  onChange={(e) =>
                    r({
                      ...n,
                      narration_presets: n.narration_presets.map((n, r) =>
                        r === t
                          ? {
                              ...n,
                              instructions: e.target.value,
                            }
                          : n,
                      ),
                    })
                  }
                  className="min-h-12 flex-1"
                  aria-label={msg("Preset instructions")}
                />
                <IconButton
                  label={msg("Remove preset")}
                  onClick={() =>
                    r({
                      ...n,
                      narration_presets: n.narration_presets.filter((e, n) => n !== t),
                    })
                  }
                >
                  <Icon.Trash className="size-3.5" />
                </IconButton>
              </div>
            ))}
          </div>
        </section>
        <section>
          <SectionTitle
            action={
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  r({
                    ...n,
                    starter_presets: [
                      ...n.starter_presets,
                      {
                        id: `starter_${Date.now()}`,
                        name: `Custom start`,
                        blueprint: ``,
                      },
                    ],
                  })
                }
              >
                <Icon.Plus className="size-3.5" /> {msg("Add starter")}
              </Button>
            }
          >
            {msg("Generic starter blueprints")}
          </SectionTitle>
          <p className="mb-2 text-xs text-faint">
            {msg(
              "Used by the new-story wizard in addition to starters from an imported world. These are original scaffolds.",
            )}
          </p>
          <div className="space-y-2">
            {n.starter_presets.map((e, t) => (
              <div className="flex gap-2 rounded-md border border-line p-2" key={e.id}>
                <Input
                  value={e.name}
                  onChange={(e) =>
                    r({
                      ...n,
                      starter_presets: n.starter_presets.map((n, r) =>
                        r === t
                          ? {
                              ...n,
                              name: e.target.value,
                            }
                          : n,
                      ),
                    })
                  }
                  className="w-40"
                  aria-label={msg("Starter name")}
                />
                <Textarea
                  value={e.blueprint}
                  onChange={(e) =>
                    r({
                      ...n,
                      starter_presets: n.starter_presets.map((n, r) =>
                        r === t
                          ? {
                              ...n,
                              blueprint: e.target.value,
                            }
                          : n,
                      ),
                    })
                  }
                  className="min-h-12 flex-1"
                  aria-label={msg("Blueprint")}
                />
                <IconButton
                  label={msg("Remove starter")}
                  onClick={() =>
                    r({
                      ...n,
                      starter_presets: n.starter_presets.filter((e, n) => n !== t),
                    })
                  }
                >
                  <Icon.Trash className="size-3.5" />
                </IconButton>
              </div>
            ))}
          </div>
        </section>
        <Button
          variant="primary"
          loading={saveSettings.isPending}
          onClick={() =>
            saveSettings.mutate({
              context_budget_tokens: n.context_budget_tokens,
              reserve_output_tokens: n.reserve_output_tokens,
              recent_messages_min: n.recent_messages_min,
              context_warning_ratio: n.context_warning_ratio,
              enter_to_send: n.enter_to_send,
              default_system_prompt: n.default_system_prompt,
              narration_presets: n.narration_presets,
              starter_presets: n.starter_presets,
              narrator_prompt_profile: n.narrator_prompt_profile ?? null,
              narration_language: n.narration_language ?? `en`,
            })
          }
        >
          {msg("Save")}
        </Button>
      </div>
    ) : (
      <Spinner />
    )
  );
}
