import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, test } from "bun:test";
import type { Root } from "react-dom/client";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

import { contactPageHref } from "../components/auth/InviteOnlyNotice";
import en from "../public/locales/en/common.json";
import es419 from "../public/locales/es-419/common.json";

const TRY_AGAIN = "Inténtalo de nuevo";

const mounted = new Map<Root, HTMLElement>();

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});
afterEach(async () => {
  const { act } = await import("react");
  await act(async () => { for (const [root, host] of mounted) { root.unmount(); host.remove(); } });
  mounted.clear();
});

async function fill(act: typeof import("react").act, input: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function refusedSignup(language: "es-419" | "en", code: string) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const { default: AuthForm } = await import("@/components/auth/AuthForm");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { "es-419": { translation: es419 }, en: { translation: en } } });
  const refusal = Object.assign(new Error("raw backend detail"), { code });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  mounted.set(root, host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <AuthForm mode="signup" onModeChange={() => undefined} onSubmit={async () => { throw refusal; }} />
      </I18nextProvider>,
    );
  });
  await fill(act, host.querySelector('input[type="email"]') as HTMLInputElement, "nobody@example.test");
  await fill(act, host.querySelector('input[autocomplete="new-password"]') as HTMLInputElement, "long enough password 47");
  await act(async () => { host.querySelector("form")?.requestSubmit(); });
  const alert = host.querySelector('[role="alert"]');
  assert.ok(alert, "the refusal is announced");
  return { alert, host };
}

describe("a refused direct sign-up", () => {
  test("says access is by invitation and offers Solicitar acceso to the contact page, never try again", async () => {
    const { alert, host } = await refusedSignup("es-419", "auth_signup_failed");
    assert.equal(alert.textContent, `${es419.auth.invite_only.body} ${es419.auth.invite_only.request_access}`);
    assert.ok(!alert.textContent!.includes(TRY_AGAIN));
    const link = alert.querySelector("a");
    assert.equal(link?.getAttribute("href"), "https://cuadrao.ai/contacto");
    assert.equal(link?.getAttribute("target"), null, "opens in the same tab");
    assert.ok([...host.querySelectorAll("button")].some((button) => button.textContent === es419.landing.sign_in), "sign-in stays offered");
  });

  test("in English the link goes to the English contact page", async () => {
    const { alert } = await refusedSignup("en", "auth_signup_failed");
    assert.equal(alert.textContent, `${en.auth.invite_only.body} ${en.auth.invite_only.request_access}`);
    assert.equal(alert.querySelector("a")?.getAttribute("href"), "https://cuadrao.ai/en/contact");
  });

  test("another refusal keeps its own message", async () => {
    const { alert } = await refusedSignup("es-419", "too_many_requests");
    assert.equal(alert.textContent, es419.auth.errors.too_many_requests);
    assert.equal(alert.querySelector("a"), null);
  });
});

describe("the contact page per language", () => {
  test("Spanish and unknown languages go to /contacto, English to /en/contact", () => {
    assert.equal(contactPageHref("es-419"), "https://cuadrao.ai/contacto");
    assert.equal(contactPageHref(undefined), "https://cuadrao.ai/contacto");
    assert.equal(contactPageHref("en"), "https://cuadrao.ai/en/contact");
    assert.equal(contactPageHref("en-US"), "https://cuadrao.ai/en/contact");
  });
});
