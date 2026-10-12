import { describe, expect, test } from "bun:test";
import i18next from "i18next";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";

import AlphaLegalPage from "../components/legal/AlphaLegalPage";
import {
  STORAGE_REGISTRY,
  type StorageConcept,
} from "../lib/browser-storage";
import en from "../public/locales/en/common.json";
import es419 from "../public/locales/es-419/common.json";

const SUPPORT_EMAIL = "support@get-argus.com";

const CATALOGS = { en, "es-419": es419 } as const;
type Locale = keyof typeof CATALOGS;

const REPO_ROOT = join(import.meta.dir, "..", "..");

/**
 * The disclosure is derived from two registries, not from searching source for
 * call sites. Each registry is the single door its side of the app writes
 * through, so this asserts a declaration rather than the result of a scan.
 *
 * Enforcement that the doors are the only doors lives elsewhere, because a
 * test cannot prove it by pattern matching:
 *  - ESLint bans localStorage/sessionStorage/document.cookie outside
 *    lib/browser-storage.ts
 *  - argus.api.browser_cookies raises on an unregistered cookie name
 *  - runtime observation watches what is genuinely written
 *    (e2e/browser-storage-disclosure.spec.ts and
 *    tests/test_browser_cookie_disclosure.py)
 */

// The phrase each concept must actually say to the reader, per locale. A
// concept mapped to a label proves nothing unless the label is in the copy.
const STORAGE_CONCEPT_PHRASES: Record<StorageConcept, Record<Locale, string>> = {
  language: { en: "language", "es-419": "idioma" },
  appearance: { en: "appearance", "es-419": "apariencia" },
  layout: { en: "layout", "es-419": "diseño" },
  tips: { en: "tips you dismissed", "es-419": "avisos que descartaste" },
  temporary: {
    en: "conversations you marked temporary",
    "es-419": "conversaciones que marcaste como temporales",
  },
  campaign: {
    en: "the ad or link that brought you here",
    "es-419": "el anuncio o enlace que te trajo aquí",
  },
};

/**
 * Read COOKIE_REGISTRY out of the backend chokepoint. This parses one named
 * declaration in one known file and fails loudly if that declaration is gone,
 * which is a different thing from searching the tree for call sites: there is
 * nothing here to evade, only a declaration to keep honest.
 */
function backendCookieRegistry(): Record<string, string> {
  const source = readFileSync(
    join(REPO_ROOT, "src", "argus", "api", "browser_cookies.py"),
    "utf-8",
  );
  const block = source.match(
    /COOKIE_REGISTRY:\s*Final\[dict\[str,\s*str\]\]\s*=\s*\{([\s\S]*?)\n\}/,
  );
  if (!block) {
    throw new Error(
      "COOKIE_REGISTRY not found in src/argus/api/browser_cookies.py. The " +
        "cookie disclosure is derived from it, so this test cannot run.",
    );
  }
  const registry: Record<string, string> = {};
  for (const entry of block[1].matchAll(/"([^"]+)"\s*:\s*"([^"]+)"/g)) {
    registry[entry[1]] = entry[2];
  }
  return registry;
}

async function renderLegal(
  locale: Locale,
  kind: "terms" | "privacy",
): Promise<string> {
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: locale,
    fallbackLng: false,
    interpolation: { escapeValue: false },
    resources: { [locale]: { translation: CATALOGS[locale] } },
  });

  const element: ReactElement = createElement(AlphaLegalPage, {
    kind,
    supportEmail: SUPPORT_EMAIL,
  });

  return renderToStaticMarkup(
    createElement(I18nextProvider, { i18n }, element),
  );
}

function legalStrings(catalog: (typeof CATALOGS)[Locale]): string[] {
  const collected: string[] = [];
  const walk = (node: unknown): void => {
    if (typeof node === "string") {
      collected.push(node);
      return;
    }
    if (node && typeof node === "object") {
      Object.values(node as Record<string, unknown>).forEach(walk);
    }
  };
  walk(catalog.legal);
  return collected;
}

