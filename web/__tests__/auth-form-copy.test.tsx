import { describe, expect, test } from "bun:test";
import i18next from "i18next";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";

import AuthForm, { type AuthFormMode } from "../components/auth/AuthForm";
import en from "../public/locales/en/common.json";
import es419 from "../public/locales/es-419/common.json";

async function renderAuthForm(mode: AuthFormMode, language: "en" | "es-419", brand?: "argus" | "cuadrao") {
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: language,
    fallbackLng: false,
    interpolation: { escapeValue: false },
    resources: {
      en: { translation: en },
      "es-419": { translation: es419 },
    },
  });

  return renderToStaticMarkup(
    createElement(
      I18nextProvider,
      { i18n },
      createElement(AuthForm, {
        mode,
        brand,
        onModeChange: () => undefined,
        onSubmit: async () => undefined,
      }),
    ),
  );
}

describe("auth form copy", () => {
  test("Cuadrao is the brand on every entry, Business or not", async () => {
    for (const language of ["en", "es-419"] as const) {
      const business = await renderAuthForm("login", language, "cuadrao");
      const shared = await renderAuthForm("login", language);
      assert.equal(business.includes("Cuadrao?"), true);
      assert.equal(business.includes("Argus"), false);
      assert.equal(shared.includes("Cuadrao?"), true);
      assert.equal(shared.includes("Argus"), false);
      assert.equal(shared.includes('data-auth-brand="cuadrao"'), true);
    }
  });
  test("signup associates the password requirement with the password input", async () => {
    const signup = await renderAuthForm("signup", "en");
    const login = await renderAuthForm("login", "en");

    expect(signup).toContain(
      'aria-describedby="auth-signup-password-requirement"',
    );
    expect(signup).toContain(
      '<p id="auth-signup-password-requirement"',
    );
    expect(login).not.toContain("auth-signup-password-requirement");
  });

  test("English signup explains the password rule and auth actions use sentence case", async () => {
    const signup = await renderAuthForm("signup", "en");
    const login = await renderAuthForm("login", "en");

    expect(signup).toContain("At least 8 characters.");
    expect(signup).toContain("Already have an account?");
    expect(signup).toContain(">Sign in</button>");
    expect(login).toContain("New to Cuadrao?");
    expect(login).toContain(">Sign in</button>");
    expect(login).not.toContain("At least 8 characters.");
  });

  test("Spanish signup explains the password rule and auth actions use sentence case", async () => {
    const signup = await renderAuthForm("signup", "es-419");
    const login = await renderAuthForm("login", "es-419");

    expect(signup).toContain("Mínimo 8 caracteres.");
    expect(signup).toContain("¿Ya tienes una cuenta?");
    expect(signup).toContain(">Iniciar sesión</button>");
    expect(login).toContain("¿Nuevo en Cuadrao?");
    expect(login).toContain(">Iniciar sesión</button>");
    expect(login).not.toContain("Mínimo 8 caracteres.");
  });
});
