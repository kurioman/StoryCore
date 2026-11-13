// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useSettings } from "@/api/queries";
import { LANGUAGES, currentLanguage, msg, setLanguage } from "@/i18n";
import { Field, Select } from "@/components/ui";
import { useSaveSettings } from "@/features/settings/SettingsPage";

export function AppearanceSettings() {
  let settings = useSettings(),
    saveSettings = useSaveSettings();
  return (
    <div className="max-w-xl space-y-3">
      <Field
        label={msg("Interface language")}
        hint={msg("The language of menus, buttons and help. The story text has its own setting (Narration & context).")}
      >
        <Select
          value={currentLanguage}
          onChange={(e) => setLanguage(e.target.value)}
          aria-label={msg("Interface language")}
        >
          {LANGUAGES.map((l) => (
            <option value={l.code} key={l.code}>
              {l.label}
            </option>
          ))}
        </Select>
      </Field>
      <Field label={msg("Theme")}>
        <Select
          value={settings.data?.theme ?? `dark`}
          onChange={(e) =>
            saveSettings.mutate({
              theme: e.target.value,
            })
          }
        >
          <option value="dark">{msg("Dark (default)")}</option>
          <option value="light">{msg("Light")}</option>
        </Select>
      </Field>
      <Field label={msg("Story text font")} hint={msg("Applies to the narration; the interface font is unchanged.")}>
        <Select
          value={settings.data?.story_font ?? `sans`}
          onChange={(e) =>
            saveSettings.mutate({
              story_font: e.target.value,
            })
          }
          aria-label={msg("Story text font")}
        >
          <option value="sans">{msg("Modern sans-serif (default)")}</option>
          <option value="serif">{msg("Book serif")}</option>
        </Select>
      </Field>
      <Field label={msg("Reading size")} hint={msg("Size of the story text only; menus and panels stay as they are.")}>
        <Select
          value={settings.data?.reading_size ?? `comfortable`}
          onChange={(e) =>
            saveSettings.mutate({
              reading_size: e.target.value,
            })
          }
          aria-label={msg("Reading size")}
        >
          <option value="compact">{msg("Compact")}</option>
          <option value="comfortable">{msg("Comfortable (default)")}</option>
          <option value="large">{msg("Large")}</option>
        </Select>
      </Field>
      <Field
        label={msg("Dialogue")}
        hint={msg(
          "Dialogue emphasis keeps spoken words at full contrast with narration in a quieter grey, labels who speaks (when the scene analysis knows) and marks spoken paragraphs with a thin accent line. Classic keeps the earlier look.",
        )}
      >
        <Select
          value={settings.data?.dialogue_style ?? `emphasis`}
          onChange={(e) =>
            saveSettings.mutate({
              dialogue_style: e.target.value,
            })
          }
          aria-label={msg("Dialogue presentation")}
        >
          <option value="emphasis">{msg("Dialogue emphasis (default)")}</option>
          <option value="classic">{msg("Classic")}</option>
        </Select>
      </Field>
    </div>
  );
}