describe("disclosure derives from the chokepoint registries", () => {
  test("every registered cookie maps to a section item that exists", () => {
    const registry = backendCookieRegistry();
    expect(Object.keys(registry).length).toBeGreaterThan(0);

    for (const locale of Object.keys(CATALOGS) as Locale[]) {
      const items = CATALOGS[locale].legal.privacy.sections.cookies.items as
        Record<string, unknown>;
      for (const [cookie, item] of Object.entries(registry)) {
        expect(
          items,
          `${locale}: cookie "${cookie}" maps to item "${item}", which the privacy copy does not have`,
        ).toHaveProperty(item);
      }
    }
  });

  test("every registered storage key maps to a concept the copy says out loud", async () => {
    const concepts = new Set<StorageConcept>(Object.values(STORAGE_REGISTRY));
    expect(concepts.size).toBe(Object.keys(STORAGE_CONCEPT_PHRASES).length);

    for (const locale of Object.keys(CATALOGS) as Locale[]) {
      const preferences =
        CATALOGS[locale].legal.privacy.sections.cookies.items.preferences.body;
      const rendered = await renderLegal(locale, "privacy");

      for (const concept of concepts) {
        const phrase = STORAGE_CONCEPT_PHRASES[concept][locale];
        expect(
          preferences,
          `${locale}: preferences copy never mentions "${concept}" ("${phrase}")`,
        ).toContain(phrase);
        expect(rendered, `${locale}: "${phrase}" is not rendered`).toContain(
          phrase,
        );
      }
    }
  });

  test("no registered key or cookie is left without a disclosure concept", () => {
    for (const [key, concept] of Object.entries(STORAGE_REGISTRY)) {
      expect(
        STORAGE_CONCEPT_PHRASES[concept as StorageConcept],
        `storage key "${key}" maps to unknown concept "${concept}"`,
      ).toBeDefined();
    }
    const items = en.legal.privacy.sections.cookies.items as Record<
      string,
      unknown
    >;
    for (const [cookie, item] of Object.entries(backendCookieRegistry())) {
      expect(items, `cookie "${cookie}" has no item "${item}"`).toHaveProperty(
        item,
      );
    }
  });
});

