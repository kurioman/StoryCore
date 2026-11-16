// Interface language. Keys are the English texts themselves (gettext style): `msg("Save")`, and placeholders use
// i18next's {{name}} syntax: `msg("In {{v0}} story(ies)", { v0: n })`. English needs no file (the key is the text);
// other languages are flat JSON maps in ./locales/<lang>.json (English text -> translation).
// locales/en.json lists every key the code uses, as the base for translators (npm run i18n:check reports gaps).
//
// Changing the language reloads the page: some labels are computed once when a module loads (tab lists, tour steps),
// and a reload is the simplest way to be sure every one of them is in the new language.
import i18next from "i18next";
import fr from "./locales/fr.json";

export const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "fr", label: "Français" },
] as const;
export type Language = (typeof LANGUAGES)[number]["code"];

const STORAGE_KEY = "lsd:language";

function initialLanguage(): Language {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && LANGUAGES.some((l) => l.code === saved)) return saved as Language;
  } catch {
    /* storage unavailable: English */
  }
  return "en";
}

export const currentLanguage: Language = initialLanguage();

void i18next.init({
  lng: currentLanguage,
  fallbackLng: "en",
  resources: { en: { translation: {} }, fr: { translation: fr } },
  initAsync: false, // ready before the first module computes a label
  keySeparator: false, // keys are sentences: dots and colons are part of the text
  nsSeparator: false,
  returnEmptyString: false,
  interpolation: { escapeValue: false }, // React escapes text already
});
document.documentElement.lang = currentLanguage;

/** Translate an English interface text. Missing translations fall back to the English text itself. */
export function msg(text: string, vars?: Record<string, unknown>): string {
  return i18next.t(text, { defaultValue: text, ...(vars ?? {}) }) as string;
}

/** A data key from the server ("secret_revealed", "power_system"...) shown as words, translated when known. */
export function msgKey(value: string | null | undefined): string {
  if (!value) return value ?? "";
  return msg(String(value).replace(/_/g, " "));
}

/** Switch the interface language (saved in this browser) and reload so every label follows. */
export function setLanguage(code: Language) {
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    /* private mode: the choice lasts for this page only */
  }
  if (code !== currentLanguage) window.location.reload();
}

let reloadOnLeave = false;

/** Switch the language without leaving the page (welcome page). Only that page re-renders now; the next navigation
 *  reloads the app so labels computed once by other modules follow too (see navigate() in lib/router). */
export function setLanguageLive(code: Language) {
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    /* private mode: the choice lasts for this page only */
  }
  void i18next.changeLanguage(code);
  document.documentElement.lang = code;
  reloadOnLeave = code !== currentLanguage;
}

/** The language shown right now (can differ from currentLanguage after setLanguageLive). */
export function shownLanguage(): Language {
  return (LANGUAGES.some((l) => l.code === i18next.language) ? i18next.language : "en") as Language;
}

export function needsReloadOnLeave(): boolean {
  return reloadOnLeave;
}

export { i18next };
