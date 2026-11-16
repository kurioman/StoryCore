// Welcome page (v1.8, roadmap phase 1): full screen, no sidebar. Logo and outlined title near the top, a light in the
// middle that the stars are born from, the big "Start your next adventure" button (to the story library), a quiet
// "Resume" link (not active yet), the settings gear (language, all settings) and a footer: credits, Discord, version.
// On hover the button lights up, trembles and absorbs the stars that come near; on click the stars jump to light speed.
import * as React from "react";
import * as Popover from "@radix-ui/react-popover";
import { useQuery } from "@tanstack/react-query";
import { Check, History, Languages, MessagesSquare, Settings, SlidersHorizontal } from "lucide-react";
import { apiGet } from "@/api/legacy";
import { LANGUAGES, msg, setLanguageLive, shownLanguage, type Language } from "@/i18n";
import { CREDITS, DISCORD_URL } from "@/lib/links";
import { navigate } from "@/lib/router";
import { cn } from "@/lib/util";
import { Starfield, type StarfieldHandle } from "./Starfield";

export function WelcomePage() {
  const stars = React.useRef<StarfieldHandle>(null);
  const button = React.useRef<HTMLButtonElement>(null);
  const [language, setLanguage] = React.useState<Language>(shownLanguage());
  const [leaving, setLeaving] = React.useState(false);
  const health = useQuery({ queryKey: [`health`], queryFn: () => apiGet<{ version: string }>(`/health`) });

  function attract(on: boolean) {
    if (leaving) return;
    const r = button.current?.getBoundingClientRect();
    stars.current?.setAttractor(on && r ? { x: r.left, y: r.top, width: r.width, height: r.height } : null);
  }

  function pickLanguage(code: Language) {
    setLanguageLive(code);
    setLanguage(code);
  }

  async function start() {
    if (leaving) return;
    setLeaving(true);
    await stars.current?.warp();
    navigate(`/library`);
  }

  return (
    <div className={cn(`sc-welcome relative h-full overflow-hidden`, leaving && `sc-leaving`)} lang={language}>
      <Starfield ref={stars} className="absolute inset-0 size-full" />
      <div className="sc-welcome-vignette pointer-events-none absolute inset-0" />
      <div className="sc-warp-flash pointer-events-none absolute inset-0 z-20" />

      <Popover.Root>
        <Popover.Trigger asChild>
          <button
            type="button"
            aria-label={msg("Settings")}
            title={msg("Settings")}
            className="sc-glow-btn absolute right-5 top-5 z-10 inline-flex size-12 items-center justify-center rounded-full"
          >
            <Settings className="sc-gear-icon size-7" strokeWidth={1.75} />
          </button>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content align="end" sideOffset={10} className="sc-menu z-50 w-60 p-2">
            <p className="flex items-center gap-2 px-2 pb-1.5 pt-1 text-xs font-medium uppercase tracking-wider text-[#e2bd72b0]">
              <Languages className="size-3.5" /> {msg("Language")}
            </p>
            {LANGUAGES.map((l) => (
              <button
                type="button"
                key={l.code}
                onClick={() => pickLanguage(l.code)}
                aria-pressed={language === l.code}
                className="sc-menu-item"
              >
                <span className="flex-1 text-left">{l.label}</span>
                {language === l.code && <Check className="size-4" />}
              </button>
            ))}
            <div className="my-1.5 h-px bg-[#e2bd7226]" />
            <button type="button" onClick={() => navigate(`/settings`)} className="sc-menu-item">
              <SlidersHorizontal className="size-4" />
              <span className="flex-1 text-left">{msg("All settings")}</span>
            </button>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>

      <main className="sc-welcome-layout relative z-[1] h-full px-6 text-center">
        <header className="sc-welcome-head flex flex-col items-center">
          <div className="sc-welcome-logo" aria-hidden>
            <svg viewBox="0 0 32 32" className="size-full">
              <defs>
                <linearGradient id="sc-logo-gold" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0" stopColor="#fbe4a3" />
                  <stop offset="0.5" stopColor="#e2bd72" />
                  <stop offset="1" stopColor="#b48a43" />
                </linearGradient>
              </defs>
              <path
                d="M16 2.5 L19.2 12.8 L29.5 16 L19.2 19.2 L16 29.5 L12.8 19.2 L2.5 16 L12.8 12.8 Z"
                fill="url(#sc-logo-gold)"
              />
              <circle cx="16" cy="16" r="2.4" fill="#0b1030" />
            </svg>
          </div>
          <div className="sc-title-wrap">
            <div className="sc-title-halo" aria-hidden />
            <h1 className="sc-welcome-title" data-text={msg("StoryCore")}>
              {msg("StoryCore")}
            </h1>
          </div>
          <p className="sc-welcome-motto">{msg("Your imagination, brought to life by AI")}</p>
        </header>

        <div aria-hidden />

        <div className="flex flex-col items-center">
          <button
            ref={button}
            type="button"
            onClick={start}
            onPointerEnter={() => attract(true)}
            onPointerLeave={() => attract(false)}
            onFocus={() => attract(true)}
            onBlur={() => attract(false)}
            className="sc-start"
          >
            <span className="sc-start-shine" aria-hidden />
            <span className="relative">{msg("Start your next adventure")}</span>
          </button>
          <button
            type="button"
            aria-disabled
            title={msg("Coming soon")}
            onClick={(e) => e.preventDefault()}
            className="sc-resume"
          >
            <History className="size-3.5" /> {msg("Resume my last adventure")}
          </button>
        </div>

        <div aria-hidden />

        <footer className="sc-welcome-foot grid grid-cols-[1fr_auto_1fr] items-center gap-4 pb-4 text-[12px]">
          <p className="text-left text-[#e2bd7299]">{msg(CREDITS)}</p>
          <button
            type="button"
            onClick={() => DISCORD_URL && window.open(DISCORD_URL, `_blank`, `noopener`)}
            aria-label={msg("Discord")}
            title={DISCORD_URL ? msg("Join us on Discord") : msg("Discord (link coming soon)")}
            className="sc-glow-btn relative inline-flex size-11 items-center justify-center rounded-full"
          >
            <MessagesSquare className="size-6" strokeWidth={1.75} />
          </button>
          <p className="text-right text-[#e2bd7299]">{health.data?.version ? `v${health.data.version}` : ``}</p>
        </footer>
      </main>
    </div>
  );
}
