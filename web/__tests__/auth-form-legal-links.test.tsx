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

  test("with nothing set, the acceptance sentence links the published Cuadrao pages", async () => {
    clearLegalEnv();
    const html = await renderAuthForm("signup");
    expect(html).toContain('href="https://cuadrao.ai/terminos"');
    expect(html).toContain('href="https://cuadrao.ai/privacidad"');
    expect(html).toContain("Al registrarte, aceptas nuestros");
    expect(html).not.toContain('href="/terms"');
    expect(html).not.toContain('href="/privacy"');
  });

  test("blank values fall back to the published pages, and data deletion stays unset", () => {
    process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL = "   ";
    process.env.NEXT_PUBLIC_CUADRAO_DATA_DELETION_URL = " ";
    expect(cuadraoLegalLinks()).toEqual({
      terms: "https://cuadrao.ai/terminos",
      privacy: "https://cuadrao.ai/privacidad",
      dataDeletion: undefined,
    });
  });

  test("a setting overrides its published page, one document at a time", async () => {
    process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL = "https://cuadrao.example/privacidad";
    expect(acceptanceLinks()).toEqual({
      terms: "https://cuadrao.ai/terminos",
      privacy: "https://cuadrao.example/privacidad",
    });
    process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL = "https://cuadrao.example/terminos";
    process.env.NEXT_PUBLIC_CUADRAO_DATA_DELETION_URL = "https://cuadrao.example/borrar";
    expect(cuadraoLegalLinks().dataDeletion).toBe("https://cuadrao.example/borrar");
    const html = await renderAuthForm("signup");
    expect(html).toContain('href="https://cuadrao.example/terminos"');
    expect(html).toContain('href="https://cuadrao.example/privacidad"');
    expect(html).not.toContain("cuadrao.ai/");
  });
});
