// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import * as Icon from "lucide-react";
import { useMutation, useQueryClient, useQuery } from "@tanstack/react-query";
import { apiPost, errorMessage, apiPut, apiGet, apiPatch, apiDelete } from "@/api/legacy";
import { queryKeys, useSettings, useProviders } from "@/api/queries";
import * as React from "react";
import { msg, currentLanguage } from "@/i18n";
import {
  Badge,
  Button,
  Callout,
  EmptyState,
  ErrorCallout,
  Field,
  IconButton,
  Input,
  Modal,
  SectionTitle,
  Select,
  Spinner,
  useUi,
} from "@/components/ui";
import { cn, isCloudModelId, timeAgo } from "@/lib/util";
import { navigate } from "@/lib/router";
import { useLocalState } from "@/lib/hooks";

var MODEL_CATALOG_KEY = [`model-catalog`],
  OPENROUTER_URL = `https://openrouter.ai/`,
  isOpenRouter = (e) => (e.base_url ?? ``).includes(`openrouter.ai`),
  fmtPrice = (e) => `$${e < 0.1 ? e.toFixed(3) : e.toFixed(2)}`,
  lastTest = (e) => e?.config.last_test;

function ExternalLinkText({ href, children }) {
  return (
    <a className="text-accent underline underline-offset-2" href={href} target="_blank" rel="noreferrer noopener">
      {children} <Icon.ExternalLink className="inline size-3" aria-hidden />
    </a>
  );
}

function ModelPrice({ m: e }) {
  return e.input_per_million === null || e.output_per_million === null ? (
    <span>{msg("Price unavailable — check OpenRouter")}</span>
  ) : (
    <span>
      {fmtPrice(e.input_per_million)} {msg("in /")} {fmtPrice(e.output_per_million)} {msg("out per 1M tokens")}
      {e.cache_read_per_million !== null && (
        <span className="text-faint">
          {" "}
          {msg("· cached input")} {fmtPrice(e.cache_read_per_million)}
        </span>
      )}
    </span>
  );
}

var CONTEXT_BUDGET_DEFAULT = 8e3,
  REPLY_RESERVE_DEFAULT = 2e3,
  suggestedContext = (e) =>
    e.input_per_million === null || e.output_per_million === null
      ? null
      : (CONTEXT_BUDGET_DEFAULT * e.input_per_million + REPLY_RESERVE_DEFAULT * e.output_per_million) / 1e6;

