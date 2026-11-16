// Welcome page (v1.8, roadmap phase 1): full screen, no sidebar. Big logo and title, the motto, one big
// "Start your next adventure" button (to the story library) and the settings gear. The starfield behind is animated
// and reacts to the mouse; on hover the button lights up and draws the nearby stars to it.
import * as React from "react";
import { Settings } from "lucide-react";
import { msg } from "@/i18n";
import { navigate } from "@/lib/router";
import { Starfield, type StarfieldHandle } from "./Starfield";

export function WelcomePage() {
  const stars = React.useRef<StarfieldHandle>(null);
  const button = React.useRef<HTMLButtonElement>(null);

  function attract(on: boolean) {
    const r = button.current?.getBoundingClientRect();
    stars.current?.setAttractor(on && r ? { x: r.left + r.width / 2, y: r.top + r.height / 2 } : null);
  }

  return (
    <div className="sc-welcome relative h-full overflow-hidden">
      <Starfield ref={stars} className="absolute inset-0 size-full" />
      <div className="sc-welcome-vignette pointer-events-none absolute inset-0" />

      <button
        type="button"
        onClick={() => navigate(`/settings`)}
        aria-label={msg("Settings")}
        title={msg("Settings")}
        className="sc-gear absolute right-5 top-5 z-10 inline-flex size-12 items-center justify-center rounded-full"
      >
        <Settings className="size-7" strokeWidth={1.75} />
      </button>

      <main className="relative z-[1] flex h-full flex-col items-center justify-center px-6 pb-[6vh] text-center">
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

        <h1 className="sc-welcome-title">{msg("StoryCore")}</h1>
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
