import { businessPilotEnabled } from "./private-alpha-flags";

export type ArgusLanguage = "en" | "es-419";
export type ArgusLocale = "en-US" | "es-419";

export type ArgusLanguageOption = {
  code: ArgusLanguage;
  name: string;
  translation: string;
};

export const ALL_LANGUAGES: ArgusLanguageOption[] = [
  { code: "en", name: "English", translation: "English" },
  { code: "es-419", name: "Español", translation: "Spanish" },
];

export const SPANISH_ENABLED =
  process.env.NEXT_PUBLIC_ENABLE_SPANISH === "true";

export const ENABLED_LANGUAGES = ALL_LANGUAGES.filter(
  (language) => language.code === "en" || SPANISH_ENABLED,
);

export const ENABLED_LANGUAGE_CODES = ENABLED_LANGUAGES.map(
  (language) => language.code,
);

/** The language a visitor sees before any choice: Spanish on a Cuadrao Business build that ships it, English otherwise. */
export function defaultLanguage(spanishEnabled: boolean, businessBuild: boolean): ArgusLanguage {
  return spanishEnabled && businessBuild ? "es-419" : "en";
}

/** Where the shown language comes from, in order: a choice saved on this device; on a consumer build the browser's language too. The browser never decides on a Business build. */
export function languageDetectionOrder(businessBuild: boolean): readonly string[] {
  return businessBuild ? ["localStorage"] : ["localStorage", "navigator"];
}

/** The languages to read a key from, in order, when the shown language lacks it: an English reader never sees Spanish; a Spanish reader falls back to English; nothing shown yet starts from the default. */
export function fallbackChain(shown: string | undefined, defaultLanguage: ArgusLanguage): ArgusLanguage[] {
  if (shown?.toLowerCase().startsWith("en")) return ["en"];
  if (shown?.toLowerCase().startsWith("es")) return ["es-419", "en"];
  return defaultLanguage === "en" ? ["en"] : [defaultLanguage, "en"];
}

export const DEFAULT_LANGUAGE = defaultLanguage(SPANISH_ENABLED, businessPilotEnabled);
export const LANGUAGE_DETECTION_ORDER = languageDetectionOrder(businessPilotEnabled);

export function normalizeEnabledLanguage(language?: string | null): ArgusLanguage {
  if (SPANISH_ENABLED && language?.toLowerCase().startsWith("es")) {
    return "es-419";
  }
  return "en";
}

export function localeForLanguage(language?: string | null): ArgusLocale {
  return normalizeEnabledLanguage(language) === "es-419" ? "es-419" : "en-US";
}

export function languageDisplayAbbreviation(language?: string | null): "en" | "es" {
  return normalizeEnabledLanguage(language) === "es-419" ? "es" : "en";
}
