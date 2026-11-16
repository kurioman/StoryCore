// First-run assistant (v0.5, roadmap phase 5) at #/setup, full screen over the starry sky. Shown the first time
// "Start your next adventure" is clicked (setting onboarding_done), and from the welcome gear menu. Steps: language,
// where the AI runs (this PC / online), model advice and connection (reusing Settings > Providers' guides), a short
// tour, then the story library. "Skip" is always there.
import * as React from "react";
import * as Icon from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPut } from "@/api/legacy";
import { queryKeys } from "@/api/queries";
import { LANGUAGES, msg, setLanguageLive, shownLanguage } from "@/i18n";
import { navigate } from "@/lib/router";
import { cn } from "@/lib/util";
import { ProvidersQuickSetup } from "@/features/settings/Providers";
import { Starfield } from "@/features/welcome/Starfield";
import { CLOUD_MODELS, ROCINANTE, VRAM_CHOICES, rocinanteFor } from "@/features/setup/recommendations";

const STEPS = [`welcome`, `where`, `connect`, `tour`];

export function SetupPage() {
  let [step, setStep] = React.useState(0),
    [lang, setLang] = React.useState(shownLanguage()),
    [where, setWhere] = React.useState(null),
    queryClient = useQueryClient();

  async function finish(to = `/library`) {
    try {
      await apiPut(`/settings`, { onboarding_done: true });
      queryClient.invalidateQueries({ queryKey: queryKeys.settings });
    } catch {
      /* the assistant simply shows again next time */
    }
    navigate(to);
  }

  return (
    <div className="sc-welcome relative h-full overflow-hidden" lang={lang}>
      <Starfield className="absolute inset-0 size-full opacity-60" />
      <div className="sc-welcome-vignette pointer-events-none absolute inset-0" />
      <div className="relative z-[1] flex h-full flex-col">
        <header className="flex items-center gap-4 px-6 pt-5">
          <div className="flex gap-1.5" aria-label={msg("Step {{v0}} of {{v1}}", { v0: step + 1, v1: STEPS.length })}>
            {STEPS.map((s, i) => (
              <span key={s} className={cn(`sc-su-dot`, i === step && `sc-su-dot-on`, i < step && `sc-su-dot-done`)} />
            ))}
          </div>
          <button className="ml-auto text-sm text-[#e2bd72aa] hover:text-[#fff0c4]" onClick={() => finish()}>
            {msg("Skip")} <Icon.ChevronsRight className="inline size-4" />
          </button>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto px-6 pb-10">
          <div className="mx-auto max-w-4xl pt-6">
            {step === 0 && (
              <Welcome
                lang={lang}
                onLang={(c) => {
                  setLanguageLive(c);
                  setLang(c);
                }}
                onNext={() => setStep(1)}
              />
            )}
            {step === 1 && (
              <Where
                where={where}
                onPick={(w) => {
                  setWhere(w);
                  setStep(2);
                }}
                onBack={() => setStep(0)}
              />
            )}
            {step === 2 && (where === `local` ? <Local /> : <Cloud />)}
            {step === 2 && (
              <Nav onBack={() => setStep(1)} onNext={() => setStep(3)} nextLabel={msg("Continue")} />
            )}
            {step === 3 && <Tour onBack={() => setStep(2)} onDone={() => finish()} />}
          </div>
        </main>
      </div>
    </div>
  );
}

function Nav({ onBack, onNext, nextLabel }) {
  return (
    <div className="mt-8 flex items-center gap-3">
      {onBack && (
        <button className="sc-su-ghost" onClick={onBack}>
          <Icon.ArrowLeft className="size-4" /> {msg("Back")}
        </button>
      )}
      {onNext && (
        <button className="sc-lib-cta ml-auto px-6 py-2.5 text-base" onClick={onNext}>
          {nextLabel} <Icon.ArrowRight className="size-4" />
        </button>
      )}
    </div>
  );
}

function Welcome({ lang, onLang, onNext }) {
  return (
    <div className="pt-[6vh] text-center">
      <h1 className="sc-brand text-[clamp(2.2rem,6vmin,3.6rem)] leading-tight text-[#f3dca0]">{msg("Welcome to StoryCore")}</h1>
      <p className="mx-auto mt-4 max-w-xl text-[#ece6d8cc]">
        {msg("A few minutes to set things up, and your first adventure can begin. You can skip this at any time.")}
      </p>
      <p className="sc-lib-h3 mt-10">{msg("Language")}</p>
      <div className="flex justify-center gap-3">
        {LANGUAGES.map((l) => (
          <button key={l.code} onClick={() => onLang(l.code)} className={cn(`sc-su-choice min-w-40`, lang === l.code && `sc-su-choice-on`)}>
            {l.label}
          </button>
        ))}
      </div>
      <button className="sc-lib-cta mt-12 px-8 py-3 text-lg" onClick={onNext}>
        {msg("Let's go")} <Icon.ArrowRight className="size-5" />
      </button>
    </div>
  );
}

