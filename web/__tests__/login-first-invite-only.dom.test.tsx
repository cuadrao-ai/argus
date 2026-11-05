import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import type { ReactNode } from "react";
import type { Root } from "react-dom/client";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

import es419 from "../public/locales/es-419/common.json";

mock.module("next/navigation", () => ({
  useRouter: () => ({ push: () => undefined, replace: () => undefined, refresh: () => undefined }),
  useSearchParams: () => new URLSearchParams(),
}));

const INVITE_ONLY_SENTENCE = "Cuadrao está en acceso anticipado, solo por invitación.";
const REQUEST_ACCESS = "Solicitar acceso";
const CONTACT_PAGE = "https://cuadrao.ai/contacto";
const SIGN_UP = "Registrarse";
const TRY_AGAIN = "Inténtalo de nuevo";

type AccessAnswer = { access_mode: string } | "unavailable";

const mounted = new Map<Root, HTMLElement>();
let restoreFetch: (() => void) | null = null;

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
  restoreFetch?.();
  restoreFetch = null;
});

function answerFetches(access: AccessAnswer) {
  const originalFetch = globalThis.fetch;
  restoreFetch = () => { globalThis.fetch = originalFetch; };
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const path = new URL(String(input)).pathname;
    if (path.endsWith("/auth/access-mode")) {
      return access === "unavailable"
        ? Response.json({ code: "internal_error" }, { status: 500 })
        : Response.json(access);
    }
    return Response.json({ code: "profile_unavailable" }, { status: 503 });
  }) as typeof fetch;
}

async function i18nSpanish() {
  const i18next = (await import("i18next")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: es419 } } });
  return i18n;
}

async function mount(element: (i18n: Awaited<ReturnType<typeof i18nSpanish>>) => ReactNode, settled: (host: HTMLElement) => boolean) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18n = await i18nSpanish();
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  mounted.set(root, host);
  await act(async () => { root.render(element(i18n)); });
  await act(async () => {
    if (settled(host)) return;
    await new Promise<void>((resolve, reject) => {
      const observer = new MutationObserver(() => {
        if (!settled(host)) return;
        observer.disconnect(); clearTimeout(timeout); resolve();
      });
      const timeout = setTimeout(() => { observer.disconnect(); reject(new Error("The screen did not settle")); }, 1000);
      observer.observe(host, { childList: true, subtree: true });
    });
  });
  return { act, host };
}

async function mountFrontDoor(query: string, access: AccessAnswer) {
  window.history.replaceState(null, "", `/${query}`);
  answerFetches(access);
  const { I18nextProvider } = await import("react-i18next");
  const { default: LandingPage } = await import("@/app/page");
  return mount(
    (i18n) => <I18nextProvider i18n={i18n}><LandingPage /></I18nextProvider>,
    (host) => Boolean(host.querySelector("[data-auth-brand]")),
  );
}

const heading = (host: HTMLElement) => host.querySelector("[data-auth-entry-content] h2")?.textContent ?? "";
const buttons = (host: HTMLElement) => [...host.querySelectorAll("button")].map((button) => button.textContent ?? "");
const notice = (host: HTMLElement) => host.querySelector('[data-testid="invite-only-notice"]');

describe("the front door while access is by invitation", () => {
  test("a bare visit opens on login with the sentence and Solicitar acceso, and no sign-up link", async () => {
    const { host } = await mountFrontDoor("", { access_mode: "invite_only" });
    assert.equal(heading(host), es419.auth.login.title);
    assert.ok(!buttons(host).includes(SIGN_UP), "no sign-up link on the login screen");
    const shown = notice(host);
    assert.ok(shown, "the invite-only sentence is under the form");
    assert.equal(shown.textContent, `${INVITE_ONLY_SENTENCE} ${REQUEST_ACCESS}`);
    const link = shown.querySelector("a");
    assert.equal(link?.getAttribute("href"), CONTACT_PAGE);
    assert.equal(link?.getAttribute("target"), null, "opens in the same tab");
  });

  test("the invitation link still opens account creation", async () => {
    const { host } = await mountFrontDoor("?auth=signup", { access_mode: "invite_only" });
    assert.equal(heading(host), es419.auth.signup.title);
    assert.equal(notice(host), null);
  });

  test("a failed read shows login and claims neither mode", async () => {
    const { host } = await mountFrontDoor("", "unavailable");
    assert.equal(heading(host), es419.auth.login.title);
    assert.ok(!buttons(host).includes(SIGN_UP));
    assert.equal(notice(host), null);
  });
});

describe("the front door while access is open", () => {
  test("a bare visit opens as today, on the request screen", async () => {
    const { host } = await mountFrontDoor("", { access_mode: "open" });
    assert.ok(host.querySelector('[data-testid="landing-request-access"]'));
    assert.equal(notice(host), null);
  });

  test("login keeps its sign-up link and shows no invite-only sentence", async () => {
    const { host } = await mountFrontDoor("?auth=login", { access_mode: "open" });
    assert.equal(heading(host), es419.auth.login.title);
    assert.ok(buttons(host).includes(SIGN_UP));
    assert.equal(notice(host), null);
  });
});

async function fill(act: typeof import("react").act, input: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function refusedSignup(accountAccess: "open" | "invite_only") {
  const { I18nextProvider } = await import("react-i18next");
  const { default: AuthForm } = await import("@/components/auth/AuthForm");
  const refusal = Object.assign(new Error("Signup failed. Please try again."), { code: "auth_signup_failed" });
  const { act, host } = await mount(
    (i18n) => (
      <I18nextProvider i18n={i18n}>
        <AuthForm mode="signup" accountAccess={accountAccess} onModeChange={() => undefined} onSubmit={async () => { throw refusal; }} />
      </I18nextProvider>
    ),
    (host) => Boolean(host.querySelector("form")),
  );
  await fill(act, host.querySelector('input[type="email"]') as HTMLInputElement, "nobody@example.test");
  await fill(act, host.querySelector('input[autocomplete="new-password"]') as HTMLInputElement, "long enough password 47");
  await act(async () => { host.querySelector("form")?.requestSubmit(); });
  const alert = host.querySelector('[role="alert"]');
  assert.ok(alert, "the refusal is announced");
  return alert;
}

describe("a refused direct sign-up", () => {
  test("while access is by invitation it says so and offers Solicitar acceso, never try again", async () => {
    const alert = await refusedSignup("invite_only");
    assert.equal(alert.textContent, `${INVITE_ONLY_SENTENCE} ${REQUEST_ACCESS}`);
    assert.ok(!alert.textContent!.includes(TRY_AGAIN));
    assert.equal(alert.querySelector("a")?.getAttribute("href"), CONTACT_PAGE);
  });

  test("while access is open it keeps today's message", async () => {
    const alert = await refusedSignup("open");
    assert.equal(alert.textContent, es419.auth.errors.auth_signup_failed);
    assert.ok(alert.textContent!.includes(TRY_AGAIN));
  });
});
