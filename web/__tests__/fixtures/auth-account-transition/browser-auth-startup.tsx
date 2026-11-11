import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";

type Session = { user: { id: string } } | null;
type Listener = (event: string, session: Session) => void;
const scenario = process.env.CUADRAO_TEST_AUTH_STARTUP ?? "missing";
const signedIn = { user: { id: "synthetic-startup-owner" } };
let storedSession: Session = scenario === "signed-in-then-sign-out" ? signedIn : null;
let readError: Error | null = scenario === "startup-blip" ? new Error("Synthetic failed startup read") : null;
let reads = 0;
const listeners = new Set<Listener>();
const events: string[] = [];

mock.module("@supabase/ssr", () => ({ createBrowserClient: () => ({ auth: {
  onAuthStateChange: (listener: Listener) => {
    listeners.add(listener);
    queueMicrotask(() => {
      if (!listeners.has(listener)) return;
      events.push("INITIAL_SESSION");
      listener("INITIAL_SESSION", storedSession);
    });
    return { data: { subscription: { unsubscribe: () => listeners.delete(listener) } } };
  },
  getSession: async () => {
    reads += 1;
    return { data: { session: storedSession }, error: readError };
  },
} }) }));
mock.module("@/lib/business-api", () => ({ getBusinessDirectory: async () => ({ spaces: [], closed_spaces: [] }) }));
mock.module("@/components/business-app/BusinessConsentGate", () => ({ default: ({ children }: { children: ReactNode }) => children }));
mock.module("@/components/business-app/BusinessWorkspace", () => ({ BusinessWorkspaceProvider: ({ children }: { children: ReactNode }) => children }));
mock.module("@/components/business-app/BusinessNamingProvider", () => ({ default: ({ children }: { children: ReactNode }) => children }));
mock.module("@/components/chat/ChatInterface", () => ({ default: () => <input aria-label="Private workspace draft" /> }));
mock.module("@/components/chat/ConversationShellGuard", () => ({ default: () => null }));
mock.module("@/components/business-app/ConversationUnavailableNotice", () => ({ default: () => null }));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  localStorage.clear();
  sessionStorage.clear();
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  process.env.NEXT_PUBLIC_SUPABASE_URL = "http://localhost";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "synthetic";
});
afterAll(() => GlobalRegistrator.unregister());

test(`real browser client and Business boundary settle ${scenario} without a stuck startup screen`, async () => {
  const { default: BusinessApp } = await import("@/components/business-app/BusinessApp");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const login = () => host.querySelector<HTMLAnchorElement>('a[href="/?auth=login"]');
  const assertLogin = () => {
    assert.equal(host.querySelector("h1")?.textContent, "Inicia sesión para continuar");
    assert.equal(login()?.textContent, "Iniciar sesión");
    assert.equal(login()?.closest("[hidden]"), null, "the login action is not hidden by the startup boundary");
    assert.equal(host.querySelector('[data-testid="fullscreen-loading"]'), null);
    assert.equal(host.querySelector("input"), null, "private workspace content is absent");
  };
  try {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessApp /></I18nextProvider>));
    assert.equal(reads, 1, "startup reads the stored session without waiting for another auth event");
    assert.ok(events.length > 0 && events.every(event => event === "INITIAL_SESSION"), "startup receives no later auth event");

    if (scenario === "startup-blip") {
      assert.equal(host.querySelector("h1")?.textContent, "No pudimos comprobar tu sesión");
      assert.equal(login(), null, "an initial null event with a failed read does not offer login");
      readError = null;
      storedSession = signedIn;
      await act(async () => host.querySelector<HTMLButtonElement>("button")!.click());
      assert.equal(reads, 2);
      assert.ok(host.querySelector("input"), "retry recovers the signed-in workspace without another auth event");
      assert.equal(login(), null);
    } else {
      if (scenario === "signed-in-then-sign-out") {
        assert.ok(host.querySelector("input"), "a stored session opens the workspace at startup");
        assert.equal(login(), null);
        await act(async () => {
          storedSession = null;
          events.push("SIGNED_OUT");
          for (const listener of listeners) listener("SIGNED_OUT", null);
        });
      }
      assertLogin();
      await act(async () => { await new Promise(resolve => setTimeout(resolve, 320)); });
      assertLogin();
      assert.equal(reads, 1, "no focus event, retry, or polling is needed to reach login");
    }
    assert.deepEqual(events.filter(event => event !== "INITIAL_SESSION"), scenario === "signed-in-then-sign-out" ? ["SIGNED_OUT"] : []);
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