function CatalogModelRow({ m: e, provider, profile, isDefault, onAdded }) {
  let { toast } = useUi(),
    mutation = useMutation({
      mutationFn: () =>
        apiPost(`/model-profiles`, {
          provider_id: provider.id,
          model_id: e.slug,
          display_name: e.name === e.slug ? undefined : e.name,
          context_limit: e.context_length,
        }),
      onSuccess: () => {
        (onAdded(),
          toast(
            msg("{{v0}} added to your models. Stories keep their current model until you change it.", {
              v0: e.slug,
            }),
          ));
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    }),
    s = useMutation({
      mutationFn: () =>
        apiPut(`/settings`, {
          default_model_profile_id: profile.id,
        }),
      onSuccess: onAdded,
      onError: (e) => toast(errorMessage(e), `danger`),
    }),
    c = e.available === false;
  return (
    <li
      className={cn(
        `flex min-w-0 flex-col gap-1.5 rounded-lg border p-3`,
        e.tested ? `border-accent/50 bg-accent-soft` : `border-line bg-panel`,
        c && `opacity-80`,
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="min-w-0 font-medium [overflow-wrap:anywhere]">{e.name}</span>
        <Badge tone={e.tested ? `accent` : `neutral`}>{e.label}</Badge>
        {c && <Badge tone="warn">{msg("Unavailable")}</Badge>}
      </div>
      <p className="font-mono text-[11px] text-faint [overflow-wrap:anywhere]">{e.slug}</p>
      <p className="text-xs text-muted">
        <ModelPrice m={e} />
        {e.context_length ? (
          <span className="text-faint">
            {" · "}
            {e.context_length.toLocaleString()} {msg("token context")}
          </span>
        ) : null}
      </p>
      {e.structured_output === false && (
        <p className="text-xs text-warn">
          {msg("Structured replies are not listed for this model, so scene analysis may be less reliable.")}
        </p>
      )}
      {e.expiration_date && (
        <p className="text-xs text-warn">
          {msg("OpenRouter lists a retirement date:")} {e.expiration_date}.
        </p>
      )}
      {c && (
        <p className="text-xs text-warn">
          {e.unavailable_reason}
          {e.alternative
            ? msg(" Try {{v0}} instead.", {
                v0: e.alternative,
              })
            : ``}
        </p>
      )}
      <ul className="text-xs">
        {e.pros.map((e) => (
          <li className="text-muted" key={e}>
            <span className="text-ok" aria-hidden>
              {"+ "}
            </span>
            <span className="sr-only">{msg("Pro:")} </span>
            {e}
          </li>
        ))}
        {e.cons.map((e) => (
          <li className="text-muted" key={e}>
            <span className="text-warn" aria-hidden>
              {"− "}
            </span>
            <span className="sr-only">{msg("Con:")} </span>
            {e}
          </li>
        ))}
      </ul>
      <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-1">
        {profile ? (
          <>
            <Badge tone="ok">
              <Icon.Check className="size-3" /> {msg("In your models")}
            </Badge>
            {isDefault ? (
              <Badge tone="accent">{msg("Default for new stories")}</Badge>
            ) : (
              <Button size="sm" variant="ghost" loading={s.isPending} onClick={() => s.mutate()}>
                {msg("Make default")}
              </Button>
            )}
          </>
        ) : (
          <Button
            size="sm"
            disabled={!provider || c}
            loading={mutation.isPending}
            onClick={() => mutation.mutate()}
            aria-label={msg("Select {{v0}}", {
              v0: e.slug,
            })}
            title={provider ? undefined : msg("Connect OpenRouter first (steps below)")}
          >
            {msg("Select")}
          </Button>
        )}
        <span className="ml-auto text-[11px]">
          <ExternalLinkText href={`${OPENROUTER_URL}${e.slug}`}>{msg("Details")}</ExternalLinkText>
        </span>
      </div>
    </li>
  );
}

function ModelCatalog({ provider, profiles, defaultId }) {
  let queryClient = useQueryClient(),
    query = useQuery({
      queryKey: MODEL_CATALOG_KEY,
      queryFn: () => apiGet(`/model-catalog`),
      staleTime: 1 / 0,
      retry: false,
      refetchOnWindowFocus: false,
    }),
    mutation = useMutation({
      mutationFn: () => apiPost(`/model-catalog/refresh`),
      onSuccess: (e) => queryClient.setQueryData(MODEL_CATALOG_KEY, e),
    }),
    o = query.data,
    s = () => {
      (queryClient.invalidateQueries({
        queryKey: queryKeys.providers,
      }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.settings,
        }));
    },
    c = (o?.models ?? []).filter((e) => e.role !== `Premium` && suggestedContext(e) !== null);
  return (
    <section aria-labelledby="recommended-models">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 id="recommended-models" className="text-sm font-semibold">
          {msg("Recommended models for stories")}
        </h3>
        {o && (
          <span className="text-[11px] text-faint">
            {o.fetched_at
              ? o.stale
                ? msg("Last checked {{v0}}", {
                    v0: new Date(o.fetched_at).toLocaleDateString(),
                  })
                : msg("Prices from OpenRouter, checked {{v0}}", {
                    v0: timeAgo(o.fetched_at),
                  })
              : msg("Prices could not be loaded.")}
          </span>
        )}
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto"
          loading={mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          <Icon.RefreshCw className="size-3" /> {msg("Refresh prices")}
        </Button>
      </div>
      {query.isLoading && <Spinner />}
      {o && (
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,17rem),1fr))] gap-2">
          {o.models.map((r) => (
            <CatalogModelRow
              m={r}
              provider={provider}
              profile={profiles.find((t) => t.provider_id === provider?.id && t.model_id === r.slug)}
              isDefault={profiles.some((e) => e.id === defaultId && e.model_id === r.slug)}
              onAdded={s}
              key={r.slug}
            />
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-muted">
        {msg(
          "Start with GLM-5 for this project, try a cheaper model for experiments, and use Ollama when offline play or privacy comes first. Only GLM-5 has been tested with StoryCore; the others are options to evaluate. Prices can change and can differ by routed provider.",
        )}
      </p>
      <details className="mt-1 text-xs text-muted">
        <summary className="cursor-pointer text-accent">{msg("How pricing works")}</summary>
        <div className="mt-1 space-y-1">
          <p>
            {msg("Models are billed per token, not per message. A hypothetical request of")}{" "}
            {CONTEXT_BUDGET_DEFAULT.toLocaleString()} {msg("input and")} {REPLY_RESERVE_DEFAULT.toLocaleString()}{" "}
            {msg("output tokens at today's listed prices, with no cache discount:")}
          </p>
          {c.length > 0 ? (
            <ul className="list-disc pl-4">
              {c.map((e) => (
                <li key={e.slug}>
                  {e.name}: ≈ ${suggestedContext(e).toFixed(5)}
                </li>
              ))}
            </ul>
          ) : (
            <p>{msg("Prices are not available right now.")}</p>
          )}
          <p>
            {msg(
              "This is an illustration, not your real cost per turn. It leaves out scene analysis, memory capture, suggestion repairs, reasoning tokens, provider differences, taxes and credit-purchase fees.",
            )}
          </p>
          <p>
            {msg(
              "Direct API billing can be inexpensive, especially with efficient models, but the total experience and included features differ from hosted story platforms.",
            )}
          </p>
          <p>
            {msg("Check")}{" "}
            <ExternalLinkText href="https://openrouter.ai/activity">{msg("your OpenRouter activity")}</ExternalLinkText>{" "}
            {msg("for what you actually spent.")}
          </p>
        </div>
      </details>
    </section>
  );
}

function SetupStep({ n: e, title, children }) {
  return (
    <li className="flex gap-2.5">
      <span
        className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-panel-2 text-[11px] font-medium text-muted"
        aria-hidden
      >
        {e}
      </span>
      <div className="min-w-0 text-[13px]">
        <p className="font-medium">{title}</p>
        {children && <div className="text-xs text-muted">{children}</div>}
      </div>
    </li>
  );
}

function SelectedModelStatus({ provider, model, onChanged }) {
  let { toast, confirm } = useUi(),
    [a, o] = React.useState(``),
    [s, c] = React.useState(null),
    mutation = useMutation({
      mutationFn: async () => {
        provider
          ? await apiPatch(`/providers/${provider.id}`, {
              api_key: a,
            })
          : await apiPost(`/providers`, {
              provider_type: `openai_compat`,
              display_name: `OpenRouter`,
              base_url: `https://openrouter.ai/api/v1`,
              api_key: a,
              config: {
                label: msg("OpenRouter"),
              },
            });
      },
      onSuccess: () => {
        (o(``), onChanged(), toast(msg("Key saved securely. It will not be shown again.")));
      },
      onError: (e) => toast(errorMessage(e), `danger`),
    }),
    u = useMutation({
      mutationFn: (n) =>
        apiPost(`/providers/${provider.id}/test`, {
          model_id: model?.model_id,
          generate: n,
          record: true,
        }),
      onSuccess: (e) => {
        (c(e), onChanged());
      },
      onError: (e) =>
        c({
          ok: false,
          message: errorMessage(e),
        }),
    });
  return (
    <section aria-labelledby="openrouter-guide" className="rounded-lg border border-line bg-panel p-3">
      <h3 id="openrouter-guide" className="mb-2 text-sm font-semibold">
        {msg("Set up OpenRouter")}
      </h3>
      <ol className="space-y-2">
        <SetupStep n={1} title={msg("Create an account")}>
          <ExternalLinkText href={OPENROUTER_URL}>{msg("openrouter.ai")}</ExternalLinkText>{" "}
          {msg("opens in your browser. StoryCore never creates accounts or buys credits for you.")}
        </SetupStep>
        <SetupStep n={2} title={msg("Add a small amount of credit, if needed")}>
          {msg("See")} <ExternalLinkText href="https://openrouter.ai/pricing">{msg("pricing")}</ExternalLinkText>
          {msg(
            ". Not every model is free. A spending limit on the key is a good idea: that limit is the real protection, not anything in this app.",
          )}
        </SetupStep>
        <SetupStep n={3} title={msg("Create an API key")}>
          <ExternalLinkText href="https://openrouter.ai/settings/keys">{msg("Keys page")}</ExternalLinkText>
          {msg(". Anyone with the key can spend your credits, so never paste it into a story or a public post.")}
        </SetupStep>
        <SetupStep n={4} title={msg("Paste the key here")}>
          <form
            className="mt-1 flex max-w-md flex-wrap gap-1.5"
            onSubmit={(e) => {
              (e.preventDefault(), a.trim() && mutation.mutate());
            }}
          >
            <Input
              type="password"
              autoComplete="off"
              value={a}
              onChange={(e) => o(e.target.value)}
              placeholder={
                provider?.has_api_key ? msg("•••••••• saved (enter a new key to replace)") : msg("Paste your key")
              }
              aria-label={msg("OpenRouter API key")}
              className="min-w-40 flex-1"
            />

            <Button size="md" type="submit" disabled={!a.trim()} loading={mutation.isPending}>
              {msg("Save key")}
            </Button>
          </form>
          <p className="mt-1">
            {msg("Kept in your system's secure credential store, never in stories, backups or logs.")}
          </p>
        </SetupStep>
        <SetupStep n={5} title={msg("Choose a model")}>
          {msg(
            "Use Select on a card above, then pick it per story from the top bar. Selecting never changes a story by itself.",
          )}
        </SetupStep>
        <SetupStep n={6} title={msg("Test the connection")}>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <Button
              size="sm"
              disabled={!provider?.has_api_key}
              loading={u.isPending && u.variables === false}
              onClick={() => u.mutate(false)}
            >
              {msg("Test connection")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={!provider?.has_api_key || !model}
              loading={u.isPending && u.variables === true}
              onClick={async () => {
                (await confirm({
                  title: msg("Send a small paid test?"),
                  body: (
                    <>
                      {msg("This sends one very short request to")} <span className="font-mono">{model?.model_id}</span>
                      {msg(
                        ". It is billed to your OpenRouter account, normally a tiny fraction of a cent. No story text is included.",
                      )}
                    </>
                  ),

                  confirmLabel: msg("Send test"),
                })) && u.mutate(true);
              }}
            >
              {msg("Test model (small paid request)")}
            </Button>
          </div>
          <p className="mt-1">
            {msg(
              "Test connection checks your key and the model list and costs nothing. Nothing is tested unless you press a button.",
            )}
          </p>
        </SetupStep>
      </ol>
      {s && (
        <Callout tone={s.ok ? `ok` : `danger`} className="mt-2">
          {s.message}
        </Callout>
      )}
      <Callout tone="info" className="mt-2">
        {msg(
          "Recommended for immersive stories: OpenRouter gives you access to powerful hosted AI models without running them on your PC. Usage is billed by tokens, and story content (your messages, recent story text and lore excerpts) is sent through OpenRouter to the model's provider, so this is not offline even though your stories are stored on your PC. Providers differ in how they retain data: review the model's price and",
        )}{" "}
        <ExternalLinkText href="https://openrouter.ai/privacy">{msg("the privacy policy")}</ExternalLinkText>{" "}
        {msg("before use.")}
      </Callout>
    </section>
  );
}

function OllamaQuickSetup({ provider, onChanged }) {
  let [n, r] = React.useState(null),
    mutation = useMutation({
      mutationFn: () => apiPost(`/ollama/quick-setup`),
      onSuccess: onChanged,
    }),
    a = useMutation({
      mutationFn: () =>
        apiPost(`/providers/${provider.id}/test`, {
          record: true,
        }),
      onSuccess: (e) => {
        (r(e), onChanged());
      },
      onError: (e) =>
        r({
          ok: false,
          message: errorMessage(e),
        }),
    });
  return (
    <section aria-labelledby="ollama-guide" className="rounded-lg border border-line bg-panel p-3">
      <h3 id="ollama-guide" className="mb-2 text-sm font-semibold">
        {msg("Set up Ollama")}
      </h3>
      <ol className="space-y-2">
        <SetupStep n={1} title={msg("Install Ollama")}>
          <ExternalLinkText href="https://ollama.com/download">{msg("ollama.com/download")}</ExternalLinkText>
        </SetupStep>
        <SetupStep n={2} title={msg("Start it")}>
          {msg("It listens on")} <span className="font-mono">{msg("http://127.0.0.1:11434")}</span>.
          {!provider && (
            <span className="mt-1 block">
              <Button size="sm" loading={mutation.isPending} onClick={() => mutation.mutate()}>
                {msg("Add local Ollama to StoryCore")}
              </Button>
            </span>
          )}
        </SetupStep>
        <SetupStep n={3} title={msg("Install a model yourself")}>
          {msg("Use Ollama, or the download box on the Ollama models page. See the")}{" "}
          <ExternalLinkText href="https://ollama.com/library">{msg("model library")}</ExternalLinkText>
          {msg(". StoryCore never downloads a model unless you ask.")}
        </SetupStep>
        <SetupStep n={4} title={msg("Check what is installed")}>
          <span className="mt-1 block">
            <Button size="sm" disabled={!provider} loading={a.isPending} onClick={() => a.mutate()}>
              {msg("Check Ollama")}
            </Button>
          </span>
          {msg("This only lists models; nothing is loaded into memory.")}
        </SetupStep>
        <SetupStep n={5} title={msg("Select a model")}>
          <span className="mt-1 block">
            <Button size="sm" variant="ghost" onClick={() => navigate(`/settings/ollama`)}>
              {msg("Open Ollama models")}
            </Button>
          </span>
          {msg("Then set its context size and output length under Parameters, in All providers below.")}
        </SetupStep>
        <SetupStep n={6} title={msg("Start a story")}>
          {msg("Speed, context and quality depend on model size, quantization and your CPU, GPU and memory.")}
        </SetupStep>
      </ol>
      {n && (
        <Callout tone={n.ok ? `ok` : `warn`} className="mt-2">
          {n.message}
        </Callout>
      )}
      {provider?.is_cloud && (
        <Callout tone="warn" className="mt-2">
          {msg(
            "This Ollama endpoint is not on this computer, so story content is sent to that server. It is not offline.",
          )}
        </Callout>
      )}
      <Callout tone="info" className="mt-2">
        {msg(
          "Ollama is great for learning, experimenting and offline or private play when you run a model locally. Small local models may struggle with long context, many characters, strict JSON extraction and extended narrative coherence. For the richest stories on typical PCs, we recommend trying an affordable hosted model through OpenRouter. Your Ollama option remains fully supported.",
        )}
      </Callout>
      <p className="mt-2 text-xs text-faint">
        {msg(
          'This applies to models running on your own computer. Ollama also offers cloud models (their names end in "cloud"): those run remotely even through local Ollama.',
        )}
      </p>
    </section>
  );
}

function DefaultModelPicker({ providers, profiles, defaultId, tested }) {
  let settings = useSettings(),
    a = profiles.find((e) => e.id === defaultId),
    o = providers.find((e) => e.id === a?.provider_id),
    s =
      settings.data?.extraction_model_source === `separate`
        ? profiles.find((e) => e.id === settings.data?.extraction_model_profile_id)
        : null,
    c = lastTest(tested),
    l = !!o?.is_cloud || (!!a && isCloudModelId(a.model_id));
  return (
    <section aria-labelledby="current-selection" className="rounded-lg border border-line bg-panel p-3 text-[13px]">
      <h3 id="current-selection" className="mb-1.5 text-sm font-semibold">
        {msg("Selected model and status")}
      </h3>
      <dl className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)] gap-x-2 gap-y-0.5 text-xs">
        {a && o ? (
          <>
            <dt className="text-faint">{msg("Default for new stories")}</dt>
            <dd className="flex min-w-0 flex-wrap items-center gap-1.5 [overflow-wrap:anywhere]">
              {l ? (
                <Icon.Cloud className="size-3 text-warn" aria-hidden />
              ) : (
                <Icon.HardDrive className="size-3 text-ok" aria-hidden />
              )}
              {o.display_name}
              {" — "}
              <span className="font-mono">{a.model_id}</span>
            </dd>
            <dt className="text-faint">{msg("Scene analysis, memory")}</dt>
            <dd>
              {settings.data?.extraction_model_source === `none` ? (
                msg("Model-based capture is off")
              ) : s ? (
                <span className="font-mono [overflow-wrap:anywhere]">{s.model_id}</span>
              ) : (
                msg("Same as each story's model")
              )}
            </dd>
          </>
        ) : (
          <>
            <dt className="text-faint">{msg("Default for new stories")}</dt>
            <dd className="text-muted">
              {msg("None yet. Select a model above, or choose per story from the top bar.")}
            </dd>
          </>
        )}
        {tested && (
          <>
            <dt className="text-faint">
              {msg("Last")} {tested.display_name} {msg("test")}
            </dt>
            <dd className={c ? (c.ok ? `text-ok` : `text-danger`) : `text-faint`}>
              {c
                ? `${c.ok ? msg("Passed", {}) : msg("Failed", {})} ${timeAgo(c.at)}: ${c.message}`
                : msg("Not tested yet")}
            </dd>
          </>
        )}
      </dl>
      {l && (settings.data?.turn_analysis_mode ?? `always`) !== `always` && (
        <Callout tone="info" className="mt-2">
          {msg("Scene analysis is")}{" "}
          {settings.data?.turn_analysis_mode === `off` ? `off` : msg("set to Local models only")}
          {msg(", so this model's replies get no portraits from analysis, suggestions or relationship changes.")}{" "}
          <button type="button" className="underline" onClick={() => navigate(`/settings/memory`)}>
            {msg("Change it in Memory capture")}
          </button>
          .
        </Callout>
      )}
      <p className="mt-1.5 text-xs text-faint">
        {msg(
          "A story that has its own model keeps it. Each turn makes several requests (the reply, then scene analysis for portraits, suggestions and relationships, and memory capture), each billed on a paid model.",
        )}
      </p>
    </section>
  );
}

function lmNoteText(e) {
  if (e.code === `not_loaded`)
    return msg(
      "This model is not loaded in LM Studio yet: load it there before playing (LM Studio may also load it on the first request).",
    );
  if (e.code === `small_context`)
    return msg(
      "It runs with a context of {{v0}} tokens, which is small for a story: in LM Studio, reload the model with a larger Context Length (16,384 or more if your memory allows), then press Detect again.",
      { v0: e.value.toLocaleString(currentLanguage) },
    );
  if (e.code === `max_context_used`)
    return msg(
      "LM Studio did not say which context length the model is loaded with; its maximum ({{v0}}) was used. If replies forget the start of the story, set the profile's context window to the length chosen in LM Studio.",
      { v0: e.value },
    );
  return e.text;
}

function LMStudioQuickSetup({ onChanged }) {
  let ui = useUi(),
    [url, setUrl] = React.useState(`http://localhost:1234/v1`),
    [result, setResult] = React.useState(null),
    detect = useMutation({
      mutationFn: () => apiGet(`/lmstudio/detect?base_url=${encodeURIComponent(url)}`),
      onSuccess: () => setResult(null),
    }),
    setup = useMutation({
      mutationFn: (modelId) =>
        apiPost(`/lmstudio/setup`, {
          base_url: url,
          model_id: modelId,
          make_default: true,
        }),
      onSuccess: (e) => {
        setResult(e);
        onChanged();
        ui.toast(msg("{{v0}} is ready and set as the default model.", { v0: e.model_id }));
      },
      onError: (e) =>
        setResult({
          error: errorMessage(e),
        }),
    }),
    found = detect.data;
  return (
    <section aria-labelledby="lmstudio-guide" className="rounded-lg border border-line bg-panel p-3">
      <h3 id="lmstudio-guide" className="mb-2 text-sm font-semibold">
        {msg("Set up LM Studio")}
      </h3>
      <ol className="space-y-2">
        <SetupStep n={1} title={msg("Install LM Studio and download a model")}>
          <ExternalLinkText href="https://lmstudio.ai/">{msg("lmstudio.ai")}</ExternalLinkText>
        </SetupStep>
        <SetupStep n={2} title={msg("Start the local server")}>
          {msg(
            "In LM Studio, open the Developer tab and switch the server on. When you load a model, choose a Context Length of 16,384 or more if your memory allows.",
          )}
        </SetupStep>
        <SetupStep n={3} title={msg("Detect LM Studio")}>
          <span className="mt-1 flex flex-wrap items-center gap-2">
            <Input
              aria-label={msg("LM Studio server address")}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="h-8 w-64 font-mono text-xs"
            />
            <Button size="sm" loading={detect.isPending} onClick={() => detect.mutate()}>
              <Icon.Radar className="size-3.5" aria-hidden />
              {msg("Detect")}
            </Button>
          </span>
        </SetupStep>
        <SetupStep n={4} title={msg("Pick a model")}>
          {msg("One click creates the connection with the right context size and output length, and makes it the default.")}
        </SetupStep>
      </ol>
      {detect.isError && (
        <Callout tone="warn" className="mt-2">
          {errorMessage(detect.error)}
        </Callout>
      )}
      {found && !found.reachable && (
        <Callout tone="warn" className="mt-2">
          {msg(
            "LM Studio is not reachable at this address. Open LM Studio, go to the Developer tab and start the server (port 1234 by default).",
          )}
        </Callout>
      )}
      {found?.reachable && found.models.length === 0 && (
        <Callout tone="warn" className="mt-2">
          {msg("LM Studio answers, but has no model. Download one in LM Studio, then press Detect again.")}
        </Callout>
      )}
      {found?.reachable && found.models.length > 0 && (
        <ul className="mt-2 divide-y divide-line rounded-md border border-line" aria-label={msg("LM Studio models")}>
          {found.models.map((m) => {
            let ctx = m.loaded_context ?? m.max_context;
            return (
              <li key={m.id} className="flex flex-wrap items-center gap-2 px-2.5 py-2">
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-mono text-xs">{m.id}</span>
                  <span className="block text-[11px] text-muted">
                    {m.state === `loaded`
                      ? msg("Loaded")
                      : m.state === `not-loaded`
                        ? msg("Not loaded")
                        : msg("State unknown")}
                    {ctx ? ` · ` + msg("context {{v0}} tokens", { v0: ctx.toLocaleString(currentLanguage) }) : ``}
                    {m.quantization ? ` · ${m.quantization}` : ``}
                  </span>
                </span>
                {m.loaded_context && m.loaded_context < 8192 && (
                  <Badge tone="warn">{msg("Small context")}</Badge>
                )}
                <Button
                  size="sm"
                  variant={m.state === `loaded` ? `primary` : `secondary`}
                  loading={setup.isPending && setup.variables === m.id}
                  disabled={setup.isPending}
                  onClick={() => setup.mutate(m.id)}
                >
                  {msg("Use this model")}
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      {result?.error && (
        <Callout tone="warn" className="mt-2">
          {result.error}
        </Callout>
      )}
      {result && !result.error && (
        <Callout tone={result.notes.length ? `warn` : `ok`} className="mt-2">
          <p>
            {msg("{{v0}} is ready: context {{v1}} tokens, replies up to {{v2}} tokens.", {
              v0: result.model_id,
              v1: result.context_limit ? result.context_limit.toLocaleString(currentLanguage) : `?`,
              v2: result.max_tokens,
            })}
          </p>
          {result.notes.map((e) => (
            <p className="mt-1" key={e.code}>
              {lmNoteText(e)}
            </p>
          ))}
        </Callout>
      )}
    </section>
  );
}

// v1.8: also used by the first-run assistant (features/setup) with a fixed path and without the chooser
export function ProvidersQuickSetup({ path, hideChooser = false } = {}) {
  let providers = useProviders(),
    queryClient = useQueryClient(),
    [saved, r] = useLocalState(`ai-path`, `openrouter`),
    n = path ?? saved,
    i = providers.data;
  if (!i) return null;
  let a = () => {
      (queryClient.invalidateQueries({
        queryKey: queryKeys.providers,
      }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.settings,
        }));
    },
    o = i.providers.find(isOpenRouter),
    s = i.providers.find((e) => e.provider_type === `ollama`),
    lm = i.providers.find((e) => e.provider_type === `openai_compat` && /:1234\b/.test(e.base_url ?? ``)),
    c = i.profiles.filter((e) => e.provider_id === o?.id),
    l = c.find((e) => e.id === i.default_model_profile_id) ?? c[0];
  return (
    <div className="space-y-4">
      {!hideChooser && (
      <section aria-labelledby="run-ai">
        <SectionTitle>
          <span id="run-ai">{msg("Choose how to run the AI")}</span>
        </SectionTitle>
        <div role="group" aria-labelledby="run-ai" className="grid gap-2 sm:grid-cols-3">
          {[
            {
              id: `openrouter`,
              title: msg("OpenRouter (recommended for rich storytelling)"),
              note: msg("Powerful hosted models, billed per use. Needs internet.", {}),
              icon: Icon.Cloud,
            },
            {
              id: `ollama`,
              title: msg("Ollama (local and offline)"),
              note: msg("Runs on your own computer. Free to use; quality depends on your hardware."),
              icon: Icon.HardDrive,
            },
            {
              id: `lmstudio`,
              title: msg("LM Studio (local and offline)"),
              note: msg("Runs on your own computer, with a window to download and load models. Set up in one click."),
              icon: Icon.Monitor,
            },
          ].map((e) => (
            <button
              type="button"
              aria-pressed={n === e.id}
              onClick={() => r(e.id)}
              className={cn(
                `flex min-w-0 items-start gap-2 rounded-lg border p-3 text-left`,
                n === e.id ? `border-accent bg-accent-soft` : `border-line hover:border-line-strong`,
              )}
              key={e.id}
            >
              <e.icon className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
              <span className="min-w-0">
                <span className="block text-[13px] font-medium">{e.title}</span>
                <span className="block text-xs text-muted">{e.note}</span>
              </span>
            </button>
          ))}
        </div>
        <p className="mt-1 text-xs text-faint">
          {msg(
            "This only changes which guide you see here. Anthropic, OpenAI and other servers are under All providers below.",
          )}
        </p>
      </section>
      )}
      {n === `openrouter` ? (
        <>
          <ModelCatalog provider={o} profiles={i.profiles} defaultId={i.default_model_profile_id} />
          <SelectedModelStatus provider={o} model={l} onChanged={a} />
        </>
      ) : n === `lmstudio` ? (
        <LMStudioQuickSetup onChanged={a} />
      ) : (
        <OllamaQuickSetup provider={s} onChanged={a} />
      )}
      <DefaultModelPicker
        providers={i.providers}
        profiles={i.profiles}
        defaultId={i.default_model_profile_id}
        tested={n === `openrouter` ? o : n === `lmstudio` ? lm : s}
      />
    </div>
  );
}

var PARAM_INFO = {
  temperature: {
    label: msg("Temperature"),
    min: 0,
    max: 2,
    step: 0.05,
  },
  top_p: {
    label: msg("Top-p"),
    min: 0,
    max: 1,
    step: 0.01,
  },
  top_k: {
    label: msg("Top-k"),
    min: 0,
    max: 200,
    step: 1,
  },
  max_tokens: {
    label: msg("Max output tokens"),
    min: 16,
    max: 32e3,
    step: 16,
  },
  context_size: {
    label: msg("Context size (num_ctx)"),
    min: 512,
    max: 262144,
    step: 512,
    hint: msg("Ollama only"),
  },
  repeat_penalty: {
    label: msg("Repetition penalty"),
    min: 0.5,
    max: 2,
    step: 0.01,
  },
  frequency_penalty: {
    label: msg("Frequency penalty"),
    min: -2,
    max: 2,
    step: 0.05,
  },
  presence_penalty: {
    label: msg("Presence penalty"),
    min: -2,
    max: 2,
    step: 0.05,
  },
  seed: {
    label: msg("Seed"),
    min: 0,
    max: 2 ** 31,
    step: 1,
  },
};

export function AdvancedProviders() {
  let providers = useProviders(),
    [t, n] = React.useState(false);
  if (providers.isLoading) return <Spinner />;
  if (providers.isError) return <ErrorCallout error={providers.error} />;
  let r = providers.data;
  return (
    <div className="max-w-5xl space-y-5">
      <ProvidersQuickSetup />
      <details className="rounded-lg border border-line p-3">
        <summary className="cursor-pointer text-sm font-semibold">{msg("All providers and advanced options")}</summary>
        <div className="mt-3 space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="max-w-2xl text-sm text-muted">
              {msg(
                "Providers you add here can be picked per story. API keys stay on this computer's backend and are never shown again after saving. Model IDs can be entered by hand; context budgets are in Narration & context.",
              )}
            </p>
            <Button variant="primary" onClick={() => n(true)}>
              <Icon.Plus className="size-4" /> {msg("Add provider")}
            </Button>
          </div>
          {r.providers.map((e) => (
            <ProviderCard
              p={e}
              profiles={r.profiles.filter((t) => t.provider_id === e.id)}
              defaultId={r.default_model_profile_id}
              key={e.id}
            />
          ))}
        </div>
      </details>
      {t && <AddProviderDialog onClose={() => n(false)} />}
    </div>
  );
}

function ProviderCard({ p: e, profiles, defaultId }) {
  let queryClient = useQueryClient(),
    { toast, confirm } = useUi(),
    [o, s] = React.useState(null),
    [c, l] = React.useState(``),
    [u, d] = React.useState(false),
    [f, p] = React.useState(e.base_url ?? ``),
    g = () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.providers,
      }),
    mutation = useMutation({
      mutationFn: () =>
        apiPost(`/providers/${e.id}/test`, {
          model_id: profiles[0]?.model_id,
          record: true,
        }),
      onSuccess: (e) => {
        (s(e), g());
      },
      onError: (e) =>
        s({
          ok: false,
          message: errorMessage(e),
        }),
    }),
    y = async (t = false) => {
      try {
        (await apiPatch(
          `/providers/${e.id}`,
          t
            ? {
                clear_api_key: true,
              }
            : {
                api_key: c,
              },
        ),
          l(``),
          g(),
          toast(t ? msg("API key removed", {}) : msg("API key saved (it will not be displayed again)", {})));
      } catch (e) {
        toast(errorMessage(e), `danger`);
      }
    };
  return (
    <div className="rounded-lg border border-line bg-panel">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
        {e.is_cloud ? <Icon.Cloud className="size-4 text-warn" /> : <Icon.HardDrive className="size-4 text-ok" />}
        <span className="font-medium">{e.display_name}</span>
        <Badge>{e.provider_type.replace(`_`, `-`)}</Badge>
        {e.is_cloud ? <Badge tone="warn">{msg("cloud")}</Badge> : <Badge tone="ok">{msg("local")}</Badge>}
        {e.provider_type === `mock` && <Badge tone="info">{msg("offline demo — not a real model")}</Badge>}
        <div className="ml-auto flex gap-1.5">
          <Button size="sm" loading={mutation.isPending} onClick={() => mutation.mutate()}>
            {msg("Test connection")}
          </Button>
          {e.provider_type !== `mock` && (
            <IconButton
              label={msg("Remove provider")}
              onClick={async () => {
                (await confirm({
                  title: msg("Remove {{v0}}?", {
                    v0: e.display_name,
                  }),
                  body: msg(
                    "Its model profiles and stored API key are removed. Stories pinned to it fall back to the default model.",
                  ),
                  danger: true,
                  confirmLabel: msg("Remove"),
                })) && (await apiDelete(`/providers/${e.id}`), g());
              }}
            >
              <Icon.Trash className="size-4" />
            </IconButton>
          )}
        </div>
      </div>
      <div className="space-y-3 px-4 py-3">
        {o && (
          <Callout tone={o.ok ? `ok` : `danger`}>
            {o.message}
            {o.error?.details && (
              <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap text-[11px] text-muted">
                {o.error.details}
              </pre>
            )}
          </Callout>
        )}
        {e.provider_type !== `mock` && (
          <div className="grid gap-3 md:grid-cols-2">
            <Field label={msg("Endpoint / base URL")}>
              <div className="flex gap-1">
                <Input value={f} onChange={(e) => p(e.target.value)} aria-label={msg("Endpoint / base URL")} />
                {f !== (e.base_url ?? ``) && (
                  <Button
                    size="sm"
                    onClick={async () => {
                      (await apiPatch(`/providers/${e.id}`, {
                        base_url: f,
                      }),
                        g());
                    }}
                  >
                    {msg("Save")}
                  </Button>
                )}
              </div>
            </Field>
            {e.provider_type !== `ollama` && (
              <Field
                label={
                  <span className="flex items-center gap-1">
                    <Icon.KeyRound className="size-3" /> {msg("API key")}{" "}
                    {e.has_api_key ? (
                      <Badge tone="ok">{msg("saved")}</Badge>
                    ) : (
                      <Badge>{e.provider_type === `openai_compat` ? `optional` : msg("not set")}</Badge>
                    )}
                  </span>
                }
              >
                <div className="flex gap-1">
                  <Input
                    type="password"
                    autoComplete="off"
                    value={c}
                    onChange={(e) => l(e.target.value)}
                    placeholder={
                      e.has_api_key ? msg("•••••••• (stored — enter a new key to replace)") : msg("Paste key")
                    }
                  />

                  <Button size="sm" disabled={!c} onClick={() => y()}>
                    {msg("Save")}
                  </Button>
                  {e.has_api_key && (
                    <Button size="sm" variant="ghost" onClick={() => y(true)}>
                      {msg("Remove")}
                    </Button>
                  )}
                </div>
              </Field>
            )}
          </div>
        )}
        {e.provider_type === `anthropic` && (
          <p className="text-xs text-faint">
            {msg("Uses Anthropic's Messages API. API usage is billed separately from a Claude.ai subscription.")}
          </p>
        )}
        {e.provider_type === `openai` && (
          <p className="text-xs text-faint">
            {msg(
              "Uses OpenAI's Responses API. Reasoning models may reject temperature/top-p; clear them in the model's parameters if so.",
            )}
          </p>
        )}
        {e.provider_type === `openai_compat` && (
          <p className="text-xs text-faint">
            {msg(
              "Uses the Chat Completions format (OpenRouter, LM Studio, llama.cpp, vLLM…). If model listing fails, add the model ID manually.",
            )}
          </p>
        )}
        <SectionTitle
          action={
            e.provider_type !== `mock` && (
              <Button size="sm" variant="ghost" onClick={() => d(true)}>
                <Icon.Plus className="size-3.5" /> {msg("Add model")}
              </Button>
            )
          }
        >
          {msg("Model profiles")}
        </SectionTitle>
        {profiles.length === 0 && <p className="text-xs text-faint">{msg("No models added yet.")}</p>}
        <div className="space-y-2">
          {profiles.map((t) => (
            <ModelProfileRow m={t} p={e} isDefault={t.id === defaultId} key={t.id} />
          ))}
        </div>
      </div>
      {u && <AddModelDialog p={e} onClose={() => d(false)} />}
    </div>
  );
}

function ModelProfileRow({ m: e, p, isDefault }) {
  let queryClient = useQueryClient(),
    { toast } = useUi(),
    [a, o] = React.useState(false),
    [s, c] = React.useState({
      ...e.generation_settings_json,
    }),
    [l, u] = React.useState(String(e.context_limit ?? ``)),
    d = () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.providers,
      });
  return (
    <div className="rounded-md border border-line">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
        <span className="min-w-0 font-medium [overflow-wrap:anywhere]">{e.display_name}</span>
        {e.display_name !== e.model_id && (
          <span className="min-w-0 text-xs text-faint [overflow-wrap:anywhere]">{e.model_id}</span>
        )}
        {isDefault && <Badge tone="accent">{msg("global default")}</Badge>}
        <div className="ml-auto flex gap-1">
          {!isDefault && (
            <Button
              size="sm"
              variant="ghost"
              onClick={async () => {
                (await apiPut(`/settings`, {
                  default_model_profile_id: e.id,
                }),
                  d(),
                  queryClient.invalidateQueries({
                    queryKey: queryKeys.settings,
                  }));
              }}
            >
              <Icon.Star className="size-3.5" /> {msg("Make default")}
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => o(!a)}>
            {msg("Parameters")}
          </Button>
          <IconButton
            label={msg("Remove model profile")}
            onClick={async () => {
              (await apiDelete(`/model-profiles/${e.id}`), d());
            }}
          >
            <Icon.Trash className="size-3.5" />
          </IconButton>
        </div>
      </div>
      {a && (
        <div className="space-y-2 border-t border-line px-3 py-3">
          <p className="text-[11px] text-faint">
            {msg("Only parameters this provider supports are shown. Empty = not sent (provider default).")}
          </p>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(17rem,1fr))] gap-2">
            {p.supported_params.map((e) => {
              if (e === `think` && p.provider_type === `openai_compat` && !(p.base_url ?? ``).includes(`openrouter.ai`))
                return null;
              if (e === `think`)
                return (
                  <label
                    className="flex items-center gap-2 text-xs text-muted"
                    title={msg(
                      "Thinking-capable models reason before answering, and those hidden tokens are billed and count toward Max output tokens: with too small a limit the story itself gets cut off. Scene analysis always turns it off.",
                    )}
                    key={e}
                  >
                    <span className="w-36 shrink-0">{msg("Thinking (story replies)")}</span>
                    <Select
                      value={s.think == null ? `` : String(s.think)}
                      onChange={(e) =>
                        c({
                          ...s,
                          think: e.target.value === `` ? null : e.target.value === `true`,
                        })
                      }
                      className="h-7"
                    >
                      <option value="">{msg("Off (recommended for stories)")}</option>
                      <option value="true">{msg("On")}</option>
                      <option value="false">{msg("Off")}</option>
                    </Select>
                  </label>
                );

              let n = PARAM_INFO[e];
              return n ? (
                <label className="flex items-center gap-2 text-xs text-muted" key={e}>
                  <span className="w-36 shrink-0">{n.label}</span>
                  <Input
                    type="number"
                    min={n.min}
                    max={n.max}
                    step={n.step}
                    value={s[e] == null ? `` : String(s[e])}
                    onChange={(t) =>
                      c({
                        ...s,
                        [e]: t.target.value === `` ? null : Number(t.target.value),
                      })
                    }
                    className="h-7"
                  />
                </label>
              ) : null;
            })}
            <label className="flex items-center gap-2 text-xs text-muted">
              <span className="w-36 shrink-0">{msg("Context window (tokens)")}</span>
              <Input
                type="number"
                value={l}
                onChange={(e) => u(e.target.value)}
                placeholder="unknown"
                className="h-7"
              />
            </label>
          </div>
          <Button
            size="sm"
            variant="primary"
            onClick={async () => {
              try {
                (await apiPatch(`/model-profiles/${e.id}`, {
                  generation_settings: s,
                  context_limit: l ? Number(l) : 0,
                }),
                  d(),
                  toast(msg("Model parameters saved")));
              } catch (e) {
                toast(errorMessage(e), `danger`);
              }
            }}
          >
            {msg("Save parameters")}
          </Button>
        </div>
      )}
    </div>
  );
}

function AddModelDialog({ p, onClose }) {
  let queryClient = useQueryClient(),
    { toast } = useUi(),
    query = useQuery({
      queryKey: [`models`, p.id],
      queryFn: () => apiGet(`/providers/${p.id}/models`),
    }),
    [a, o] = React.useState(``),
    [s, c] = React.useState(``),
    [l, u] = React.useState(false),
    d = async (i, a) => {
      try {
        (await apiPost(`/model-profiles`, {
          provider_id: p.id,
          model_id: i,
          context_limit: a ?? null,
          make_default: l,
        }),
          queryClient.invalidateQueries({
            queryKey: queryKeys.providers,
          }),
          toast(
            msg("Added {{v0}}", {
              v0: i,
            }),
          ),
          onClose());
      } catch (e) {
        toast(errorMessage(e), `danger`);
      }
    },
    f = (query.data?.models ?? []).filter((e) => e.id.toLowerCase().includes(s.toLowerCase()));
  return (
    <Modal
      open
      onOpenChange={(e) => !e && onClose()}
      size="lg"
      title={msg("Add a model — {{v0}}", {
        v0: p.display_name,
      })}
    >
      {query.isLoading && <Spinner />}
      {query.data && !query.data.ok && (
        <Callout tone="warn" className="mb-3" title={msg("Couldn't list models")}>
          {query.data.message} {query.data.manual_hint}
        </Callout>
      )}
      {query.data?.ok && (
        <>
          <Input
            value={s}
            onChange={(e) => c(e.target.value)}
            placeholder={msg("Filter {{v0}} models", {
              v0: query.data.models.length,
            })}
            className="mb-2"
          />

          <div className="max-h-72 space-y-1 overflow-y-auto">
            {f.length === 0 && (
              <EmptyState title={msg("No models listed")}>
                {p.provider_type === `ollama`
                  ? msg("Download one in Settings → Ollama models.")
                  : msg("Enter a model ID below.")}
              </EmptyState>
            )}
            {f.map((e) => (
              <button
                onClick={() => d(e.id, e.context_length)}
                className="flex w-full items-center gap-2 rounded-md border border-line px-3 py-1.5 text-left text-sm hover:border-accent/60"
                key={e.id}
              >
                <span className="flex-1 truncate">{e.display_name || e.id}</span>
                {e.details?.price_in != null && e.details?.price_out != null && (
                  <Badge title={msg("USD per 1M input / output tokens, from the provider's catalog")}>
                    ${e.details.price_in}
                    {" / $"}
                    {e.details.price_out}
                  </Badge>
                )}
                {e.context_length ? (
                  <Badge>
                    {e.context_length.toLocaleString()} {msg("ctx")}
                  </Badge>
                ) : null}
                {query.data?.running?.includes(e.id) && <Badge tone="ok">{msg("loaded")}</Badge>}
                <Icon.Plus className="size-3.5 text-muted" />
              </button>
            ))}
          </div>
        </>
      )}
      <form
        className="mt-4 flex gap-2"
        onSubmit={(e) => {
          (e.preventDefault(), a.trim() && d(a.trim()));
        }}
      >
        <Input
          value={a}
          onChange={(e) => o(e.target.value)}
          placeholder={
            p.provider_type === `anthropic` ? msg("Manual model ID, e.g. claude-sonnet-5-5") : msg("Manual model ID")
          }
        />

        <Button type="submit" disabled={!a.trim()}>
          {msg("Add manually")}
        </Button>
      </form>
      <label className="mt-2 flex items-center gap-2 text-xs text-muted">
        <input type="checkbox" checked={l} onChange={(e) => u(e.target.checked)} />{" "}
        {msg("Make it the global default model")}
      </label>
    </Modal>
  );
}

function AddProviderDialog({ onClose }) {
  let query = useQuery({
      queryKey: [`presets`],
      queryFn: () => apiGet(`/providers/presets`),
    }),
    queryClient = useQueryClient(),
    { toast } = useUi(),
    [i, a] = React.useState(null),
    [o, s] = React.useState(``),
    [c, l] = React.useState(``),
    [u, d] = React.useState(``),
    [f, p] = React.useState(null),
    [g, v] = React.useState(null),
    [y, b] = React.useState(false);
  return (
    <Modal
      open
      onOpenChange={(t) => !t && onClose()}
      size="lg"
      title={msg("Add a provider")}
      description={msg(
        "Choose → connect → test → pick models. Nothing is sent to a cloud provider until you start a story with it and approve the data notice.",
      )}
    >
      {!i && (
        <div className="grid gap-2 sm:grid-cols-2">
          {query.data?.presets.map((e) => (
            <button
              onClick={() => {
                (a(e), s(e.display_name), l(e.base_url));
              }}
              className="rounded-lg border border-line p-3 text-left hover:border-accent/60"
              key={e.display_name}
            >
              <p className="text-sm font-medium">{e.display_name}</p>
              <p className="text-xs text-faint">{e.base_url || msg("Any OpenAI-compatible server")}</p>
              <p className="mt-1 text-[11px] text-muted">
                {e.needs_key ? msg("Needs an API key") : msg("No key needed")}
              </p>
            </button>
          ))}
        </div>
      )}
      {i && !f && (
        <div className="space-y-3">
          <Field label={msg("Display name")}>
            <Input value={o} onChange={(e) => s(e.target.value)} />
          </Field>
          <Field
            label={msg("Base URL")}
            hint={i.provider_type === `ollama` ? msg("Default: http://localhost:11434") : undefined}
          >
            <Input value={c} onChange={(e) => l(e.target.value)} placeholder="https://…" />
          </Field>
          {i.provider_type !== `ollama` && (
            <Field
              label={msg("API key{{v0}}", {
                v0: i.needs_key ? `` : ` (optional)`,
              })}
              hint={msg("Stored in your OS credential store when available; never sent to the browser again.")}
            >
              <Input type="password" autoComplete="off" value={u} onChange={(e) => d(e.target.value)} />
            </Field>
          )}
          {query.data?.secrets_warning && <Callout tone="warn">{query.data.secrets_warning}</Callout>}
          <div className="flex justify-between">
            <Button variant="ghost" onClick={() => a(null)}>
              {msg("Back")}
            </Button>
            <Button
              variant="primary"
              loading={y}
              disabled={i.needs_key && !u}
              onClick={async () => {
                if (i) {
                  b(true);
                  try {
                    let e = await apiPost(`/providers`, {
                      provider_type: i.provider_type,
                      display_name: o || i.display_name,
                      base_url: c || i.base_url,
                      api_key: u || null,
                      config:
                        i.display_name === `OpenRouter`
                          ? {
                              label: msg("OpenRouter"),
                            }
                          : {},
                    });
                    (p(e),
                      d(``),
                      queryClient.invalidateQueries({
                        queryKey: queryKeys.providers,
                      }));
                    let t = await apiPost(`/providers/${e.id}/test`, {});
                    v(t);
                  } catch (e) {
                    toast(errorMessage(e), `danger`);
                  } finally {
                    b(false);
                  }
                }
              }}
            >
              {msg("Save & test connection")}
            </Button>
          </div>
        </div>
      )}
      {f && (
        <div className="space-y-3">
          {g && (
            <Callout tone={g.ok ? `ok` : `warn`} title={g.ok ? msg("Connected") : msg("Connection test failed")}>
              {g.message}
              {!g.ok && (
                <p className="mt-1">
                  {msg(
                    "The provider was saved; fix the URL/key on its card and test again, or add a model ID manually.",
                  )}
                </p>
              )}
            </Callout>
          )}
          <p className="text-sm text-muted">{msg("Next, add the model(s) you want to use.")}</p>
          <div className="flex justify-end gap-2">
            <Button onClick={onClose}>{msg("Done")}</Button>
            <ProviderStatusBadge p={f} />
          </div>
        </div>
      )}
    </Modal>
  );
}

function ProviderStatusBadge({ p }) {
  let [t, n] = React.useState(false);
  return (
    <>
      <Button variant="primary" onClick={() => n(true)}>
        <Icon.Check className="size-4" /> {msg("Choose models")}
      </Button>
      {t && <AddModelDialog p={p} onClose={() => n(false)} />}
    </>
  );
}