describe("legal page cookie and storage disclosure", () => {
  test("names every storage category Argus actually writes to the browser", async () => {
    const markup = await renderLegal("en", "privacy");

    expect(markup).toContain("Cookies and browser storage");
    expect(markup).toContain("Sign-in cookies");
    expect(markup).toContain("Guest handoff cookies");
    expect(markup).toContain("Security cookies");
    expect(markup).toContain("Preferences you set");
    expect(markup).toContain("Supabase authentication");
    expect(markup).toContain("Cloudflare Turnstile");
    expect(markup).toContain("local storage");
  });

  test("describes the handoff cookies at their real path scope", async () => {
    // path=/api/v1/auth reaches every auth route, not only sign-in:
    // /auth/login, /auth/logout, /auth/session, /auth/signup, /auth/guest,
    // /auth/guest/signup.
    expect(await renderLegal("en", "privacy")).toContain(
      "limited to Argus authentication routes",
    );
    expect(await renderLegal("es-419", "privacy")).toContain(
      "se limitan a las rutas de autenticación de Argus",
    );
    for (const locale of Object.keys(CATALOGS) as Locale[]) {
      const body =
        CATALOGS[locale].legal.privacy.sections.cookies.items.guest_handoff.body;
      expect(body, locale).not.toContain("sign-in routes");
      expect(body, locale).not.toContain("rutas de inicio de sesión");
    }
  });

  test("states the no-tracking position that keeps the consent banner unnecessary", async () => {
    const markup = await renderLegal("en", "privacy");

    expect(markup).toContain("does not show a cookie consent banner");
    expect(markup).toContain("does not use advertising cookies");
    expect(markup).toContain("cross-site tracking");
    expect(markup).toContain(
      "run on Argus servers and store nothing in your browser",
    );
  });

  test("ships the disclosure in both supported locales", async () => {
    const spanish = await renderLegal("es-419", "privacy");

    expect(spanish).toContain("Cookies y almacenamiento del navegador");
    expect(spanish).toContain("Cookies de inicio de sesión");
    expect(spanish).toContain("Cookies de traspaso de invitado");
    expect(spanish).toContain("Cookies de seguridad");
    expect(spanish).toContain("Preferencias que tú eliges");
    expect(spanish).toContain("no muestra un aviso de consentimiento de cookies");
  });

  test("keeps the cookie section keys parallel across locales", () => {
    for (const catalog of Object.values(CATALOGS)) {
      const cookies = catalog.legal.privacy.sections.cookies;
      expect(Object.keys(cookies).sort()).toEqual([
        "body",
        "body_after",
        "items",
        "title",
      ]);
      expect(Object.keys(cookies.items).sort()).toEqual([
        "guest_handoff",
        "preferences",
        "security",
        "sign_in",
      ]);
    }
  });

  test("does not claim sign-in cookies expire with the browser session", async () => {
    // @supabase/ssr defaults to a 400-day maxAge, so a session-only claim is
    // false. This pins the correction rather than the wording around it.
    for (const locale of Object.keys(CATALOGS) as Locale[]) {
      const signIn =
        CATALOGS[locale].legal.privacy.sections.cookies.items.sign_in.body;
      expect(signIn.toLowerCase(), locale).not.toContain("for your session");
      expect(signIn.toLowerCase(), locale).not.toContain("lo que dura tu sesión");
    }
    expect(await renderLegal("en", "privacy")).toContain(
      "They stay after you close the browser",
    );
  });

  test("does not claim campaign attribution stays only on the device", async () => {
    const enBody = en.legal.privacy.sections.cookies.items.preferences.body;
    const esBody =
      es419.legal.privacy.sections.cookies.items.preferences.body;
    expect(enBody).not.toContain("This stays on your device");
    expect(esBody).not.toContain("Todo eso queda en tu dispositivo");
    expect(enBody).toContain("start as a guest or create an account");
    expect(esBody).toContain("empiezas como invitado o creas una cuenta");
    expect(await renderLegal("en", "privacy")).toContain(
      "Argus may receive it when you start as a guest or create an account",
    );
  });
});

describe("legal page early-access wording", () => {
  test("drops private-alpha jargon from every user-facing legal string", () => {
    for (const [locale, catalog] of Object.entries(CATALOGS)) {
      for (const value of legalStrings(catalog)) {
        expect(value.toLowerCase(), `${locale}: ${value}`).not.toContain(
          "private alpha",
        );
        expect(value.toLowerCase(), `${locale}: ${value}`).not.toContain(
          "alfa privada",
        );
      }
    }
  });

  test("keeps the pre-release disclaimer that the wording change must not lose", async () => {
    const markup = await renderLegal("en", "terms");

    expect(markup).toContain("Early access availability and changes");
    expect(markup).toContain("provided as is, without warranties");
    expect(markup).toContain("may never reach a full release");
  });

  test("holds the founder-locked no-em-dash rule", () => {
    for (const [locale, catalog] of Object.entries(CATALOGS)) {
      for (const value of legalStrings(catalog)) {
        expect(value, `${locale}: ${value}`).not.toContain("—");
      }
    }
  });
});

describe("legal page navigation", () => {
  test("offers a back-to-Cuadrao affordance at the top as well as the footer", async () => {
    for (const kind of ["terms", "privacy"] as const) {
      const markup = await renderLegal("en", kind);
      const header = markup.slice(0, markup.indexOf("<h1"));

      expect(header).toContain('aria-label="Back to Cuadrao"');
      expect(header).toContain('href="/"');
      expect(markup.split('href="/"').length - 1).toBeGreaterThanOrEqual(2);
    }
  });

  test("cross-links the sibling legal page", async () => {
    expect(await renderLegal("en", "privacy")).toContain('href="/terms"');
    expect(await renderLegal("en", "terms")).toContain('href="/privacy"');
  });
});
