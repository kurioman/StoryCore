// Welcome page (v1.8, roadmap phase 1): full screen, no sidebar. Big logo and outlined title with a soft light
// behind it, the motto, one big "Start your next adventure" button (to the story library) and the settings gear
// (language, all settings). The starfield behind loops from the centre outwards and reacts to the mouse; on hover
// the button lights up, trembles with impatience and absorbs the stars that come near.
import * as React from "react";
import * as Popover from "@radix-ui/react-popover";
import { Check, Languages, Settings, SlidersHorizontal } from "lucide-react";
import { LANGUAGES, msg, setLanguageLive, shownLanguage, type Language } from "@/i18n";
import { navigate } from "@/lib/router";
import { Starfield, type StarfieldHandle } from "./Starfield";

export function WelcomePage() {
  const stars = React.useRef<StarfieldHandle>(null);
  const button = React.useRef<HTMLButtonElement>(null);
  const [language, setLanguage] = React.useState<Language>(shownLanguage());

  function attract(on: boolean) {
    const r = button.current?.getBoundingClientRect();
    stars.current?.setAttractor(on && r ? { x: r.left, y: r.top, width: r.width, height: r.height } : null);
  }

  function pickLanguage(code: Language) {
    setLanguageLive(code);
    setLanguage(code);
  }

  return (
    <div className="sc-welcome relative h-full overflow-hidden" lang={language}>
      <Starfield ref={stars} className="absolute inset-0 size-full" />
      <div className="sc-welcome-vignette pointer-events-none absolute inset-0" />

      <Popover.Root>
        <Popover.Trigger asChild>
          <button
            type="button"
            aria-label={msg("Settings")}
            title={msg("Settings")}
            className="sc-gear absolute right-5 top-5 z-10 inline-flex size-12 items-center justify-center rounded-full"
          >
            <Settings className="size-7" strokeWidth={1.75} />
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

      <main className="relative z-[1] flex h-full flex-col items-center justify-center px-6 pb-[16vh] text-center">
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

        <button
          ref={button}
          type="button"
          onClick={() => navigate(`/library`)}
          onPointerEnter={() => attract(true)}
          onPointerLeave={() => attract(false)}
          onFocus={() => attract(true)}
          onBlur={() => attract(false)}
          className="sc-start"
        >
          <span className="sc-start-shine" aria-hidden />
          <span className="relative">{msg("Start your next adventure")}</span>
        </button>
      </main>
    </div>
  );
}
