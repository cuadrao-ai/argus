import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";

// The reset password page over a fake auth port that already holds a recovery session.
const calls: string[] = [];
const realAuth = await import("@/lib/auth-security");
mock.module("@/lib/auth-security", () => ({
  ...realAuth,
  getAuthSecurityActions: () => ({
    hasRecoverySession: async () => true,
    exchangeRecoveryCode: async () => undefined,
    resetRecoveredPassword: async (password: string) => {
      calls.push(password);
      return { currentSessionPreserved: false, freshLoginRequired: true, revocation: "complete", cookieSync: "cleared" };
    },
    signOutAllSessions: async () => ({ currentSessionPreserved: false, freshLoginRequired: true, revocation: "complete", cookieSync: "cleared" }),
  }),
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/auth/recovery" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(() => {
  document.body.innerHTML = "";
  calls.length = 0;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function mount() {
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { default: RecoveryPage } = await import("@/app/auth/recovery/page");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><RecoveryPage /></I18nextProvider>));
  for (let i = 0; i < 40 && !host.querySelector("form"); i += 1) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
  }
  const input = host.querySelector<HTMLInputElement>("form input") as HTMLInputElement;
  const type = (value: string) => act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  const submit = () => act(async () => { host.querySelector<HTMLButtonElement>('button[type="submit"]')?.click(); });
  return { host, input, type, submit, close: () => act(async () => root.unmount()) };
}

describe("reset password", () => {
  test("one new password field, coached, with no retype field", async () => {
    const page = await mount();
    try {
      assert.equal(page.host.querySelectorAll("form input").length, 1);
      assert.equal(page.input.autocomplete, "new-password");
      assert.equal(page.input.getAttribute("passwordrules"), "minlength: 8;");
      assert.equal(page.host.querySelector('[data-testid="password-coach"]'), null);
      await act(async () => page.input.focus());
      assert.ok(page.host.querySelector('[data-testid="password-coach"]'));
      assert.ok(page.host.querySelector('button[aria-label="Mostrar contraseña"]'), "the shared eye");
    } finally {
      await page.close();
    }
  });

  test("a short password is stopped inline; a long one is sent once", async () => {
    const page = await mount();
    try {
      await page.type("corta");
      await page.submit();
      assert.equal(page.host.querySelector('[data-testid="form-error-summary"]'), null);
      assert.equal(page.input.getAttribute("aria-invalid"), "true");
      assert.deepEqual(calls, []);
      const password = `frase larga ${Date.now().toString(36)}`;
      await page.type(password);
      await page.submit();
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
      assert.deepEqual(calls, [password]);
    } finally {
      await page.close();
    }
  });
});
