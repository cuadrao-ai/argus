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

export const BUSINESS_BUILD =
  process.env.NEXT_PUBLIC_BUSINESS_PILOT_ENABLED === "true";

/** The language a visitor sees before any choice: Spanish on a Cuadrao Business build that ships it, English otherwise. */
export function defaultLanguage(spanishEnabled: boolean, businessBuild: boolean): ArgusLanguage {
  return spanishEnabled && businessBuild ? "es-419" : "en";
}

/** Where the shown language comes from, in order: a choice saved on this device; on a consumer build the browser's language too. The browser never decides on a Business build. */
export function languageDetectionOrder(businessBuild: boolean): readonly string[] {
  return businessBuild ? ["localStorage"] : ["localStorage", "navigator"];
}

export const DEFAULT_LANGUAGE = defaultLanguage(SPANISH_ENABLED, BUSINESS_BUILD);
export const LANGUAGE_DETECTION_ORDER = languageDetectionOrder(BUSINESS_BUILD);

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
