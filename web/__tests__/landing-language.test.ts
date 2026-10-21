import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import english from "../public/locales/en/common.json";
import spanish from "../public/locales/es-419/common.json";
import { ALL_LANGUAGES, LANGUAGE_DETECTION_CACHES, commitShellLanguage, defaultLanguage, documentLanguage, fallbackChain, landingLanguageChoices, languageDetectionOrder } from "../lib/language-features";

const root = join(import.meta.dir, "..");

describe("the language a visitor sees first", () => {
  test("Spanish is the default on a Business build that ships it; English elsewhere", () => {
    expect(defaultLanguage(true, true)).toBe("es-419");
    expect(defaultLanguage(true, false)).toBe("en");
    expect(defaultLanguage(false, true)).toBe("en");
    expect(defaultLanguage(false, false)).toBe("en");
  });

  test("a saved choice on the device wins on both builds; only a consumer build then reads the browser", () => {
    expect(languageDetectionOrder(true)).toEqual(["localStorage"]);
    expect(languageDetectionOrder(false)).toEqual(["localStorage", "navigator"]);
    expect([...LANGUAGE_DETECTION_CACHES]).toEqual(["localStorage"]);
  });

  test("the account language wins over the shell language on both builds", async () => {
    const shellAt = (language: string) => {
      const calls: string[] = [];
      return {
        calls,
        shell: {
          language,
          changeLanguage: async (next: string) => {
            calls.push(next);
          },
        },
      };
    };
    for (const businessBuild of [true, false]) {
      const toEnglish = shellAt("es-419");
      await commitShellLanguage(toEnglish.shell, businessBuild, "en");
      expect(toEnglish.calls).toEqual(["en"]);
      const toSpanish = shellAt("en");
      await commitShellLanguage(toSpanish.shell, businessBuild, "es-419");
      expect(toSpanish.calls).toEqual(["es-419"]);
      const noAccount = shellAt("es-419");
      await commitShellLanguage(noAccount.shell, businessBuild, null);
      await commitShellLanguage(noAccount.shell, businessBuild, undefined);
      await commitShellLanguage(noAccount.shell, businessBuild, "");
      expect(noAccount.calls).toEqual([]);
      const same = shellAt("en");
      await commitShellLanguage(same.shell, businessBuild, "en");
      expect(same.calls).toEqual([]);
    }
  });

  test("the document language follows the shown language; Business spells Spanish es", () => {
    expect(documentLanguage(undefined, true, true)).toBe("es");
    expect(documentLanguage("en", true, true)).toBe("en");
    expect(documentLanguage("es-419", true, true)).toBe("es");
    expect(documentLanguage(undefined, false, true)).toBe("en");
    expect(documentLanguage("es-419", false, true)).toBe("es-419");
    expect(documentLanguage("en", false, true)).toBe("en");
  });

  test("i18n reads the default and the order from one owner, and the auth page saves a chosen language on the account at sign-in", () => {
    const i18n = readFileSync(join(root, "lib/i18n.ts"), "utf-8");
    expect(i18n).toContain("fallbackLng: (code?: string) => fallbackChain(code, DEFAULT_LANGUAGE)");
    expect(i18n).toContain("order: [...LANGUAGE_DETECTION_ORDER]");
    expect(i18n).toContain("caches: [...LANGUAGE_DETECTION_CACHES]");
    expect(i18n).not.toContain("lng:");
    expect(i18n).not.toContain("fallbackLng: 'en'");
    expect(i18n).not.toContain("caches: ['localStorage']");
    const page = readFileSync(join(root, "app/page.tsx"), "utf-8");
    // The footer link shows the other language by its own name and switches at once.
    expect(page).toContain('data-testid="auth-language-switch"');
    expect(page).toContain("onClick={() => void chooseLanguage(language.code)}");
    expect(page).toContain("await i18n.changeLanguage(code);");
    // After a successful login the choice is saved on the account, before leaving the page.
    const login = page.slice(page.indexOf("await loginWithEmail({"), page.indexOf("router.replace(postAuthPath());", page.indexOf("await loginWithEmail({")));
    expect(login).toContain("saveProfileLanguage(i18n, chosenLanguage");
    // Signup already sends the shown language with the account.
    expect(page).toContain("language: normalizeApiLanguage(i18n.resolvedLanguage ?? i18n.language)");
    expect(page).toContain("landingLanguageChoices(shownLanguage)");
  });

  test("the landing page offers the other language on both builds", () => {
    expect(landingLanguageChoices("es-419", ALL_LANGUAGES).map((language) => language.name)).toEqual(["English"]);
    expect(landingLanguageChoices("en", ALL_LANGUAGES).map((language) => language.name)).toEqual(["Español"]);
  });
});

describe("what a reader sees for a key the shown language lacks", () => {
  test("an English reader never falls back to Spanish; a Spanish reader falls back to English; nothing shown yet starts from the default", () => {
    expect(fallbackChain("en", "es-419")).toEqual(["en"]);
    expect(fallbackChain("en-US", "es-419")).toEqual(["en"]);
    expect(fallbackChain("es-419", "es-419")).toEqual(["es-419", "en"]);
    expect(fallbackChain("es", "en")).toEqual(["es-419", "en"]);
    expect(fallbackChain(undefined, "es-419")).toEqual(["es-419", "en"]);
    expect(fallbackChain(undefined, "en")).toEqual(["en"]);
  });

  test("both locale files carry the same keys, so no reader meets the other language by accident", () => {
    const flat = (node: unknown, prefix = ""): string[] =>
      node && typeof node === "object"
        ? Object.entries(node as Record<string, unknown>).flatMap(([key, value]) => flat(value, prefix ? `${prefix}.${key}` : key))
        : [prefix];
    const en = new Set(flat(english));
    const es = new Set(flat(spanish));
    expect([...en].filter((key) => !es.has(key))).toEqual([]);
    expect([...es].filter((key) => !en.has(key))).toEqual([]);
  });
});
