import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
import { leaveSession, resetLeavingSession } from "@/lib/logout-flow";

const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
let listener: (event: string, session: { user: { id: string } } | null) => void = () => {};
let session: { user: { id: string }; access_token: string } | null = null;
function emit(event: string, id: string | null) {
  session = id ? { user: { id }, access_token: `${id}-token` } : null;
  listener(event, session);
}
mock.module("@/lib/supabase-client", () => ({
  getSupabaseClient: () => ({
    auth: {
      onAuthStateChange: (next: typeof listener) => {
        listener = next;
        return { data: { subscription: { unsubscribe: () => {} } } };
      },
      getSession: async () => ({ data: { session }, error: null }),
      getUser: async () => ({ data: { user: session?.user ?? null }, error: null }),
    },
  }),
}));
mock.module("@/components/business-app/BusinessWorkspace", () => ({
  BusinessWorkspaceProvider: ({ children }: { children: ReactNode }) => children,
}));
mock.module("@/components/business-app/BusinessNamingProvider", () => ({ default: ({ children }: { children: ReactNode }) => children }));
mock.module("@/components/chat/ChatInterface", () => ({
  default: () => <input aria-label="Business draft" defaultValue="" />,
}));
mock.module("@/components/chat/ConversationShellGuard", () => ({ default: () => null }));
mock.module("@/components/business-app/ConversationUnavailableNotice", () => ({ default: () => null }));

beforeAll(() => {
  resetLeavingSession();
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  globalThis.fetch = async (url) => {
    const path = new URL(String(url)).pathname;
    assert.ok(path.endsWith("/spaces"), `Unexpected request ${path}`);
    return Response.json({ spaces: [] });
  };
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

let restoreConsent = () => {};
let consentAsked = () => {};
let firstConsent: unknown;
let currentConsent = (): unknown => undefined;

afterAll(() => {
  globalThis.fetch = originalFetch;
  restoreConsent();
  assert.equal(currentConsent(), firstConsent, "the consent method is restored after sign-out tests");
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  resetLeavingSession();
  GlobalRegistrator.unregister();
});

async function mount() {
  session = null;
  const { act } = await import("react");
  const { createElement } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { default: BusinessApp } = await import("@/components/business-app/BusinessApp");
  const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
  const { consent } = liveBusinessDataSource;
  if (firstConsent === undefined) {
    firstConsent = consent;
    restoreConsent = () => Object.assign(liveBusinessDataSource, { consent });
  }
  currentConsent = () => liveBusinessDataSource.consent;
  Object.assign(liveBusinessDataSource, {
    consent: async (version: string) => {
      consentAsked();
      return { version, accepted_at: "2026-10-18T12:00:00.000Z" };
    },
  });
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: "es-419",
    resources: { "es-419": { translation: spanish } },
    interpolation: { escapeValue: false },
  });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(createElement(I18nextProvider, { i18n }, createElement(BusinessApp)));
  });
  return { act, host, title: () => host.querySelector('[data-testid="session-recovery-screen"] h1')?.textContent, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

/** The consent gate hashes its copy off the main thread, which `act` cannot see, so wait for its check. */
async function signIn(page: Awaited<ReturnType<typeof mount>>, id: string) {
  const asked = new Promise<void>((resolve) => {
    consentAsked = resolve;
  });
  await page.act(async () => emit("SIGNED_IN", id));
  await page.act(() => asked);
}

test("an unexpected sign-out offers login without saying the account changed", async () => {
  const page = await mount();
  try {
    await signIn(page, "owner");
    await page.act(async () => emit("SIGNED_OUT", null));
    assert.equal(page.title(), "Inicia sesión para continuar");
    assert.ok(page.host.querySelector('a[href="/?auth=login"]'));
    assert.equal(page.host.querySelector("input"), null);
  } finally { await page.close(); }
});

test("a different signed-in account waits on the account-change screen", async () => {
  const page = await mount();
  try {
    await signIn(page, "owner");
    await page.act(async () => emit("SIGNED_IN", "other"));
    assert.equal(page.title(), "Cambió la cuenta activa");
    assert.equal(page.host.querySelector("input"), null);
  } finally { await page.close(); }
});

test("signing out of Business skips the account-changed alert and opens login", async () => {
  const page = await mount();
  try {
    await signIn(page, "owner");
    const landed: string[] = [];
    await page.act(async () => {
      await leaveSession({
        boundary: { beginConversion() {}, finishConversion() {} },
        currentUserId: "owner",
        signOut: async () => {
          emit("SIGNED_OUT", null);
          return { revocation: "complete", cookieSync: "cleared" };
        },
        clearLocalState() {},
        navigate: (href) => landed.push(href),
        onFailed() { landed.push("failed"); },
        businessBuild: true,
      });
    });
    assert.equal(page.title(), undefined);
    assert.deepEqual(landed, ["/?auth=login"]);
  } finally { await page.close(); }
});
