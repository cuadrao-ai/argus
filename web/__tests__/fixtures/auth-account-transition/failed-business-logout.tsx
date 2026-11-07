import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { BusinessWorkspaceInfo } from "@/lib/business-api";
import type { ChatRequestSessionController } from "@/lib/chat-request-session";

const owner = { user: { id: "owner" }, access_token: "fixture-token" };
const ownGrant = "4b2a1f0e-9c3d-4e5f-8a7b-6c5d4e3f2a1b";
const clientGrant = "5b2a1f0e-9c3d-4e5f-8a7b-6c5d4e3f2a1b";
type AuthListener = (event: string, value: typeof owner | null) => void;
type LogoutOutcome = "same" | "rejected" | "left" | "cookie-failed" | "changed" | "unavailable";
type CheckFailure = { delivery: "return" | "throw"; emitsSignedOut: boolean };
let session: typeof owner | null;
let outcome: LogoutOutcome;
let checkFailure: CheckFailure | null;
const listeners = new Set<AuthListener>();
const searchParams = new URLSearchParams("");
const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;

function emitSignedOut() {
  session = null;
  listeners.forEach((listener) => listener("SIGNED_OUT", null));
}

mock.module("next/navigation", () => ({
  useSearchParams: () => searchParams,
  useRouter: () => ({ push() {}, replace() {} }),
  usePathname: () => "/biz",
}));
mock.module("@supabase/ssr", () => ({
  createBrowserClient: () => ({
    auth: {
      onAuthStateChange(next: AuthListener) {
        listeners.add(next);
        return { data: { subscription: { unsubscribe: () => { listeners.delete(next); } } } };
      },
      async getSession() {
        if (!checkFailure) return { data: { session }, error: null };
        if (checkFailure.emitsSignedOut && session) emitSignedOut();
        const error = new Error("Session unavailable");
        if (checkFailure.delivery === "throw") throw error;
        return { data: { session }, error };
      },
      getUser: async () => ({ data: { user: session?.user ?? null }, error: null }),
      async signOut() {
        if (outcome === "left" || outcome === "cookie-failed") {
          emitSignedOut();
          return { error: null };
        }
        if (outcome === "changed") {
          session = { user: { id: "other-owner" }, access_token: "other-fixture-token" };
          listeners.forEach((listener) => listener("SIGNED_IN", session));
        }
        if (outcome === "unavailable") checkFailure = { delivery: "return", emitsSignedOut: false };
        if (outcome === "rejected") throw new Error("Sign-out request rejected");
        return { error: new Error("Revocation failed") };
      },
    },
  }),
}));
mock.module("@/components/business-app/BusinessNamingProvider", () => ({ default: ({ children }: { children: ReactNode }) => children }));
mock.module("@/components/chat/ConversationShellGuard", () => ({ default: () => null }));
mock.module("@/components/business-app/ConversationUnavailableNotice", () => ({ default: () => null }));
let Probe: () => ReactNode;
mock.module("@/components/chat/ChatInterface", () => ({ default: () => <Probe /> }));

beforeAll(() => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  process.env.NEXT_PUBLIC_SUPABASE_URL = "http://localhost";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "synthetic";
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  globalThis.fetch = originalFetch;
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  await GlobalRegistrator.unregister();
});

