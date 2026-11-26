// Display sizes of the play screen, chosen in Settings > Appearance (test report of 26 Nov 2026): story text,
// portraits and the writing box. Saved on this device only (a phone and a computer want different sizes) and applied
// as CSS variables on <html> (--sc-text, --sc-portrait, --sc-composer; see the end of styles.css).
import * as React from "react";

const KEY = `lsd:display`;
export const DISPLAY_DEFAULTS = { text: 1, portraits: 1, composer: 1 };
export const DISPLAY_RANGES = { text: [0.8, 1.5], portraits: [0.5, 1.6], composer: [0.8, 1.5] };

export function readDisplay() {
  try {
    return { ...DISPLAY_DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || `{}`) };
  } catch {
    return { ...DISPLAY_DEFAULTS };
  }
}

export function applyDisplay(p) {
  let s = document.documentElement.style;
  s.setProperty(`--sc-text`, String(p.text));
  s.setProperty(`--sc-portrait`, String(p.portraits));
  s.setProperty(`--sc-composer`, String(p.composer));
}

export function useDisplayPrefs() {
  let [prefs, setPrefs] = React.useState(readDisplay);
  let update = React.useCallback((next) => {
    setPrefs(next);
    applyDisplay(next);
    try {
      localStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      /* private mode: the sizes still apply until the app is closed */
    }
  }, []);
  return [prefs, update];
}

if (typeof document !== `undefined`) applyDisplay(readDisplay());
