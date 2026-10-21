import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import type { SessionActionResult } from "@/lib/auth-security";

// The account security page over a fake auth port: the page keeps the calls it
// makes today, and these tests watch what the person sees around them.
const calls: string[] = [];
let failing = new Set<string>();
const done: SessionActionResult = { currentSessionPreserved: true, freshLoginRequired: false, revocation: "complete", cookieSync: "cleared" };
const run = (name: string) => async (input?: unknown) => {
  calls.push(input ? `${name} ${JSON.stringify(input)}` : name);
  if (failing.has(name)) throw new Error("auth unavailable");
  return done;
};

const realAuth = await import("@/lib/auth-security");
mock.module("@/lib/auth-security", () => ({
  ...realAuth,
  getAuthSecurityActions: () => ({
    changePassword: run("changePassword"),
    signOutThisBrowser: run("signOutThisBrowser"),
    signOutOtherSessions: run("signOutOtherSessions"),
    signOutAllSessions: run("signOutAllSessions"),
  }),
}));
const realApi = await import("@/lib/argus-api");
mock.module("@/lib/argus-api", () => ({ ...realApi, getMe: async () => ({ id: "u-1" }) }));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/account/security" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(() => {
  document.body.innerHTML = "";
  calls.length = 0;
  failing = new Set();
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function mount() {
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { default: AccountSecurityPage } = await import("@/app/account/security/page");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><AccountSecurityPage /></I18nextProvider>));
  for (let i = 0; i < 40 && !host.querySelector("h1"); i += 1) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
  }
  const input = (id: string) => host.querySelector<HTMLInputElement>(`#${id}`) as HTMLInputElement;
  const type = (id: string, value: string) => act(async () => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(input(id), value);
    input(id).dispatchEvent(new Event("input", { bubbles: true }));
  });
  const leave = (id: string) => act(async () => { input(id).focus(); input(id).blur(); });
  const button = (name: string) => {
    const found = [...document.querySelectorAll<HTMLButtonElement>("button")].find((node) => (node.getAttribute("aria-label") ?? node.textContent?.trim()) === name);
    assert.ok(found, `a button named ${name}`);
    return found;
  };
  const press = (name: string) => act(async () => { button(name).click(); });
  const settle = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  return { host, input, type, leave, button, press, settle, close: () => act(async () => root.unmount()) };
}

const strong = () => `clave-${Math.random().toString(36).slice(2, 10)}`;

describe("account security", () => {
  test("two password fields with real labels and autocomplete, and the length rule shown before any error", async () => {
    const page = await mount();
    try {
      const fields = [...page.host.querySelectorAll<HTMLInputElement>("form input")];
      assert.deepEqual(fields.map((field) => [page.host.querySelector(`label[for="${field.id}"]`)?.textContent, field.autocomplete, field.type]), [
        ["Contraseña actual", "current-password", "password"],
        ["Contraseña nueva", "new-password", "password"],
      ], "no retype field: the eye and the password manager cover typos");
      assert.equal(page.input("new-password").getAttribute("passwordrules"), "minlength: 8;");
      assert.match(page.host.querySelector('[data-testid="password-coach"]')?.textContent ?? "", /Al menos 8 caracteres/);
      assert.equal(page.button("Cambiar contraseña").disabled, false, "the submit is there to press, it checks on press");
    } finally {
      await page.close();
    }
  });

  test("a short password turns red only after leaving it, and clears the moment it is long enough", async () => {
    const page = await mount();
    try {
      await page.type("new-password", "corta");
      assert.equal(page.input("new-password").getAttribute("aria-invalid"), null);
      await page.leave("new-password");
      assert.equal(page.host.querySelector("#new-password-note")?.textContent, "Usa al menos 8 caracteres.");
      await page.type("new-password", strong());
      assert.equal(page.host.querySelector("#new-password-note")?.textContent, "");
      assert.equal(page.input("new-password").getAttribute("aria-invalid"), null);
    } finally {
      await page.close();
    }
  });

  test("submitting with gaps lists every broken field and changes nothing", async () => {
    const page = await mount();
    try {
      await page.press("Cambiar contraseña");
      const summary = page.host.querySelector('[data-testid="form-error-summary"]');
      assert.ok(summary);
      assert.deepEqual([...summary.querySelectorAll("a")].map((link) => link.getAttribute("href")), ["#current-password", "#new-password"]);
      assert.deepEqual(calls, []);
    } finally {
      await page.close();
    }
  });

  test("a valid change sends the same call as before and empties the fields", async () => {
    const page = await mount();
    try {
      const current = strong();
      const next = strong();
      await page.type("current-password", current);
      await page.type("new-password", next);
      await page.press("Cambiar contraseña");
      await page.settle();
      assert.deepEqual(calls, [`changePassword ${JSON.stringify({ currentPassword: current, newPassword: next })}`]);
      assert.equal(page.input("new-password").value, "");
    } finally {
      await page.close();
    }
  });

  test("each session choice says what it does, and signing out everywhere is red and confirms first", async () => {
    const page = await mount();
    try {
      for (const [name, line] of [
        ["Cerrar sesión en este navegador", "Sales solo aquí. Tus otras sesiones siguen abiertas."],
        ["Cerrar otras sesiones", "Sales en tus otros navegadores y dispositivos. Tu sesión aquí sigue abierta."],
        ["Cerrar todas las sesiones", "Sales en todas partes, también aquí. Tendrás que iniciar sesión de nuevo."],
      ]) {
        const describedBy = page.button(name).getAttribute("aria-describedby");
        assert.equal(document.getElementById(describedBy ?? "")?.textContent, line);
      }
      assert.match(page.button("Cerrar todas las sesiones").className, /text-\[#9e2f39\]/);
      await page.press("Cerrar todas las sesiones");
      assert.deepEqual(calls, [], "nothing signs out before the confirm");
      const dialog = document.querySelector('[role="alertdialog"]');
      assert.ok(dialog);
      const confirm = dialog.querySelector<HTMLButtonElement>('[data-testid="confirm-dialog-confirm"]');
      assert.equal(confirm?.style.backgroundColor.replace(/\s/g, ""), "#9e2f39");

      failing = new Set(["signOutAllSessions"]);
      await page.press("Confirmar");
      await page.settle();
      assert.equal(document.querySelector('[data-testid="confirm-dialog-error"]')?.textContent, "No pudimos completar ese cambio de sesión. Inténtalo de nuevo.");
      assert.deepEqual(calls, ["signOutAllSessions"]);
    } finally {
      await page.close();
    }
  });

  test("a failed sign out says so inline, with Reintentar beside its text, and retries the same call", async () => {
    const page = await mount();
    try {
      failing = new Set(["signOutThisBrowser"]);
      await page.press("Cerrar sesión en este navegador");
      await page.settle();
      const alert = [...page.host.querySelectorAll('[role="alert"]')].find((node) => node.textContent?.includes("Reintentar"));
      assert.ok(alert);
      const text = alert.querySelector("p");
      const retry = alert.querySelector("button");
      assert.equal(text?.textContent, "No pudimos completar ese cambio de sesión. Inténtalo de nuevo.");
      assert.equal(retry?.parentElement, text?.parentElement, "the retry sits in the text's column");
      failing = new Set();
      await act(async () => retry?.click());
      await page.settle();
      assert.deepEqual(calls, ["signOutThisBrowser", "signOutThisBrowser"]);
    } finally {
      await page.close();
    }
  });
});