function Where({ where, onPick, onBack }) {
  return (
    <div>
      <h2 className="sc-brand text-center text-3xl text-[#f3dca0]">{msg("Where should the AI run?")}</h2>
      <p className="mx-auto mt-3 max-w-2xl text-center text-sm text-[#ece6d8b3]">
        {msg("The AI writes the story. It can run on your own computer, or on an online service.")}
      </p>
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <button className={cn(`sc-su-card`, where === `local` && `sc-su-choice-on`)} onClick={() => onPick(`local`)}>
          <Icon.Monitor className="size-9 text-[#e2bd72]" />
          <p className="sc-brand mt-3 text-xl text-[#f3dca0]">{msg("On my computer")}</p>
          <ul className="mt-3 space-y-1.5 text-left text-sm text-[#ece6d8cc]">
            <li>✓ {msg("Free and private: nothing leaves your PC")}</li>
            <li>✓ {msg("Works without internet")}</li>
            <li className="text-[#e2bd72aa]">• {msg("Needs a graphics card with enough video memory (8 GB or more is best)")}</li>
          </ul>
        </button>
        <button className={cn(`sc-su-card`, where === `cloud` && `sc-su-choice-on`)} onClick={() => onPick(`cloud`)}>
          <Icon.Cloud className="size-9 text-[#e2bd72]" />
          <p className="sc-brand mt-3 text-xl text-[#f3dca0]">{msg("Online")}</p>
          <ul className="mt-3 space-y-1.5 text-left text-sm text-[#ece6d8cc]">
            <li>✓ {msg("The best writing quality")}</li>
            <li>✓ {msg("Fast, even on a modest computer")}</li>
            <li className="text-[#e2bd72aa]">• {msg("Paid per use (from a few cents to a few euros per session) and needs internet")}</li>
          </ul>
        </button>
      </div>
      <Nav onBack={onBack} />
    </div>
  );
}

