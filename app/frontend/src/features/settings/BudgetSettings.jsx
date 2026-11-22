// v0.6.2: spending cap for paid (online) models. Caps in dollars, 0 = no cap. Past the warning share the cost button
// turns orange; at the cap, paid requests stop (the reply shows why) until the cap is raised. Local models are free.
import { useSettings } from "@/api/queries";
import * as React from "react";
import { msg } from "@/i18n";
import { Button, Callout, Field, Input, Spinner } from "@/components/ui";
import { useSaveSettings } from "@/features/settings/SettingsPage";

function dollars(v) {
  let n = Number(String(v ?? ``).replace(`,`, `.`));
  return Number.isFinite(n) && n > 0 ? Math.round(n * 100) / 100 : 0;
}

export function BudgetSettings() {
  let settings = useSettings(),
    saveSettings = useSaveSettings(),
    [form, setForm] = React.useState(null);
  React.useEffect(() => {
    settings.data &&
      !form &&
      setForm({
        story: String(settings.data.budget_story_usd ?? 0),
        month: String(settings.data.budget_month_usd ?? 0),
        warn: String(settings.data.budget_warn_pct ?? 80),
      });
  }, [settings.data, form]);
  if (!form) return <Spinner />;
  let months = Object.entries(settings.data?.spend_by_month ?? {}).reverse().slice(0, 6);
  return (
    <div className="max-w-3xl space-y-5">
      <Callout tone="info">
        {msg(
          "Set a maximum to spend with online models. 0 means no cap. When a cap is reached, the app stops sending paid requests (your message is kept) until you raise it. Local models (LM Studio, Ollama) are free and never stopped.",
        )}
      </Callout>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label={msg("Cap per story ($)")}>
          <Input inputMode="decimal" value={form.story} onChange={(e) => setForm({ ...form, story: e.target.value })} />
        </Field>
        <Field label={msg("Cap per month ($)")}>
          <Input inputMode="decimal" value={form.month} onChange={(e) => setForm({ ...form, month: e.target.value })} />
        </Field>
        <Field label={msg("Warn me at (% of the cap)")}>
          <Input
            type="number"
            min={10}
            max={100}
            value={form.warn}
            onChange={(e) => setForm({ ...form, warn: e.target.value })}
          />
        </Field>
      </div>
      {months.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-semibold text-fg">{msg("Spent by month (all stories)")}</p>
          <dl className="grid max-w-xs grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 text-xs text-muted">
            {months.map(([m, v]) => (
              <React.Fragment key={m}>
                <dt>{m}</dt>
                <dd className="text-right">${Number(v).toFixed(3)}</dd>
              </React.Fragment>
            ))}
          </dl>
        </div>
      )}
      <Button
        variant="primary"
        loading={saveSettings.isPending}
        onClick={() =>
          saveSettings.mutate({
            budget_story_usd: dollars(form.story),
            budget_month_usd: dollars(form.month),
            budget_warn_pct: Math.min(100, Math.max(10, Math.round(Number(form.warn) || 80))),
          })
        }
      >
        {msg("Save")}
      </Button>
    </div>
  );
}
