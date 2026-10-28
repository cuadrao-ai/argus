import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";

// Exercise the real reset component through its injected auth boundary.
const calls: string[] = [];
const complete = { currentSessionPreserved: false, freshLoginRequired: true, revocation: "complete", cookieSync: "cleared" } as const;
let ready = true;
let resetResult: typeof complete | { currentSessionPreserved: "unknown"; freshLoginRequired: false; revocation: "failed"; cookieSync: "not_required"; revocationAuthority?: "absent" | "unknown" | "present" } = complete;
let retryResult: typeof resetResult = complete;
let retryCalls = 0;
const acceptedProofs: string[] = [];

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/auth/recovery" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(() => {
  document.body.innerHTML = "";
  calls.length = 0;
  ready = true;
  resetResult = complete;
  retryResult = complete;
  retryCalls = 0;
  acceptedProofs.length = 0;
  window.history.replaceState(null, "", "/auth/recovery");
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function mount(language: "es-419" | "en" = "es-419") {
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const english = (await import("@/public/locales/en/common.json")).default;
  const { RecoveryReset } = await import("@/components/auth/RecoveryReset");
  const { getAuthSecurityActions } = await import("@/lib/auth-security");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { "es-419": { translation: spanish }, en: { translation: english } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const actions = (() => ({
    hasRecoverySession: async () => ready,
    exchangeRecoveryCode: async () => undefined,
    acceptRecoveryProof: async (proof: string) => { acceptedProofs.push(proof); if (!ready) throw new Error("fixture"); },
    resetRecoveredPassword: async (password: string) => { calls.push(password); return resetResult; },
    signOutAllSessions: async () => { retryCalls += 1; return retryResult; },
    retryCookieCleanup: async () => "cleared",
  })) as unknown as typeof getAuthSecurityActions;
  await act(async () => root.render(<I18nextProvider i18n={i18n}><RecoveryReset actions={actions} /></I18nextProvider>));
  for (let i = 0; i < 40 && !host.querySelector("form") && !host.querySelector('[role="alert"]'); i += 1) {
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
  test("an initially absent recovery session never claims the password changed", async () => {
    ready = false;
    const page = await mount();
    try {
      assert.equal(page.host.querySelector("form"), null);
      assert.ok(page.host.textContent?.includes("Este enlace de recuperación falta, venció o ya fue usado."));
      assert.ok(!page.host.textContent?.includes("Tu contraseña fue actualizada."));
      assert.deepEqual(calls, []);
      const reference = page.host.querySelector<HTMLElement>('[data-testid="error-reference"]');
      assert.match(reference?.textContent ?? "", /Ref\. [A-Za-z0-9_-]{4,}/, "the invalid state shows a reference");
      assert.equal(page.host.querySelector('a[href="/auth/forgot-password"]')?.textContent, "Solicitar un enlace nuevo");
    } finally { await page.close(); }
  });

  test("a proof handed over by the confirm route opens the form and leaves the address", async () => {
    const proof = `person-1:${"a".repeat(64)}`;
    window.history.replaceState(null, "", `/auth/recovery#recovery_proof=${proof}`);
    const page = await mount();
    try {
      assert.deepEqual(acceptedProofs, [proof]);
      assert.ok(page.host.querySelector("form input"), "the password form shows");
      assert.equal(window.location.hash, "");
      assert.equal(window.location.pathname, "/auth/recovery");
    } finally { await page.close(); }
  });

  test("a handed-over proof the session does not match stays on the invalid state", async () => {
    ready = false;
    window.history.replaceState(null, "", `/auth/recovery#recovery_proof=person-2:${"b".repeat(64)}`);
    const page = await mount();
    try {
      assert.equal(acceptedProofs.length, 1);
      assert.equal(page.host.querySelector("form"), null);
      assert.ok(page.host.textContent?.includes("Vamos a buscar un nuevo enlace"));
      assert.equal(window.location.hash, "");
    } finally { await page.close(); }
  });

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

  test("confirmed missing authority shows the approved Spanish sign-in fallback", async () => {
    resetResult = { currentSessionPreserved: "unknown", freshLoginRequired: false, revocation: "failed", cookieSync: "not_required", revocationAuthority: "absent" };
    const page = await mount();
    try {
      await page.type("frase nueva segura");
      await page.submit();
      assert.ok(page.host.textContent?.includes("Tu contraseña fue actualizada."));
      assert.ok(page.host.textContent?.includes("No pudimos confirmar que todas las sesiones se cerraron. Inicia sesión de nuevo y abre Seguridad de la cuenta para cerrarlas."));
      assert.equal(page.host.querySelectorAll('a[href="/?auth=login"]').length, 1);
      assert.equal(page.host.querySelectorAll("button.auth-primary").length, 0);
      assert.equal(retryCalls, 0);
    } finally { await page.close(); }
  });

  test("confirmed missing authority uses the exact approved English copy", async () => {
    resetResult = { currentSessionPreserved: "unknown", freshLoginRequired: false, revocation: "failed", cookieSync: "not_required", revocationAuthority: "absent" };
    const page = await mount("en");
    try {
      await page.type("secure new phrase");
      await page.submit();
      assert.ok(page.host.textContent?.includes("Your password is updated."));
      assert.ok(page.host.textContent?.includes("We couldn’t confirm that every session was signed out. Sign in again and open Account security to sign them out."));
      assert.ok(page.host.querySelector('a[href="/?auth=login"]'));
    } finally { await page.close(); }
  });

  test("unknown authority keeps the existing retry, which can complete", async () => {
    resetResult = { currentSessionPreserved: "unknown", freshLoginRequired: false, revocation: "failed", cookieSync: "not_required", revocationAuthority: "unknown" };
    const page = await mount();
    try {
      await page.type("frase nueva segura");
      await page.submit();
      assert.ok(page.host.textContent?.includes("Tu contraseña fue actualizada."));
      assert.ok(page.host.textContent?.includes("Vuelve a intentarlo antes de iniciar sesión de nuevo."));
      assert.equal(page.host.querySelectorAll('a[href="/?auth=login"]').length, 0);
      const retry = page.host.querySelector<HTMLButtonElement>("button.auth-primary");
      assert.ok(retry);
      await act(async () => retry.click());
      assert.equal(retryCalls, 1);
      assert.ok(page.host.textContent?.includes("Tu contraseña fue actualizada. Inicia sesión de nuevo en cada navegador."));
      assert.ok(page.host.querySelector('a[href="/?auth=login"]'));
    } finally { await page.close(); }
  });
});
