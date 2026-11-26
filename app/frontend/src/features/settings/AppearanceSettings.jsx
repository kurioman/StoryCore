// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useSettings } from "@/api/queries";
import { LANGUAGES, currentLanguage, msg, setLanguage } from "@/i18n";
import { Field, Select } from "@/components/ui";
import { useSaveSettings } from "@/features/settings/SettingsPage";
import { DISPLAY_DEFAULTS, DISPLAY_RANGES, useDisplayPrefs } from "@/lib/displayPrefs";

export function AppearanceSettings() {
  let settings = useSettings(),
    saveSettings = useSaveSettings(),
    [display, setDisplay] = useDisplayPrefs();
  return (
    <div className="max-w-xl space-y-3">
      <section className="sc-av-card space-y-3" aria-labelledby="display-sizes">
        <div className="flex items-center">
          <p id="display-sizes" className="sc-av-label">
            {msg("Display sizes (this device)")}
          </p>
          <button type="button" className="ml-auto text-xs text-muted" onClick={() => setDisplay({ ...DISPLAY_DEFAULTS })}>
            {msg("Reset")}
          </button>
        </div>
        {[
          [`text`, msg("Story text")],
          [`portraits`, msg("Portraits")],
          [`composer`, msg("Writing box")],
        ].map(([k, label]) => (
          <label className="block text-sm" key={k}>
            <span className="flex">
              {label}
              <span className="ml-auto text-xs text-faint">{Math.round(display[k] * 100)} %</span>
            </span>
            <input
              type="range"
              min={DISPLAY_RANGES[k][0]}
              max={DISPLAY_RANGES[k][1]}
              step={0.05}
              value={display[k]}
              onChange={(e) => setDisplay({ ...display, [k]: Number(e.target.value) })}
              className="mt-1 w-full accent-[var(--c-accent)]"
            />
          </label>
        ))}
      </section>
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
      <Field
        label={msg("Place backgrounds")}
        hint={msg("The picture of the scene's place, softly behind the story text (when the world has one).")}
      >
        <Select
          value={settings.data?.scene_backdrops === false ? `off` : `on`}
          onChange={(e) => saveSettings.mutate({ scene_backdrops: e.target.value === `on` })}
          aria-label={msg("Place backgrounds")}
        >
          <option value="on">{msg("Shown (default)")}</option>
          <option value="off">{msg("Hidden")}</option>
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
          "Cinematic shows spoken words bright and narration in a clearly darker grey, as on OOC.AI. Dialogue emphasis does the same with a softer grey. Both label who speaks (when the scene analysis knows) and mark spoken paragraphs with a thin accent line. Classic keeps the earlier look.",
        )}
      >
        <Select
          value={settings.data?.dialogue_style ?? `cinematic`}
          onChange={(e) =>
            saveSettings.mutate({
              dialogue_style: e.target.value,
            })
          }
          aria-label={msg("Dialogue presentation")}
        >
          <option value="cinematic">{msg("Cinematic (default)")}</option>
          <option value="emphasis">{msg("Dialogue emphasis")}</option>
          <option value="classic">{msg("Classic")}</option>
        </Select>
      </Field>
    </div>
  );
}