async function mount(logoutOutcome: LogoutOutcome = "same") {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: i18next } = await import("i18next");
  const { I18nextProvider } = await import("react-i18next");
  const { default: spanish } = await import("@/public/locales/es-419/common.json");
  const { default: BusinessApp } = await import("@/components/business-app/BusinessApp");
  const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
  const { useBusiness } = await import("@/components/business-app/business-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { useChatAccountBoundary } = await import("@/components/chat/useChatAccountBoundary");
  const { getChosenGrant, synchronizeBusinessAccount } = await import("@/lib/business-grant");
  const { logoutFromApi } = await import("@/lib/argus-api");
  const { leaveSession, resetLeavingSession } = await import("@/lib/logout-flow");
  const fixture = createFixtureBusinessDataSource();
  const [listed, workspace, [receipt]] = await Promise.all([
    fixture.spaces(),
    fixture.workspace(),
    fixture.receipts("inbox"),
  ]);
  const spaces = listed.map((space) => ({
    ...space,
    grant_id: space.role === "owner" ? ownGrant : clientGrant,
    access_seen: true,
  }));
  assert.ok(receipt);
  const requests = { synchronizeAccountScope: () => true } as unknown as ChatRequestSessionController;
  const writes: { text: string; grant: string | null }[] = [];
  const uploads: { filename: string; grant: string | null }[] = [];
  const navigations: string[] = [];
  const unexpectedRequests: string[] = [];
  let api: BusinessContextValue;
  let boundary: ReturnType<typeof useChatAccountBoundary>;
  let logout!: () => Promise<"left" | "failed">;
  let nextRead: { response: Promise<BusinessWorkspaceInfo>; started: () => void } | null = null;
  let logoutErrors = 0;

  session = owner;
  outcome = logoutOutcome;
  checkFailure = null;
  resetLeavingSession();
  synchronizeBusinessAccount(null);
  globalThis.fetch = (async (url, init) => {
    const path = new URL(String(url)).pathname;
    if (path.endsWith("/auth/logout")) return Response.json({}, { status: outcome === "cookie-failed" ? 503 : 200 });
    if (path.endsWith("/business/spaces")) return Response.json({ spaces });
    if (path.endsWith("/business/captures") && init?.method === "POST") {
      const headers = new Headers(init.headers);
      const key = headers.get("Idempotency-Key");
      assert.ok(key && typeof init.body === "string");
      const { text } = JSON.parse(init.body);
      assert.equal(typeof text, "string");
      writes.push({ text, grant: headers.get("X-Business-Grant") });
      return Response.json(await fixture.captureNote({ text }, key));
    }
    if (path.endsWith("/profile")) return new Response(null, { status: 404 });
    unexpectedRequests.push(path);
    throw new Error(`Unexpected request ${path}`);
  }) as typeof fetch;

  const originalSource = { ...liveBusinessDataSource };
  const source: BusinessDataSource = {
    ...fixture,
    mode: "live",
    spaces: async () => spaces,
    spaceDirectory: async () => ({ spaces, closed_spaces: [] }),
    receiptReading: undefined,
    setReceiptReading: undefined,
    workspace: async () => {
      const deferred = nextRead;
      nextRead = null;
      if (!deferred) return workspace;
      deferred.started();
      return deferred.response;
    },
    captureNote: originalSource.captureNote,
    uploadReceipt: async (file) => {
      uploads.push({ filename: file.name, grant: getChosenGrant() });
      return { ...receipt, filename: file.name };
    },
  };
  Object.assign(liveBusinessDataSource, source);

  Probe = function BusinessProbe() {
    api = useBusiness();
    boundary = useChatAccountBoundary(api.userId ?? null, requests, () => {});
    logout = () => leaveSession({
      boundary,
      currentUserId: logoutOutcome === "same" ? null : api.userId ?? null,
      signOut: logoutFromApi,
      clearLocalState() {},
      navigate: (href) => navigations.push(href),
      onFailed: () => { logoutErrors += 1; },
      businessBuild: true,
    });
    return <p data-testid="workspace-probe">{api.records.workspace?.currency}</p>;
  };

  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const waitFor = async (condition: () => boolean, description: string) => {
    for (let i = 0; i < 80; i += 1) {
      if (condition()) return;
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); });
    }
    assert.fail(`Timed out waiting for ${description}: ${host.textContent?.slice(0, 180)}`);
  };
  const ready = () => waitFor(() => host.querySelector('[data-testid="workspace-probe"]')?.textContent === "DOP", "Business records");
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessApp /></I18nextProvider>));

  return {
    act, host, ready, waitFor, navigations, writes, uploads,
    api: () => api,
    boundary: () => boundary,
    chosenGrant: getChosenGrant,
    logoutErrors: () => logoutErrors,
    recoveryHeading: () => host.querySelector('[data-testid="session-recovery-screen"] h1')?.textContent,
    async selectClient() {
      await ready();
      await act(async () => api.chooseBusiness(clientGrant));
      await waitFor(() => api.records.workspaceGrant === clientGrant, "selected client's records");
    },
    async failFocusCheck(failure: CheckFailure) {
      checkFailure = failure;
      await act(async () => { window.dispatchEvent(new Event("focus")); });
    },
    async retryAsOwner() {
      const button = host.querySelector<HTMLButtonElement>('[data-testid="session-recovery-screen"] button');
      assert.ok(button);
      assert.equal(button.textContent, "Reintentar");
      session = owner;
      checkFailure = null;
      await act(async () => button.click());
      await ready();
    },
    signOutFromAnotherTab: () => act(async () => emitSignedOut()),
    async signOut() {
      let result: "left" | "failed" | undefined;
      await act(async () => { result = await logout(); });
      return result;
    },
    deferRead() {
      const started = Promise.withResolvers<void>();
      const response = Promise.withResolvers<BusinessWorkspaceInfo>();
      nextRead = { response: response.promise, started: started.resolve };
      return { started: started.promise, resolve: () => response.resolve(workspace) };
    },
    async close() {
      await act(async () => root.unmount());
      host.remove();
      Object.assign(liveBusinessDataSource, originalSource);
      globalThis.fetch = originalFetch;
      resetLeavingSession();
      assert.deepEqual(unexpectedRequests, []);
    },
  };
}

