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

/** Where the shown language comes from. A Business build reads nothing, so a stored value and the browser cannot decide. A consumer build reads a saved choice, then the browser. */
export function languageDetectionOrder(businessBuild: boolean): readonly string[] {
  return businessBuild ? [] : ["localStorage", "navigator"];
}

/** Where a language change is written. A Business build writes nothing, so it cannot store English. A consumer build keeps the saved choice. */
export function languageDetectionCaches(businessBuild: boolean): readonly string[] {
  return businessBuild ? [] : ["localStorage"];
}

/** The languages to read a key from, in order, when the shown language lacks it: an English reader never sees Spanish; a Spanish reader falls back to English; nothing shown yet starts from the default. */
export function fallbackChain(shown: string | undefined, defaultLanguage: ArgusLanguage): ArgusLanguage[] {
  if (shown?.toLowerCase().startsWith("en")) return ["en"];
  if (shown?.toLowerCase().startsWith("es")) return ["es-419", "en"];
  return defaultLanguage === "en" ? ["en"] : [defaultLanguage, "en"];
}

export const DEFAULT_LANGUAGE = defaultLanguage(SPANISH_ENABLED, businessPilotEnabled);
export const LANGUAGE_DETECTION_ORDER = languageDetectionOrder(businessPilotEnabled);

export function normalizeEnabledLanguage(language?: string | null, spanishEnabled: boolean = SPANISH_ENABLED): ArgusLanguage {
  if (spanishEnabled && language?.toLowerCase().startsWith("es")) {
    return "es-419";
  }
  return "en";
}

/** Language a build may show. Business Spanish is always es-419. A consumer build shows the requested language. */
export function languageToShow(
  businessBuild: boolean,
  requested: string | null | undefined,
  spanishEnabled: boolean = SPANISH_ENABLED,
): string | null {
  if (businessBuild && spanishEnabled) return "es-419";
  return requested ?? null;
}

/** Language applied once the account is known. Business ignores the account and anything stored on the device. A consumer build keeps the account language. */
export function accountLanguageToApply(
  businessBuild: boolean,
  accountLanguage: string | null | undefined,
  spanishEnabled: boolean = SPANISH_ENABLED,
): string | null {
  if (businessBuild && spanishEnabled) return "es-419";
  return accountLanguage ?? null;
}

/** Switches the shell language. A Business build can only move to es-419. */
export async function commitShellLanguage(
  i18n: { language?: string; changeLanguage: (language: string) => Promise<unknown> },
  businessBuild: boolean,
  accountLanguage: string | null | undefined,
  spanishEnabled: boolean = SPANISH_ENABLED,
): Promise<void> {
  const resolved = accountLanguageToApply(businessBuild, accountLanguage, spanishEnabled);
  if (!resolved || resolved === i18n.language) return;
  if (businessBuild && resolved !== "es-419") return;
  await i18n.changeLanguage(resolved);
}

/** Document language. Business Spanish is `es` for the whole response. A consumer page stays `es-419` or `en`. */
export function documentLanguage(
  language: string | null | undefined,
  businessBuild: boolean,
  spanishEnabled: boolean = SPANISH_ENABLED,
): "en" | "es" | "es-419" {
  if (businessBuild && spanishEnabled) return "es";
  return normalizeEnabledLanguage(language, spanishEnabled);
}

export function localeForLanguage(language?: string | null): ArgusLocale {
  return normalizeEnabledLanguage(language) === "es-419" ? "es-419" : "en-US";
}

export function languageDisplayAbbreviation(language?: string | null): "en" | "es" {
  return normalizeEnabledLanguage(language) === "es-419" ? "es" : "en";
}
