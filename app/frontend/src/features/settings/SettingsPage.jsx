// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useQueryClient, useMutation } from "@tanstack/react-query";
import { apiPut, errorMessage } from "@/api/legacy";
import { queryKeys } from "@/api/queries";
import { msg } from "@/i18n";
import { AdvancedProviders } from "@/features/settings/Providers";
import { AppearanceSettings } from "@/features/settings/AppearanceSettings";
import { DataSettings } from "@/features/settings/DataSettings";
import { GlobalNoteSettings } from "@/features/settings/GlobalNoteSettings";
import { MemorySettings } from "@/features/settings/MemorySettings";
import { BudgetSettings } from "@/features/settings/BudgetSettings";
import { NarrationSettings } from "@/features/settings/NarrationSettings";
import { OllamaModelsPage } from "@/features/settings/OllamaModels";
import { cn } from "@/lib/util";
import { navigate } from "@/lib/router";
import { useUi } from "@/components/ui";
import { PhonePanel } from "@/features/mobile/PhonePanel";
import { IS_REMOTE } from "@/lib/remote";

// built when shown (msg() needs the chosen language); a paired phone only gets its own preferences (v0.5)
function settingsTabs() {
  let tabs = [
  {
    id: `providers`,
    label: msg("Providers & models"),
  },
  {
    id: `ollama`,
    label: msg("Ollama models"),
  },
  {
    id: `budget`,
    label: msg("Budget"),
  },
  {
    id: `generation`,
    label: msg("Narration & context"),
  },
  {
    id: `memory`,
    label: msg("Memory capture"),
  },
  {
    id: `notes`,
    label: msg("Global note"),
  },
  {
    id: `appearance`,
    label: msg("Appearance"),
  },
  {
    id: `phone`,
    label: msg("Play on a phone"),
  },
  {
    id: `data`,
    label: msg("Data & backups"),
  },
];
  return IS_REMOTE ? tabs.filter((t) => PHONE_TABS.includes(t.id)) : tabs;
}

var PHONE_TABS = [`generation`, `memory`, `notes`, `appearance`];

export function SettingsPage({ tab }) {
  let SETTINGS_TABS = settingsTabs();
  if (!SETTINGS_TABS.some((t) => t.id === tab)) tab = SETTINGS_TABS[0].id;
  return (
    <div className="flex h-full min-h-0 flex-col md:flex-row">
      <nav
        className="flex shrink-0 gap-1 overflow-x-auto border-b border-line p-2 md:w-52 md:flex-col md:border-b-0 md:border-r md:p-3"
        aria-label={msg("Settings sections")}
      >
        <h1 className="hidden px-2 pb-2 text-sm font-semibold md:block">{msg("Settings")}</h1>
        {SETTINGS_TABS.map((t) => (
          <button
            onClick={() => navigate(`/settings/${t.id}`)}
            className={cn(
              `whitespace-nowrap rounded-md px-2.5 py-1.5 text-left text-[13px]`,
              tab === t.id ? `bg-panel-2 text-fg` : `text-muted hover:text-fg`,
            )}
            key={t.id}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <div className="min-h-0 flex-1 overflow-y-auto p-5 md:p-8">
        <h2 className="mb-4 text-lg font-semibold">
          {SETTINGS_TABS.find((t) => t.id === tab)?.label ?? msg("Settings")}
        </h2>
        {tab === `providers` && <AdvancedProviders />}
        {tab === `ollama` && <OllamaModelsPage />}
        {tab === `generation` && <NarrationSettings />}
        {tab === `memory` && <MemorySettings />}
        {tab === `budget` && <BudgetSettings />}
        {tab === `notes` && <GlobalNoteSettings />}
        {tab === `appearance` && <AppearanceSettings />}
        {tab === `phone` && <PhonePanel />}
        {tab === `data` && <DataSettings />}
      </div>
    </div>
  );
}

export function useSaveSettings() {
  let queryClient = useQueryClient(),
    { toast } = useUi();
  return useMutation({
    mutationFn: (e) => apiPut(`/settings`, e),
    onSuccess: () => {
      (queryClient.invalidateQueries({
        queryKey: queryKeys.settings,
      }),
        queryClient.invalidateQueries({
          queryKey: [`context`],
        }),
        toast(msg("Settings saved")));
    },
    onError: (e) => toast(errorMessage(e), `danger`),
  });
}
