// Interface language. Keys are the English texts themselves (gettext style): `msg("Save")`, and placeholders use
// i18next's {{name}} syntax: `msg("In {{v0}} story(ies)", { v0: n })`. English needs no file (the key is the text);
// other languages are flat JSON maps in ./locales/<lang>.json (English text -> translation).
// Locales/en.json lists every key the code uses, as the base for translators (regenerate: npm run i18n:extract).
import i18next from "i18next";

export const LANGUAGES = [{ code: "en", label: "English" }] as const;
export type Language = (typeof LANGUAGES)[number]["code"];

const STORAGE_KEY = "lsd:language";

function initialLanguage(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) || "en";
  } catch {
    return "en";
  }
}

void i18next.init({
  lng: initialLanguage(),
  fallbackLng: "en",
  resources: { en: { translation: {} } },
  keySeparator: false, // keys are sentences: dots and colons are part of the text
  nsSeparator: false,
  returnEmptyString: false,
  interpolation: { escapeValue: false }, // React escapes text already
});

/** Translate an English interface text. Missing translations fall back to the English text itself. */
export function msg(text: string, vars?: Record<string, unknown>): string {
  return i18next.t(text, { defaultValue: text, ...(vars ?? {}) }) as string;
}

export function setLanguage(code: string) {
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    /* private mode: the choice lasts for this session only */
  }
  void i18next.changeLanguage(code);
}

export { i18next };