test.each(["same", "rejected"] as const)("failed sign-out (%s) restores new Business reads, notes and uploads while old callbacks stay blocked", async (outcome) => {
  const page = await mount(outcome);
  try {
    await page.selectClient();
    const oldSource = page.api().source;
    const oldBoundary = page.boundary();
    const reply = page.deferRead();
    const lateRead = assert.rejects(oldSource.workspace());
    await reply.started;

    assert.equal(await page.signOut(), "failed");
    assert.equal(page.logoutErrors(), 1);
    assert.deepEqual(page.navigations, []);
    reply.resolve();
    await lateRead;
    await assert.rejects(oldSource.captureNote({ text: "Old note" }, "old-note"));

    await page.ready();
    const current = page.api();
    assert.equal((await current.source.workspace()).currency, "DOP");
    assert.equal(oldBoundary.admission.current.signal.aborted, true);
    assert.equal(page.boundary().admission.current.signal.aborted, false);
    assert.equal(page.boundary().recovery.takeLogoutFailure(), true);
    assert.equal(page.boundary().recovery.takeLogoutFailure(), false);
    await current.source.captureNote({ text: "Pagué 300 por transporte" }, "new-note");
    assert.deepEqual(page.writes, [{ text: "Pagué 300 por transporte", grant: clientGrant }]);

    const add = current.actions.create.find((action) => action.id === "upload_receipt");
    assert.ok(add);
    await page.act(async () => add.run());
    const picker = () => document.querySelector<HTMLInputElement>('input[type="file"]:not([capture])');
    await page.waitFor(() => Boolean(picker()), "the receipt file picker");
    const input = picker();
    assert.ok(input);
    const transfer = new DataTransfer();
    transfer.items.add(new File(["synthetic receipt"], "new.jpg", { type: "image/jpeg" }));
    await page.act(async () => {
      input.files = transfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    assert.deepEqual(page.uploads, [{ filename: "new.jpg", grant: clientGrant }]);
  } finally {
    await page.close();
  }
});

test("a successful sign-out opens login and fences callbacks captured by the workspace", async () => {
  const page = await mount("left");
  try {
    await page.selectClient();
    const source = page.api().source;
    assert.equal(await page.signOut(), "left");
    assert.deepEqual(page.navigations, ["/?auth=login"]);
    assert.equal(page.chosenGrant(), null);
    await assert.rejects(source.workspace());
    assert.equal(page.logoutErrors(), 0);
  } finally {
    await page.close();
  }
});

for (const [outcome, title] of [
  ["cookie-failed", "Inicia sesión para continuar"],
  ["changed", "Cambió la cuenta activa"],
  ["unavailable", "No pudimos comprobar tu sesión"],
] as const) {
  test(`a failed logout with outcome ${outcome} keeps the old workspace closed`, async () => {
    const page = await mount(outcome);
    try {
      await page.selectClient();
      const source = page.api().source;
      const oldBoundary = page.boundary();
      assert.equal(await page.signOut(), "failed");
      await page.waitFor(() => page.recoveryHeading() === title, title);
      assert.equal(page.host.querySelector('[data-testid="workspace-probe"]'), null);
      assert.equal(oldBoundary.admission.current.signal.aborted, true);
      assert.equal(oldBoundary.recovery.takeLogoutFailure(), false);
      assert.deepEqual(page.navigations, []);
      await assert.rejects(source.captureNote({ text: "Old note" }, "old-note"));
      assert.deepEqual(page.writes, []);
      if (outcome === "unavailable") {
        await page.retryAsOwner();
        await page.api().source.captureNote({ text: "Nota tras reintentar" }, "logout-retry-note");
        assert.deepEqual(page.writes, [{ text: "Nota tras reintentar", grant: clientGrant }]);
        assert.equal(page.api().records.workspaceGrant, clientGrant);
      } else {
        assert.equal(page.chosenGrant(), null);
      }
    } finally {
      await page.close();
    }
  });
}

test.each([
  ["returned error", { delivery: "return", emitsSignedOut: false }],
  ["thrown error", { delivery: "throw", emitsSignedOut: false }],
  ["returned error after SIGNED_OUT", { delivery: "return", emitsSignedOut: true }],
  ["thrown error after SIGNED_OUT", { delivery: "throw", emitsSignedOut: true }],
] as const)("Retry after a focus check (%s) restores the selected client Business", async (_label, failure) => {
  const page = await mount();
  try {
    await page.selectClient();
    const oldSource = page.api().source;
    await page.failFocusCheck(failure);
    assert.equal(page.recoveryHeading(), "No pudimos comprobar tu sesión");
    assert.equal(page.host.querySelector('[data-testid="workspace-probe"]'), null);
    await assert.rejects(oldSource.captureNote({ text: "Old note" }, "old-note"));

    await page.retryAsOwner();
    await page.api().source.captureNote({ text: "Pagué 500 por materiales" }, "focus-retry-note");
    assert.deepEqual(page.writes, [{ text: "Pagué 500 por materiales", grant: clientGrant }]);
    assert.equal(page.api().records.workspaceGrant, clientGrant);
  } finally {
    await page.close();
  }
});

test("signing out in another tab closes the workspace and clears the selected client", async () => {
  const page = await mount();
  try {
    await page.selectClient();
    await page.signOutFromAnotherTab();
    assert.equal(page.recoveryHeading(), "Inicia sesión para continuar");
    assert.equal(page.host.querySelector('[data-testid="workspace-probe"]'), null);
    assert.equal(page.chosenGrant(), null);
  } finally {
    await page.close();
  }
});