function Local() {
  let gpu = useQuery({ queryKey: [`gpu`], queryFn: () => apiGet(`/system/gpu`), staleTime: Infinity }),
    detected = gpu.data?.gpus?.[0],
    [vram, setVram] = React.useState(null),
    v = vram ?? (detected ? detected.vram_gb : null),
    rec = v != null ? rocinanteFor(v) : null,
    activeChoice = v != null ? Math.max(...VRAM_CHOICES.filter((g) => g <= Math.round(v) + 0.5), VRAM_CHOICES[0]) : null;
  return (
    <div>
      <h2 className="sc-brand text-3xl text-[#f3dca0]">{msg("Running the AI on your computer")}</h2>
      <div className="sc-su-panel mt-6">
        <p className="sc-lib-h3">{msg("Your graphics card")}</p>
        {gpu.isLoading ? (
          <p className="text-sm text-[#ece6d8b3]">{msg("Looking for your graphics card…")}</p>
        ) : detected ? (
          <p className="text-sm text-[#ece6d8]">
            <Icon.Cpu className="mr-1.5 inline size-4 text-[#e2bd72]" />
            {msg("Detected: {{v0}} with {{v1}} GB of video memory (VRAM).", { v0: detected.name, v1: Math.round(detected.vram_gb) })}
          </p>
        ) : (
          <p className="text-sm text-[#ece6d8b3]">
            {msg("Your card could not be detected automatically (this works for NVIDIA cards). Choose its video memory (VRAM):")}
          </p>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          {VRAM_CHOICES.map((g) => (
            <button
              key={g}
              onClick={() => setVram(g)}
              className={cn(`sc-mu-chip`, g === activeChoice && `sc-mu-chip-on`)}
            >
              {g === 24 ? msg("{{v0}} GB or more", { v0: g }) : msg("{{v0}} GB", { v0: g })}
            </button>
          ))}
        </div>
      </div>

      {rec && (
        <div className="sc-su-panel mt-4">
          <p className="sc-lib-h3">{msg("Our recommendation")}</p>
          <p className="sc-brand text-2xl text-[#f3dca0]">{ROCINANTE.name}</p>
          <p className="text-xs text-[#e2bd72aa]">
            {msg("by {{v0}} · made for roleplay and storytelling", { v0: ROCINANTE.author })}
          </p>
          <p className="mt-3 text-sm text-[#ece6d8]">
            {msg("For your card, download the {{v0}} version (about {{v1}} GB) and load it with a context length of {{v2}}.", {
              v0: rec.quant,
              v1: String(rec.size).replace(`.`, shownLanguage() === `fr` ? `,` : `.`),
              v2: rec.context,
            })}
            {rec.lighter && ` ${msg("If replies are slow, take {{v0}} instead (lighter).", { v0: rec.lighter })}`}
          </p>
          <div className={cn(`mt-4 flex gap-2.5 rounded-lg p-3 text-sm`, rec.fits ? `bg-[#e2bd7212] text-[#ece6d8cc]` : `bg-[#e0715f1f] text-[#ffd3cb]`)}>
            <Icon.Info className="mt-0.5 size-4 shrink-0" />
            <p>
              {!rec.fits && `${msg("This model is bigger than your video memory.")} `}
              {msg(
                "You can use a model larger than your video memory: it still works, but part of it then runs from the computer's normal memory, and every reply takes much longer to write (often several times slower).",
              )}
              {!rec.fits && ` ${msg("With little video memory, the online option is usually more pleasant.")}`}
            </p>
          </div>
          <ol className="mt-5 space-y-2.5 text-sm text-[#ece6d8]">
            {[
              <>
                {msg("Install LM Studio (free):")}{" "}
                <a className="text-[#f3d48c] underline" href="https://lmstudio.ai" target="_blank" rel="noreferrer">
                  lmstudio.ai
                </a>
              </>,
              msg("In LM Studio, open the search (magnifying glass), type {{v0}} and download the {{v1}} version.", {
                v0: ROCINANTE.search,
                v1: rec.quant,
              }),
              msg("Load the model, and set its context length to {{v0}} before loading.", { v0: rec.context }),
              msg("Open the Developer tab and start the server (Status: Running)."),
              msg("Come back here and click Detect below, then Use this model."),
            ].map((t, i) => (
              <li key={i} className="flex gap-3">
                <span className="sc-su-num">{i + 1}</span>
                <span className="pt-0.5">{t}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
      <div className="sc-su-panel sc-su-embed mt-4">
        <ProvidersQuickSetup path="lmstudio" hideChooser />
      </div>
    </div>
  );
}

function Cloud() {
  return (
    <div>
      <h2 className="sc-brand text-3xl text-[#f3dca0]">{msg("Using an online AI")}</h2>
      <p className="mt-3 text-sm text-[#ece6d8b3]">
        {msg(
          "The simplest way is OpenRouter: one account and one key give access to all the models below. You pay only for what you use, with credit you top up yourself.",
        )}
      </p>
      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        {CLOUD_MODELS.map((m) => (
          <div key={m.id} className="sc-su-panel">
            <div className="flex items-baseline gap-2">
              <p className="sc-brand text-xl text-[#f3dca0]">{m.name}</p>
              <span className="text-xs text-[#e2bd72aa]">{m.maker}</span>
              <span className="ml-auto text-sm tracking-widest text-[#f3d48c]" title={msg("Price")}>
                {`€€€`.slice(0, m.cost)}
                <span className="text-[#e2bd7240]">{`€€€`.slice(m.cost)}</span>
              </span>
            </div>
            <p className="mt-2 text-sm text-[#ece6d8cc]">✓ {m.pros}</p>
            <p className="mt-1 text-sm text-[#e2bd72aa]">• {m.cons}</p>
            <p className="mt-2 text-xs text-[#ece6d899]">{msg("In the catalogue below, search: {{v0}}", { v0: m.search })}</p>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-[#ece6d899]">
        {msg("Prices change often: check them in the catalogue before choosing. Claude, Mistral and others can also be connected directly with their own key in Settings > Providers & models.")}
      </p>
      <div className="sc-su-panel sc-su-embed mt-5">
        <ProvidersQuickSetup path="openrouter" hideChooser />
      </div>
    </div>
  );
}

function Tour({ onBack, onDone }) {
  let items = [
    [Icon.Library, msg("Library"), msg("Choose a story, read its summary and pick how it begins. Your games in progress are at the top.")],
    [Icon.BookOpenText, msg("Codex"), msg("During a game, the Codex button lists the characters and places you have discovered.")],
    [Icon.Music, msg("Music"), msg("Add your .mp3 files in the Music page and tag them: the music then follows the story's mood and places.")],
    [Icon.ScrollText, msg("Recap"), msg("The golden button sums up the story so far, handy when you come back after a break.")],
    [Icon.Bug, msg("Report a problem"), msg("The red button makes a small file to send us when something goes wrong. Your stories are never inside.")],
  ];
  return (
    <div>
      <h2 className="sc-brand text-center text-3xl text-[#f3dca0]">{msg("A quick tour")}</h2>
      <div className="mt-8 grid gap-3 sm:grid-cols-2">
        {items.map(([I, t, d]) => (
          <div key={t} className="sc-su-panel flex gap-4">
            <I className="mt-0.5 size-7 shrink-0 text-[#e2bd72]" />
            <div>
              <p className="font-semibold text-[#f3dca0]">{t}</p>
              <p className="mt-1 text-sm text-[#ece6d8cc]">{d}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-10 text-center">
        <button className="sc-lib-cta px-8 py-3 text-lg" onClick={onDone}>
          <Icon.Sparkles className="size-5" /> {msg("Start my first adventure")}
        </button>
      </div>
      <Nav onBack={onBack} />
    </div>
  );
}
