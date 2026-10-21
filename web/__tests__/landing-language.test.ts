import { describe, expect, test } from "bun:test";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import english from "../public/locales/en/common.json";
import spanish from "../public/locales/es-419/common.json";
import { ALL_LANGUAGES, accountLanguage, commitShellLanguage, defaultLanguage, documentLanguage, fallbackChain, landingLanguageChoices, resolveLanguage } from "../lib/language-features";

const root = join(import.meta.dir, "..");

describe("the one precedence that picks the shown language", () => {
  test("Spanish is the default on a Business build that ships it; English elsewhere", () => {
    expect(defaultLanguage(true, true)).toBe("es-419");
    expect(defaultLanguage(true, false)).toBe("en");
    expect(defaultLanguage(false, true)).toBe("en");
    expect(defaultLanguage(false, false)).toBe("en");
    expect(resolveLanguage({}, true, true)).toBe("es-419");
    expect(resolveLanguage({}, false, true)).toBe("en");
  });

  test("the account wins over the device choice and the browser, on both builds", () => {
    for (const businessBuild of [true, false]) {
      expect(resolveLanguage({ account: "en", device: "es-419", browser: "es-MX" }, businessBuild, true)).toBe("en");
      expect(resolveLanguage({ account: "es-419", device: "en", browser: "en-US" }, businessBuild, true)).toBe("es-419");
    }
  });

  test("on Business an account language counts only once the person saved one; a consumer account's always counts", () => {
    const unchosen = { language: "en", onboarding: { language_confirmed: false } };
    const chosen = { language: "en", onboarding: { language_confirmed: true } };
    expect(accountLanguage(unchosen, true)).toBeNull();
    expect(accountLanguage(chosen, true)).toBe("en");
    expect(accountLanguage({ language: "en" }, true)).toBeNull();
    expect(accountLanguage(unchosen, false)).toBe("en");
    expect(accountLanguage(null, true)).toBeNull();
    expect(resolveLanguage({ account: accountLanguage(unchosen, true), browser: "en-US" }, true, true)).toBe("es-419");
    expect(resolveLanguage({ account: accountLanguage(chosen, true), device: "es-419" }, true, true)).toBe("en");
  });

  test("before sign-in the device choice wins, whatever the browser says", () => {
    for (const businessBuild of [true, false]) {
      expect(resolveLanguage({ device: "en", browser: "es-MX" }, businessBuild, true)).toBe("en");
      expect(resolveLanguage({ device: "es-419", browser: "en-US" }, businessBuild, true)).toBe("es-419");
    }
  });

  test("an English browser stays Spanish on Business; only a consumer build lets the browser decide", () => {
    expect(resolveLanguage({ browser: "en-US" }, true, true)).toBe("es-419");
    expect(resolveLanguage({ browser: "en-US" }, false, true)).toBe("en");
    expect(resolveLanguage({ browser: "es-MX" }, false, true)).toBe("es-419");
    expect(resolveLanguage({ browser: "fr-FR" }, false, true)).toBe("en");
  });

  test("a consumer browser that lists Spanish after an unsupported language still gets Spanish", async () => {
    const { GlobalRegistrator } = await import("@happy-dom/global-registrator");
    GlobalRegistrator.register({ url: "http://localhost/" });
    try {
      Object.defineProperty(window.navigator, "language", { configurable: true, value: "fr-FR" });
      Object.defineProperty(window.navigator, "languages", { configurable: true, value: ["fr-FR", "es-ES"] });
      const { browserLanguageSources } = await import("../lib/language-features");
      expect(resolveLanguage(browserLanguageSources(), false, true)).toBe("es-419");
      expect(resolveLanguage(browserLanguageSources(), true, true)).toBe("es-419");
      Object.defineProperty(window.navigator, "languages", { configurable: true, value: ["fr-FR", "de-DE"] });
      expect(resolveLanguage(browserLanguageSources(), false, true)).toBe("en");
    } finally {
      await GlobalRegistrator.unregister();
    }
  });

  test("the shell moves to what the account resolves to and otherwise keeps what it shows", async () => {
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
      await commitShellLanguage(toEnglish.shell, businessBuild, "en", true);
      expect(toEnglish.calls).toEqual(["en"]);
      const toSpanish = shellAt("en");
      await commitShellLanguage(toSpanish.shell, businessBuild, "es-419", true);
      expect(toSpanish.calls).toEqual(["es-419"]);
      const noAccount = shellAt("es-419");
      await commitShellLanguage(noAccount.shell, businessBuild, null, true);
      await commitShellLanguage(noAccount.shell, businessBuild, undefined, true);
      await commitShellLanguage(noAccount.shell, businessBuild, "", true);
      expect(noAccount.calls).toEqual([]);
      const same = shellAt("en");
      await commitShellLanguage(same.shell, businessBuild, "en", true);
      expect(same.calls).toEqual([]);
    }
  });

  test("the document spells the resolved language; Business spells Spanish es", () => {
    expect(documentLanguage("es-419", true)).toBe("es");
    expect(documentLanguage("en", true)).toBe("en");
    expect(documentLanguage("es-419", false)).toBe("es-419");
    expect(documentLanguage("en", false)).toBe("en");
  });

  test("every reader goes through resolveLanguage and nothing else reads the device key", () => {
    for (const reader of ["lib/i18n.ts", "app/layout.tsx", "components/I18nProvider.tsx"]) {
      expect(readFileSync(join(root, reader), "utf-8")).toContain("resolveLanguage(");
    }
    const readers = sourceFiles(["app", "components", "lib"]).filter((file) => readFileSync(file, "utf-8").includes("LANGUAGE_STORAGE_KEY"));
    expect(readers.map((file) => file.slice(root.length + 1)).sort()).toEqual(["lib/browser-storage.ts", "lib/language-features.ts"]);
    const chosenReaders = sourceFiles(["app", "components", "lib"]).filter((file) => /language_confirmed/.test(readFileSync(file, "utf-8")));
    expect(chosenReaders.map((file) => file.slice(root.length + 1)).sort()).toEqual(["lib/guest-account.ts", "lib/language-features.ts"]);
    const accountReaders = sourceFiles(["app", "components", "lib"]).filter((file) => /accountLanguage\(/.test(readFileSync(file, "utf-8")));
    expect(accountReaders.map((file) => file.slice(root.length + 1)).sort()).toEqual(["lib/argus-api.ts", "lib/language-features.ts"]);
  });

  test("the auth page switches at once and saves the chosen language on the account at sign-in", () => {
    const page = readFileSync(join(root, "app/page.tsx"), "utf-8");
    expect(page).toContain('data-testid="auth-language-switch"');
    expect(page).toContain("onClick={() => void chooseLanguage(language.code)}");
    expect(page).toContain("await i18n.changeLanguage(code);");
    const login = page.slice(page.indexOf("await loginWithEmail({"), page.indexOf("router.replace(postAuthPath());", page.indexOf("await loginWithEmail({")));
    expect(login).toContain("saveProfileLanguage(i18n, chosenLanguage");
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

function sourceFiles(dirs: string[]): string[] {
  const files: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const path = join(dir, entry);
      if (statSync(path).isDirectory()) walk(path);
      else if (/\.(ts|tsx)$/.test(entry)) files.push(path);
    }
  };
  for (const dir of dirs) walk(join(root, dir));
  return files;
}
