import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, type ReactNode } from "react";
import { RecoveryRequestError } from "@/lib/auth-security";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/auth/forgot-password" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount(child: ReactNode, language = "es-419") {
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const es = (await import("@/public/locales/es-419/common.json")).default;
  const en = (await import("@/public/locales/en/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { "es-419": { translation: es }, en: { translation: en } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}>{child}</I18nextProvider>));
  return {
    host,
    type: async (value: string) => act(async () => {
      const input = host.querySelector("input")!;
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }),
    submit: async () => act(async () => { host.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); }),
    close: async () => { await act(async () => root.unmount()); host.remove(); },
  };
}

for (const language of ["es-419", "en"]) {
  test(`email validates on blur, clears live, and keeps its label in ${language}`, async () => {
    const { RecoveryRequest } = await import("@/components/auth/RecoveryRequest");
    let calls = 0;
    const page = await mount(<RecoveryRequest request={async () => { calls++; }} />, language);
    try {
      const input = page.host.querySelector("input")!;
      await page.type("broken");
      assert.equal(input.getAttribute("aria-invalid"), null);
      await act(async () => { input.focus(); input.blur(); });
      assert.equal(input.getAttribute("aria-invalid"), "true");
      await page.type("design@example.test");
      assert.equal(input.getAttribute("aria-invalid"), null);
      assert.ok(page.host.querySelector('label[for="recovery-email"]'));
      assert.ok(input.placeholder);
      await page.submit();
      assert.equal(calls, 1);
      assert.ok(page.host.textContent?.includes("design@example.test"));
      assert.equal(page.host.querySelector("form"), null);
      assert.ok(page.host.querySelector('button[disabled]'));
      assert.equal(document.activeElement?.tagName, "H1");
      assert.equal(page.host.querySelector('[role="status"]')?.textContent,
        language === "es-419"
          ? "Si hay una cuenta habilitada con este correo, recibirás un enlace para restablecer tu contraseña."
          : "If an eligible account uses this email, you’ll receive a link to reset your password.",
        "accepted delivery is announced without announcing the countdown");
    } finally { await page.close(); }
  });
}

test("duplicate requests are blocked and errors retain the email", async () => {
  const { RecoveryRequest } = await import("@/components/auth/RecoveryRequest");
  let reject!: (error: Error) => void;
  let calls = 0;
  const response = new Promise<void>((_, fail) => { reject = fail; });
  const page = await mount(<RecoveryRequest request={() => { calls++; return response; }} />);
  try {
    await page.type("design@example.test");
    await page.submit(); await page.submit();
    assert.equal(calls, 1);
    await act(async () => reject(new RecoveryRequestError(400, 0)));
    assert.equal(page.host.querySelector("input")?.value, "design@example.test");
    assert.ok(page.host.querySelector('[role="alert"]'));
    assert.equal(page.host.querySelector('button[type="submit"]')?.hasAttribute("disabled"), false);
  } finally { await page.close(); }
});

test("rate limiting respects the service wait", async () => {
  const { RecoveryRequest } = await import("@/components/auth/RecoveryRequest");
  const page = await mount(<RecoveryRequest request={async () => { throw new RecoveryRequestError(429, 91); }} />);
  try {
    await page.type("design@example.test"); await page.submit();
    assert.ok(page.host.textContent?.includes("91s"));
    assert.equal(page.host.querySelector('[role="status"]')?.textContent?.includes("91s"), false, "countdown must not announce each second");
    assert.ok(page.host.querySelector('button[type="submit"]')?.hasAttribute("disabled"));
  } finally { await page.close(); }
});

test("only the eye reveals the password and a failed reset retains the value", async () => {
  const { RecoveryReset } = await import("@/components/auth/RecoveryReset");
  const complete = { currentSessionPreserved: false, freshLoginRequired: true, revocation: "complete", cookieSync: "cleared" } as const;
  const page = await mount(<RecoveryReset actions={() => ({ hasRecoverySession: async () => true, exchangeRecoveryCode: async () => {}, resetRecoveredPassword: async () => { throw new Error("fixture"); }, changePassword: async () => complete, signOutThisBrowser: async () => complete, signOutOtherSessions: async () => complete, signOutAllSessions: async () => complete })} />);
  try {
    await page.type("Synthetic phrase 2026");
    const input = page.host.querySelector("input")!;
    await act(async () => input.click());
    assert.equal(input.type, "password");
    await act(async () => page.host.querySelector<HTMLButtonElement>('button[aria-controls="recovery-password"]')!.click());
    assert.equal(input.type, "text");
    assert.ok(page.host.querySelector('.lucide-eye-closed'));
    await act(async () => page.host.querySelector<HTMLButtonElement>('button[aria-controls="recovery-password"]')!.click());
    assert.equal(input.type, "password");
    await page.submit();
    assert.equal(input.value, "Synthetic phrase 2026");
    assert.ok(page.host.querySelector('[role="alert"]'));
    await page.type("A revised synthetic phrase 2026");
    assert.equal(page.host.querySelector('[role="alert"]'), null, "editing clears stale save failure");
  } finally { await page.close(); }
});


test("expired links offer a new link without exposing a password form", async () => {
  const { RecoveryReset } = await import("@/components/auth/RecoveryReset");
  const complete = { currentSessionPreserved: false, freshLoginRequired: true, revocation: "complete", cookieSync: "cleared" } as const;
  const page = await mount(<RecoveryReset actions={() => ({ hasRecoverySession: async () => false, exchangeRecoveryCode: async () => {}, resetRecoveredPassword: async () => complete, changePassword: async () => complete, signOutThisBrowser: async () => complete, signOutOtherSessions: async () => complete, signOutAllSessions: async () => complete })} />);
  try {
    assert.equal(page.host.querySelector("form"), null);
    assert.ok(page.host.querySelector('a[href="/auth/forgot-password"]'));
    assert.ok(page.host.querySelector('[role="alert"]'));
  } finally { await page.close(); }
});
