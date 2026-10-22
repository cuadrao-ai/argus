import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
import { leaveSession, resetLeavingSession } from "@/lib/logout-flow";

const originalFetch = globalThis.fetch;
let listener: (event: string, session: { user: { id: string } } | null) => void = () => {};
mock.module("@/lib/supabase-client", () => ({
  getSupabaseClient: () => ({
    auth: {
      onAuthStateChange: (next: typeof listener) => {
        listener = next;
        return { data: { subscription: { unsubscribe: () => {} } } };
      },
      getSession: async () => ({ data: { session: null }, error: null }),
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

afterAll(() => {
  globalThis.fetch = originalFetch;
  restoreConsent();
  resetLeavingSession();
  GlobalRegistrator.unregister();
});

async function mount() {
  const { act } = await import("react");
  const { createElement } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { default: BusinessApp } = await import("@/components/business-app/BusinessApp");
  const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
  const { consent } = liveBusinessDataSource;
  restoreConsent = () => Object.assign(liveBusinessDataSource, { consent });
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
  return { act, host, root };
}

/** The consent gate hashes its copy off the main thread, which `act` cannot see, so wait for its check. */
async function signIn(page: Awaited<ReturnType<typeof mount>>, id: string) {
  const asked = new Promise<void>((resolve) => {
    consentAsked = resolve;
  });
  await page.act(async () => listener("SIGNED_IN", { user: { id } }));
  await page.act(() => asked);
}

test("an unexpected sign-out still shows the account-changed alert", async () => {
  const page = await mount();
  await signIn(page, "owner");
  await page.act(async () => listener("SIGNED_OUT", null));
  assert.match(page.host.querySelector("[role=alert]")?.textContent ?? "", /Tu cuenta cambió/);
  await page.act(async () => page.root.unmount());
});

test("a different signed-in account does not show the account-changed alert", async () => {
  const page = await mount();
  await signIn(page, "owner");
  await signIn(page, "other");
  assert.equal(page.host.querySelector("[role=alert]"), null);
  assert.notEqual(page.host.querySelector("input"), null);
  await page.act(async () => page.root.unmount());
});

test("signing out of Business skips the account-changed alert and opens login", async () => {
  const page = await mount();
  await signIn(page, "owner");
  const landed: string[] = [];
  await page.act(async () => {
    await leaveSession({
      boundary: { beginConversion() {}, finishConversion() {} },
      currentUserId: "owner",
      signOut: async () => {
        listener("SIGNED_OUT", null);
        return { revocation: "complete", cookieSync: "cleared" };
      },
      clearLocalState() {},
      navigate: (href) => landed.push(href),
      onFailed() {
        landed.push("failed");
      },
      businessBuild: true,
    });
  });
  assert.equal(page.host.querySelector("[role=alert]"), null);
  assert.deepEqual(landed, ["/?auth=login"]);
  await page.act(async () => page.root.unmount());
});
