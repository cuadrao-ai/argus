import { afterEach, describe, expect, test } from "bun:test";
import i18next from "i18next";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";

import AuthForm, { type AuthFormMode } from "../components/auth/AuthForm";
import { acceptanceLinks, cuadraoLegalLinks } from "../lib/cuadrao-legal-links";
import es419 from "../public/locales/es-419/common.json";

const ENV_NAMES = [
  "NEXT_PUBLIC_CUADRAO_TERMS_URL",
  "NEXT_PUBLIC_CUADRAO_PRIVACY_URL",
  "NEXT_PUBLIC_CUADRAO_DATA_DELETION_URL",
] as const;

function clearLegalEnv() {
  for (const name of ENV_NAMES) delete process.env[name];
}

async function renderAuthForm(mode: AuthFormMode) {
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: "es-419",
    fallbackLng: false,
    interpolation: { escapeValue: false },
    resources: { "es-419": { translation: es419 } },
  });
  return renderToStaticMarkup(
    createElement(
      I18nextProvider,
      { i18n },
      createElement(AuthForm, {
        mode,
        onModeChange: () => undefined,
        onSubmit: async () => undefined,
      }),
    ),
  );
}

describe("auth form legal links", () => {
  afterEach(clearLegalEnv);

  test("no link and no dangling acceptance line while the Cuadrao URLs are unpublished", async () => {
    clearLegalEnv();
    for (const mode of ["login", "signup"] as const) {
      const html = await renderAuthForm(mode);
      expect(html).not.toContain('href="/terms"');
      expect(html).not.toContain('href="/privacy"');
      expect(html).not.toContain("aceptas nuestros");
    }
  });

  test("blank values count as unpublished", () => {
    process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL = "   ";
    expect(cuadraoLegalLinks()).toEqual({
      terms: undefined,
      privacy: undefined,
      dataDeletion: undefined,
    });
  });

  test("published URLs render as the only legal links", async () => {
    process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL = "https://cuadrao.example/terminos";
    process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL = "https://cuadrao.example/privacidad";
    const html = await renderAuthForm("signup");
    expect(html).toContain('href="https://cuadrao.example/terminos"');
    expect(html).toContain('href="https://cuadrao.example/privacidad"');
    expect(html).toContain("Al registrarte, aceptas nuestros");
    expect(html).not.toContain('href="/terms"');
    expect(html).not.toContain('href="/privacy"');
  });

  test("one published URL renders no acceptance sentence at all", async () => {
    process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL = "https://cuadrao.example/privacidad";
    for (const mode of ["login", "signup"] as const) {
      const html = await renderAuthForm(mode);
      expect(html).not.toContain("cuadrao.example");
      expect(html).not.toContain("aceptas nuestros");
      expect(html).not.toContain('href="/terms"');
      expect(html).not.toContain('href="/privacy"');
    }
    delete process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL;
    process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL = "https://cuadrao.example/terminos";
    const html = await renderAuthForm("login");
    expect(html).not.toContain("cuadrao.example");
    expect(html).not.toContain("aceptas nuestros");
  });

  test("acceptanceLinks is null unless both URLs are published", () => {
    expect(acceptanceLinks()).toBeNull();
    process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL = "https://cuadrao.example/terminos";
    expect(acceptanceLinks()).toBeNull();
    process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL = "https://cuadrao.example/privacidad";
    expect(acceptanceLinks()).toEqual({
      terms: "https://cuadrao.example/terminos",
      privacy: "https://cuadrao.example/privacidad",
    });
  });
});
