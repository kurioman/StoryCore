// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, errorMessage, apiUpload } from "@/api/legacy";
import * as React from "react";
import * as Icon from "lucide-react";
import { msg, msgKey } from "@/i18n";
import { Badge, Button, Callout, ErrorCallout, SectionTitle, Spinner, useUi } from "@/components/ui";
import { cn, downloadJson, fmtBytes, readFileText, timeAgo } from "@/lib/util";

export function DataSettings() {
  let query = useQuery({
      queryKey: [`paths`],
      queryFn: () => apiGet(`/system/paths`),
    }),
    t = useQuery({
      queryKey: [`health`],
      queryFn: () => apiGet(`/health`),
    }),
    n = useQuery({
      queryKey: [`backups`],
      queryFn: () => apiGet(`/backups`),
    }),
    mutation = useMutation({
      mutationFn: () => apiGet(`/system/integrity`),
    }),
    i = useQuery({
      queryKey: [`logs`],
      queryFn: () => apiGet(`/system/logs?lines=200`),
      enabled: false,
    }),
    queryClient = useQueryClient(),
    { toast, confirm } = useUi(),
    [c, l] = React.useState({}),
    u = React.useRef(null),
    d = React.useRef(null),
    f = useMutation({
      mutationFn: () => apiPost(`/backups`),
      onSuccess: (e) => {
        (queryClient.invalidateQueries({
          queryKey: [`backups`],
        }),
          toast(
            msg("Backup created: {{v0}} ({{v1}})", {
              v0: e.name,
              v1: fmtBytes(e.size),
            }),
          ));
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    });
  return (
    <div className="max-w-3xl space-y-6">
      <section>
        <SectionTitle>{msg("Where your data lives")}</SectionTitle>
        {query.data ? (
          <dl className="grid grid-cols-[8rem_1fr] gap-y-1 text-xs">
            {Object.entries(query.data).map(([e, t]) => (
              <div className="contents" key={e}>
                <dt className="capitalize text-faint">{msgKey(e)}</dt>
                <dd className="break-all font-mono text-muted">{t}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <Spinner />
        )}
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            onClick={() =>
              apiPost(`/system/open-data-folder`).then(
                (e) => !e.ok && toast(e.error ?? msg("Could not open", {}), `warn`),
              )
            }
          >
            <Icon.FolderOpen className="size-3.5" /> {msg("Open data folder")}
          </Button>
          {t.data && (
            <Badge tone={t.data.secrets_backend === `keyring` ? `ok` : `warn`}>
              {msg("API keys:")}{" "}
              {t.data.secrets_backend === `keyring` ? msg("OS credential store") : t.data.secrets_backend}
            </Badge>
          )}
        </div>
        {t.data?.secrets_warning && (
          <Callout tone="warn" className="mt-2">
            {t.data.secrets_warning}
          </Callout>
        )}
      </section>
      <section>
        <SectionTitle>{msg("Full backups")}</SectionTitle>
        <p className="mb-2 text-xs text-muted">
          {msg(
            "A full backup contains the database (all stories, journal, avatars, commands, settings) and uploaded images. API keys are never included.",
          )}
        </p>
        <div className="mb-3 flex flex-wrap gap-2">
          <Button variant="primary" loading={f.isPending} onClick={() => f.mutate()}>
            {msg("Back up now")}
          </Button>
          <Button onClick={() => u.current?.click()}>
            <Icon.Upload className="size-4" /> {msg("Upload a backup…")}
          </Button>
          <input
            ref={u}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={async (e) => {
              let t = e.target.files?.[0];
              if (!t) return;
              let n = new FormData();
              n.append(`file`, t);
              try {
                let e = await apiUpload(`/backups/upload`, n);
                (l((t) => ({
                  ...t,
                  [e.name]: e.verify,
                })),
                  queryClient.invalidateQueries({
                    queryKey: [`backups`],
                  }));
              } catch (e) {
                toast(errorMessage(e), `danger`);
              }
              e.target.value = ``;
            }}
          />
        </div>
        {n.data?.last_backup_at && (
          <p className="mb-2 text-xs text-faint">
            {msg("Last backup")} {timeAgo(n.data.last_backup_at)}.
          </p>
        )}
        <div className="space-y-1.5">
          {n.data?.backups.map((e) => (
            <div className="rounded-md border border-line px-3 py-2 text-xs" key={e.name}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono">{e.name}</span>
                <span className="text-faint">{fmtBytes(e.size)}</span>
                <div className="ml-auto flex gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={async () =>
                      l({
                        ...c,
                        [e.name]: await apiPost(`/backups/${e.name}/verify`),
                      })
                    }
                  >
                    <Icon.ShieldCheck className="size-3.5" /> {msg("Test restore")}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={msg("Download {{v0}}", {
                      v0: e.name,
                    })}
                    title={msg("Download")}
                    onClick={() => (window.location.href = `/api/backups/${e.name}/download`)}
                  >
                    <Icon.Download className="size-3.5" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={async () => {
                      if (
                        await confirm({
                          title: msg("Restore this backup?"),
                          body: msg(
                            "ALL current data is replaced by the backup. A safety backup of the current data is created first.",
                          ),
                          danger: true,
                          confirmLabel: msg("Restore"),
                        })
                      )
                        try {
                          (await apiPost(`/backups/${e.name}/restore`, {
                            confirm: true,
                          }),
                            toast(msg("Backup restored — reloading")),
                            setTimeout(() => window.location.reload(), 800));
                        } catch (e) {
                          toast(errorMessage(e), `danger`);
                        }
                    }}
                  >
                    {msg("Restore")}
                  </Button>
                </div>
              </div>
              {c[e.name] && (
                <p className={cn(`mt-1`, c[e.name].ok ? `text-ok` : `text-danger`)}>
                  {msg("Integrity:")} {c[e.name].integrity} {msg("· schema")} {c[e.name].schema_revision}
                  {" · "}
                  {Object.entries(c[e.name].counts)
                    .map(([e, t]) => `${t} ${e}`)
                    .join(`, `)}
                  {" · "}
                  {c[e.name].uploads} {msg("uploaded files")}
                </p>
              )}
            </div>
          ))}
        </div>
      </section>
      <section>
        <SectionTitle>{msg("Exports")}</SectionTitle>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            onClick={async () => downloadJson(`storycore-commands.json`, await apiGet(`/commands/export`))}
          >
            {msg("Command library (JSON)")}
          </Button>
          <Button
            size="sm"
            onClick={async () => downloadJson(`storycore-local-canon.json`, await apiGet(`/local-canon/export`))}
          >
            {msg("Local canon (JSON)")}
          </Button>
          <Button size="sm" onClick={() => (window.location.href = `/api/local-canon/export?fmt=md`)}>
            {msg("Local canon (Markdown)")}
          </Button>
          <Button size="sm" onClick={async () => downloadJson(`storycore-notes.json`, await apiGet(`/notes/export`))}>
            {msg("Notes (JSON)")}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => d.current?.click()}>
            <Icon.Upload className="size-3.5" /> {msg("Import local canon")}
          </Button>
          <input
            ref={d}
            type="file"
            accept=".json"
            className="hidden"
            onChange={async (e) => {
              let t = e.target.files?.[0];
              if (t)
                try {
                  let e = await apiPost(`/local-canon/import`, JSON.parse(await readFileText(t)));
                  toast(
                    msg("{{v0}} local-canon entries imported as pending", {
                      v0: e.added,
                    }),
                  );
                } catch (e) {
                  toast(errorMessage(e), `danger`);
                }
            }}
          />
        </div>
        <p className="mt-1 text-xs text-faint">
          {msg("Story packages and avatars are exported from their own menus.")}
        </p>
      </section>
      <section>
        <SectionTitle>{msg("Report a problem")}</SectionTitle>
        <p className="mb-2 text-xs text-muted">
          {msg(
            "Makes a zip to send to whoever helps you with StoryCore: versions, the app log, settings, your AI providers and models, the lore pack check and figures about recent replies. Never inside: API keys, story text, story titles, notes or lore content.",
          )}
        </p>
        <Button
          size="sm"
          variant="primary"
          onClick={() => {
            window.location.href = `/api/system/bug-report`;
            toast(msg("Preparing the bug report…"));
          }}
        >
          <Icon.Download className="size-3.5" /> {msg("Export a bug report")}
        </Button>
      </section>
      <section>
        <SectionTitle>{msg("Maintenance")}</SectionTitle>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" loading={mutation.isPending} onClick={() => mutation.mutate()}>
            {msg("Check database integrity")}
          </Button>
          <Button size="sm" onClick={() => i.refetch()}>
            {msg("View recent logs")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={async () => {
              (await apiPost(`/system/clear-logs`), toast(msg("Logs cleared")), i.refetch());
            }}
          >
            {msg("Clear logs")}
          </Button>
        </div>
        {mutation.data && (
          <Callout tone={mutation.data.ok ? `ok` : `danger`} className="mt-2">
            {msg("SQLite:")} {mutation.data.sqlite} {msg("· foreign-key issues:")}{" "}
            {mutation.data.foreign_key_violations} {msg("· dangling branch heads:")}{" "}
            {mutation.data.dangling_branch_heads} {msg("· dangling parents:")} {mutation.data.dangling_message_parents}
          </Callout>
        )}
        {mutation.isError && <ErrorCallout error={mutation.error} />}
        {i.data && (
          <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-md border border-line bg-panel-2 p-2 text-[11px] text-muted">
            {i.data.lines.join(`
`) || msg("Log is empty.")}
          </pre>
        )}
      </section>
    </div>
  );
}
