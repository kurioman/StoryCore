// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useProviders, queryKeys } from "@/api/queries";
import { useQueryClient, useMutation, useQuery } from "@tanstack/react-query";
import { apiPost, apiGet, apiStream, errorMessage } from "@/api/legacy";
import * as React from "react";
import * as Icon from "lucide-react";
import { msg } from "@/i18n";
import { Badge, Button, Callout, EmptyState, Input, Modal, SectionTitle, Spinner, useUi } from "@/components/ui";
import { fmtBytes } from "@/lib/util";

export function OllamaModelsPage() {
  let e = useProviders(),
    queryClient = useQueryClient(),
    { toast, confirm } = useUi(),
    i = e.data?.providers.find((e) => e.provider_type === `ollama`),
    mutation = useMutation({
      mutationFn: () => apiPost(`/ollama/quick-setup`),
      onSuccess: () =>
        queryClient.invalidateQueries({
          queryKey: queryKeys.providers,
        }),
    }),
    query = useQuery({
      queryKey: [`ollama-status`, i?.id],
      enabled: !!i,
      queryFn: () => apiPost(`/providers/${i.id}/test`, {}),
      refetchInterval: 15e3,
    }),
    s = useQuery({
      queryKey: [`models`, i?.id],
      enabled: !!i && !!query.data?.ok,
      queryFn: () => apiGet(`/providers/${i.id}/models`),
    }),
    c = useQuery({
      queryKey: [`ollama-curated`],
      queryFn: () => apiGet(`/ollama/curated`),
    }),
    [l, u] = React.useState(``),
    [d, f] = React.useState({}),
    [p, g] = React.useState(null);
  React.useEffect(() => {
    apiGet(`/ollama/pulls`).then((e) => {
      for (let t of e.jobs) t.status === `running` && y(t.id);
      f((t) => ({
        ...Object.fromEntries(e.jobs.map((e) => [e.id, e])),
        ...t,
      }));
    });
  }, []);
  let v = React.useRef(new Set()),
    y = (e) => {
      v.current.has(e) ||
        (v.current.add(e),
        apiStream(`/ollama/pulls/${e}/stream`, (e) => {
          ((e.type === `progress` || e.type === `done`) &&
            f((t) => ({
              ...t,
              [e.id]: e,
            })),
            e.type === `done` &&
              (queryClient.invalidateQueries({
                queryKey: [`models`, i?.id],
              }),
              e.status === `succeeded`
                ? toast(
                    msg("Downloaded {{v0}}", {
                      v0: e.model,
                    }),
                  )
                : e.status === `failed` &&
                  toast(
                    msg("Download failed: {{v0}}", {
                      v0: e.error,
                    }),
                    `danger`,
                  )));
        }).finally(() => v.current.delete(e)));
    },
    b = async (e) => {
      if (i)
        try {
          let t = await apiPost(`/ollama/${i.id}/pull`, {
            model: e,
          });
          (f((e) => ({
            ...e,
            [t.id]: t,
          })),
            y(t.id),
            u(``));
        } catch (e) {
          toast(errorMessage(e), `danger`);
        }
    },
    x = async (e) => {
      if (i)
        try {
          let r = null;
          try {
            r = (await apiGet(`/ollama/${i.id}/show?model=${encodeURIComponent(e)}`)).context_length ?? null;
          } catch {}
          (await apiPost(`/model-profiles`, {
            provider_id: i.id,
            model_id: e,
            context_limit: r,
            generation_settings: r
              ? {
                  context_size: Math.min(r, 8192),
                }
              : {},
          }),
            queryClient.invalidateQueries({
              queryKey: queryKeys.providers,
            }),
            toast(
              msg("{{v0}} is now selectable as a model", {
                v0: e,
              }),
            ));
        } catch (e) {
          toast(errorMessage(e), `danger`);
        }
    },
    S = new Set(e.data?.profiles.filter((e) => e.provider_id === i?.id).map((e) => e.model_id));
  if (!i)
    return (
      <div className="max-w-2xl space-y-3">
        <p className="text-sm text-muted">
          {msg(
            "Ollama runs open models on your own computer, so nothing leaves it. Providers & models has a short setup guide.",
          )}
        </p>
        <Button variant="primary" loading={mutation.isPending} onClick={() => mutation.mutate()}>
          {msg("Set up local Ollama (localhost:11434)")}
        </Button>
      </div>
    );
  let C = Object.values(d)
    .filter((e) => e.status === `running` || e.status === `failed`)
    .sort((e) => (e.status === `running` ? -1 : 1));
  return (
    <div className="max-w-3xl space-y-5">
      {query.isLoading && <Spinner />}
      {query.data && !query.data.ok && (
        <Callout tone="warn" title={msg("Ollama is not reachable")}>
          <p>{query.data.message}</p>
          <p className="mt-1">
            {msg("Install it from")}{" "}
            <a className="text-accent underline" href="https://ollama.com/download" target="_blank" rel="noreferrer">
              {msg("ollama.com/download")} <Icon.ExternalLink className="inline size-3" />
            </a>{" "}
            {msg(
              "and start it. Cloud providers keep working in the meantime. The endpoint can be changed in Providers.",
            )}
          </p>
        </Callout>
      )}
      {query.data?.ok && <Callout tone="ok">{query.data.message}</Callout>}
      <section>
        <SectionTitle>{msg("Download a model")}</SectionTitle>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            (e.preventDefault(), l.trim() && b(l.trim()));
          }}
        >
          <Input
            value={l}
            onChange={(e) => u(e.target.value)}
            placeholder={msg("Model name or tag, e.g. llama3.1:8b")}
            disabled={!query.data?.ok}
            aria-label={msg("Model to download")}
          />
          <Button variant="primary" type="submit" disabled={!query.data?.ok || !l.trim()}>
            <Icon.Download className="size-4" /> {msg("Download in Ollama")}
          </Button>
        </form>
        <p className="mt-1 text-[11px] text-faint">
          {msg("Ollama's local API has no searchable catalogue, so names are entered manually. Browse")}{" "}
          <a className="underline" href="https://ollama.com/library" target="_blank" rel="noreferrer">
            {msg("ollama.com/library")}
          </a>
          {msg(". Download size is reported by Ollama once the download starts; it is unknown before that.")}
        </p>
        {c.data && (
          <div className="mt-3 rounded-md border border-line p-3">
            <p className="mb-2 flex items-center gap-1 text-xs text-muted">
              <Icon.Info className="size-3.5" /> {c.data.source}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {c.data.models.map((e) => (
                <Button
                  size="sm"
                  variant="subtle"
                  title={e.note}
                  disabled={!query.data?.ok}
                  onClick={() => u(e.name)}
                  key={e.name}
                >
                  {e.name}
                </Button>
              ))}
            </div>
          </div>
        )}
      </section>
      {C.length > 0 && (
        <section>
          <SectionTitle>{msg("Downloads")}</SectionTitle>
          <div className="space-y-2">
            {C.map((e) => {
              let t = e.progress.total ? (e.progress.completed ?? 0) / e.progress.total : null;
              return (
                <div className="rounded-md border border-line p-3 text-sm" key={e.id}>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{e.model}</span>
                    <Badge tone={e.status === `failed` ? `danger` : `info`}>{e.status}</Badge>
                    <span className="text-xs text-faint">{e.progress.status}</span>
                    {e.status === `running` ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="ml-auto"
                        onClick={() => apiPost(`/ollama/pulls/${e.id}/cancel`)}
                      >
                        <Icon.Square className="size-3" /> {msg("Cancel")}
                      </Button>
                    ) : (
                      <Button size="sm" className="ml-auto" onClick={() => b(e.model)}>
                        {msg("Retry")}
                      </Button>
                    )}
                  </div>
                  {t !== null && e.status === `running` && (
                    <>
                      <div
                        className="mt-2 h-1.5 overflow-hidden rounded-full bg-line"
                        role="progressbar"
                        aria-valuenow={Math.round(t * 100)}
                        aria-valuemin={0}
                        aria-valuemax={100}
                      >
                        <div
                          className="h-full bg-accent transition-all"
                          style={{
                            width: `${t * 100}%`,
                          }}
                        />
                      </div>
                      <p className="mt-1 text-xs text-faint">
                        {fmtBytes(e.progress.completed)} {msg("of")} {fmtBytes(e.progress.total)}
                        {" ("}
                        {Math.round(t * 100)}
                        {msg("%) — make sure you have enough free disk space.")}
                      </p>
                    </>
                  )}
                  {e.error && <p className="mt-1 text-xs text-danger">{e.error}</p>}
                </div>
              );
            })}
          </div>
          <p className="mt-1 text-[11px] text-faint">
            {msg("Cancel closes the download request; Ollama may keep partial data and resume it if you retry.")}
          </p>
        </section>
      )}
      <section>
        <SectionTitle>{msg("Installed models")}</SectionTitle>
        {s.isLoading && <Spinner />}
        {s.data?.models.length === 0 && <EmptyState title={msg("No models installed yet")} />}
        <div className="space-y-1.5">
          {s.data?.models.map((e) => (
            <div
              className="flex flex-wrap items-center gap-2 rounded-md border border-line px-3 py-2 text-sm"
              key={e.id}
            >
              <span className="font-medium">{e.id}</span>
              <span className="text-xs text-faint">
                {[e.details?.parameter_size, e.details?.quantization, e.details?.family].filter(Boolean).join(` · `)}
                {" · "}
                {fmtBytes(e.size_bytes)}
              </span>
              {s.data?.running?.includes(e.id) && <Badge tone="ok">{msg("loaded in memory")}</Badge>}
              <div className="ml-auto flex gap-1">
                <Button size="sm" variant="ghost" onClick={() => g(e.id)}>
                  {msg("Details")}
                </Button>
                {S.has(e.id) ? (
                  <Badge tone="accent">{msg("in model list")}</Badge>
                ) : (
                  <Button size="sm" onClick={() => x(e.id)}>
                    <Icon.Plus className="size-3.5" /> {msg("Use in stories")}
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={msg("Delete {{v0}} from Ollama", {
                    v0: e.id,
                  })}
                  title={msg("Delete {{v0}} from Ollama", {
                    v0: e.id,
                  })}
                  onClick={async () => {
                    if (
                      await confirm({
                        title: msg("Delete {{v0}} from Ollama?", {
                          v0: e.id,
                        }),
                        body: msg(
                          "This removes the model files from disk ({{v0}}). You would need to download it again to use it.",
                          {
                            v0: fmtBytes(e.size_bytes),
                          },
                        ),
                        confirmLabel: msg("Delete model"),
                        danger: true,
                      })
                    )
                      try {
                        (await apiPost(`/ollama/${i.id}/delete`, {
                          model: e.id,
                          confirm: true,
                        }),
                          queryClient.invalidateQueries({
                            queryKey: [`models`, i.id],
                          }),
                          toast(`${e.id} deleted`));
                      } catch (e) {
                        toast(errorMessage(e), `danger`);
                      }
                  }}
                >
                  <Icon.Trash className="size-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      </section>
      {p && <OllamaShowDialog pid={i.id} model={p} onClose={() => g(null)} />}
    </div>
  );
}

function OllamaShowDialog({ pid, model, onClose }) {
  let query = useQuery({
    queryKey: [`ollama-show`, model],
    queryFn: () => apiGet(`/ollama/${pid}/show?model=${encodeURIComponent(model)}`),
  });
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      title={model}
      description={msg("Reported by Ollama (/api/show).")}
    >
      {query.isLoading && <Spinner />}
      {query.data && (
        <div className="space-y-2 text-sm">
          <p>
            {msg("Context length:")} {query.data.context_length?.toLocaleString() ?? msg("not reported")}
          </p>
          {query.data.capabilities.length > 0 && (
            <p>
              {msg("Capabilities:")} {query.data.capabilities.join(`, `)}
            </p>
          )}
          <pre className="whitespace-pre-wrap rounded border border-line bg-panel-2 p-2 text-xs text-muted">
            {JSON.stringify(query.data.details, null, 2)}
          </pre>
          {query.data.parameters && (
            <pre className="whitespace-pre-wrap rounded border border-line bg-panel-2 p-2 text-xs text-muted">
              {query.data.parameters}
            </pre>
          )}
          {query.data.license && (
            <p className="text-xs text-faint">
              {msg("Licence (excerpt):")} {query.data.license}…
            </p>
          )}
        </div>
      )}
    </Modal>
  );
}
