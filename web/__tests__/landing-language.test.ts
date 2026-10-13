import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { defaultLanguage, languageDetectionOrder } from "../lib/language-features";

const root = join(import.meta.dir, "..");

describe("the language a visitor sees first", () => {
  test("Spanish is the default on a Business build that ships it; English elsewhere", () => {
    expect(defaultLanguage(true, true)).toBe("es-419");
    expect(defaultLanguage(true, false)).toBe("en");
    expect(defaultLanguage(false, true)).toBe("en");
    expect(defaultLanguage(false, false)).toBe("en");
  });

  test("on a Business build the browser's language never decides; a choice saved on the device does", () => {
    expect(languageDetectionOrder(true)).toEqual(["localStorage"]);
    expect(languageDetectionOrder(false)).toEqual(["localStorage", "navigator"]);
  });

  test("i18n reads the default and the order from one owner, and the auth page saves a chosen language on the account at sign-in", () => {
    const i18n = readFileSync(join(root, "lib/i18n.ts"), "utf-8");
    expect(i18n).toContain("fallbackLng: DEFAULT_LANGUAGE");
    expect(i18n).toContain("order: [...LANGUAGE_DETECTION_ORDER]");
    expect(i18n).not.toContain("fallbackLng: 'en'");
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
  });
});
