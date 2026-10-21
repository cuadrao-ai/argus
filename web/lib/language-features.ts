import { LANGUAGE_STORAGE_KEY, readStored, writeStored } from "./browser-storage";
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

/** What a reader knows when it picks the language. The server knows none of these. */
export type LanguageSources = {
  /** The signed-in account's saved language. */
  account?: string | null;
  /** The language this device last showed, or the shell's current one. */
  device?: string | null;
  /** The browser's own language, which only a consumer build reads. */
  browser?: string | null;
};

/** The one precedence every reader uses: account, then the device choice, then the browser on a consumer build, then the default. */
export function resolveLanguage(
  sources: LanguageSources,
  businessBuild: boolean = businessPilotEnabled,
  spanishEnabled: boolean = SPANISH_ENABLED,
): ArgusLanguage {
  const chosen = sources.account || sources.device || (businessBuild ? null : sources.browser);
  return chosen ? normalizeEnabledLanguage(chosen, spanishEnabled) : defaultLanguage(spanishEnabled, businessBuild);
}

/** The sources a browser can read. On the server there are none. */
export function browserLanguageSources(): LanguageSources {
  if (typeof window === "undefined") return {};
  const { language, languages } = window.navigator;
  const browser = languages?.find((code) => /^(en|es)/i.test(code)) ?? language;
  return { device: readStored(LANGUAGE_STORAGE_KEY), browser };
}

/** The device keeps the language the shell last showed, so the next visit starts there until the account is known. */
export function rememberShownLanguage(language: ArgusLanguage): void {
  writeStored(LANGUAGE_STORAGE_KEY, language);
}

/** The languages to read a key from, in order, when the shown language lacks it: an English reader never sees Spanish; a Spanish reader falls back to English; nothing shown yet starts from the default. */
export function fallbackChain(shown: string | undefined, defaultLanguage: ArgusLanguage): ArgusLanguage[] {
  if (shown?.toLowerCase().startsWith("en")) return ["en"];
  if (shown?.toLowerCase().startsWith("es")) return ["es-419", "en"];
  return defaultLanguage === "en" ? ["en"] : [defaultLanguage, "en"];
}

export const DEFAULT_LANGUAGE = defaultLanguage(SPANISH_ENABLED, businessPilotEnabled);

export function normalizeEnabledLanguage(language?: string | null, spanishEnabled: boolean = SPANISH_ENABLED): ArgusLanguage {
  if (spanishEnabled && language?.toLowerCase().startsWith("es")) {
    return "es-419";
  }
  return "en";
}

/** Moves the shell to what the account resolves to; with no account language the shell keeps what it shows. */
export async function commitShellLanguage(
  i18n: { language?: string; changeLanguage: (language: string) => Promise<unknown> },
  businessBuild: boolean,
  accountLanguage: string | null | undefined,
  spanishEnabled: boolean = SPANISH_ENABLED,
): Promise<void> {
  const next = resolveLanguage({ account: accountLanguage, device: i18n.language }, businessBuild, spanishEnabled);
  if (next === i18n.language) return;
  await i18n.changeLanguage(next);
}

/** How a resolved language is spelled on the document: Business spells Spanish `es`, a consumer page keeps `es-419`, English is `en` on both. */
export function documentLanguage(language: ArgusLanguage, businessBuild: boolean): "en" | "es" | "es-419" {
  return businessBuild && language === "es-419" ? "es" : language;
}

export function localeForLanguage(language?: string | null): ArgusLocale {
  return normalizeEnabledLanguage(language) === "es-419" ? "es-419" : "en-US";
}

export function languageDisplayAbbreviation(language?: string | null): "en" | "es" {
  return normalizeEnabledLanguage(language) === "es-419" ? "es" : "en";
}
