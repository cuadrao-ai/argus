import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import english from "../public/locales/en/common.json";
import spanish from "../public/locales/es-419/common.json";
import { accountLanguageToApply, commitShellLanguage, defaultLanguage, documentLanguage, fallbackChain, languageDetectionCaches, languageDetectionOrder, languageToShow } from "../lib/language-features";

const root = join(import.meta.dir, "..");

describe("the language a visitor sees first", () => {
  test("Spanish is the default on a Business build that ships it; English elsewhere", () => {
    expect(defaultLanguage(true, true)).toBe("es-419");
    expect(defaultLanguage(true, false)).toBe("en");
    expect(defaultLanguage(false, true)).toBe("en");
    expect(defaultLanguage(false, false)).toBe("en");
  });

  test("a Business build reads no stored language and writes none; a consumer build still does", () => {
    expect(languageDetectionOrder(true)).toEqual([]);
    expect(languageDetectionCaches(true)).toEqual([]);
    expect(languageDetectionOrder(false)).toEqual(["localStorage", "navigator"]);
    expect(languageDetectionCaches(false)).toEqual(["localStorage"]);
  });

  test("a Business shell never switches to English", async () => {
    const calls: string[] = [];
    const shell = {
      language: "en",
      changeLanguage: async (next: string) => {
        calls.push(next);
        shell.language = next;
      },
    };
    await commitShellLanguage(shell, true, "en", true);
    await commitShellLanguage(shell, true, "en", true);
    expect(calls).toEqual(["es-419"]);
    expect(accountLanguageToApply(true, "en", true)).toBe("es-419");
    expect(languageToShow(true, "en", true)).toBe("es-419");
    expect(documentLanguage("en", true, true)).toBe("es");
    expect(documentLanguage(undefined, true, true)).toBe("es");
    const consumer: string[] = [];
    await commitShellLanguage(
      { language: "es-419", changeLanguage: async (next: string) => { consumer.push(next); } },
      false,
      "en",
      true,
    );
    expect(consumer).toEqual(["en"]);
    expect(languageToShow(false, "en", true)).toBe("en");
    expect(documentLanguage("es-419", false, true)).toBe("es-419");
  });

  test("i18n reads the default and the order from one owner, and the auth page saves a chosen language on the account at sign-in", () => {
    const i18n = readFileSync(join(root, "lib/i18n.ts"), "utf-8");
    expect(i18n).toContain("fallbackLng: (code?: string) => fallbackChain(code, DEFAULT_LANGUAGE)");
    expect(i18n).toContain("order: [...LANGUAGE_DETECTION_ORDER]");
    expect(i18n).toContain("caches: [...languageDetectionCaches(businessPilotEnabled)]");
    expect(i18n).toContain("lng: DEFAULT_LANGUAGE === 'es-419' ? DEFAULT_LANGUAGE : undefined");
    expect(i18n).not.toContain("fallbackLng: 'en'");
    expect(i18n).not.toContain("caches: ['localStorage']");
    const page = readFileSync(join(root, "app/page.tsx"), "utf-8");
    // The footer link shows the other language by its own name and switches at once.
    expect(page).toContain('data-testid="auth-language-switch"');
    expect(page).toContain("onClick={() => void chooseLanguage(language.code)}");
    expect(page).toContain("await i18n.changeLanguage(shown);");
    // After a successful login the choice is saved on the account, before leaving the page.
    const login = page.slice(page.indexOf("await loginWithEmail({"), page.indexOf("router.replace(postAuthPath());", page.indexOf("await loginWithEmail({")));
    expect(login).toContain("saveProfileLanguage(i18n, chosenLanguage");
    // Signup already sends the shown language with the account.
    expect(page).toContain("language: normalizeApiLanguage(i18n.resolvedLanguage ?? i18n.language)");
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
