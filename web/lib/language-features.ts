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

/** Every enabled language except the one already shown. */
export function landingLanguageChoices(
  shown: ArgusLanguage,
  languages: readonly ArgusLanguageOption[] = ENABLED_LANGUAGES,
): readonly ArgusLanguageOption[] {
  return languages.filter((language) => language.code !== shown);
}

/** The language shown when nothing is saved: Spanish on a Business build that ships it, English otherwise. */
export function defaultLanguage(spanishEnabled: boolean, businessBuild: boolean): ArgusLanguage {
  return spanishEnabled && businessBuild ? "es-419" : "en";
}

/** Where the shown language is read from, first match wins. Only a consumer build lets the browser language decide. */
export function languageDetectionOrder(businessBuild: boolean): readonly string[] {
  return businessBuild ? ["localStorage"] : ["localStorage", "navigator"];
}

/** The one place a language choice is written. */
export const LANGUAGE_DETECTION_CACHES = ["localStorage"] as const;

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

/** Moves the shell to the account language. The build does not change the outcome. */
export async function commitShellLanguage(
  i18n: { language?: string; changeLanguage: (language: string) => Promise<unknown> },
  businessBuild: boolean,
  accountLanguage: string | null | undefined,
): Promise<void> {
  if (!accountLanguage || accountLanguage === i18n.language) return;
  await i18n.changeLanguage(accountLanguage);
}

/** Document language. Business spells Spanish `es`; a consumer page keeps `es-419`. English is `en` on both. */
export function documentLanguage(
  language: string | null | undefined,
  businessBuild: boolean,
  spanishEnabled: boolean = SPANISH_ENABLED,
): "en" | "es" | "es-419" {
  const shown = normalizeEnabledLanguage(
    language ?? defaultLanguage(spanishEnabled, businessBuild),
    spanishEnabled,
  );
  return businessBuild && shown === "es-419" ? "es" : shown;
}

export function localeForLanguage(language?: string | null): ArgusLocale {
  return normalizeEnabledLanguage(language) === "es-419" ? "es-419" : "en-US";
}

export function languageDisplayAbbreviation(language?: string | null): "en" | "es" {
  return normalizeEnabledLanguage(language) === "es-419" ? "es" : "en";
}
