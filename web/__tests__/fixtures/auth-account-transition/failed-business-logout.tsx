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
let session: typeof owner | null;
let revocationFails: boolean;
let cookieSyncFails: boolean;
let checkError: Error | null;
const listeners = new Set<AuthListener>();
const searchParams = new URLSearchParams("");
const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;

mock.module("next/navigation", () => ({
  useSearchParams: () => searchParams,
  useRouter: () => ({ push() {}, replace() {} }),
  usePathname: () => "/biz",
}));
mock.module("@/lib/supabase-client", () => ({
  getSupabaseClient: () => ({
    auth: {
      onAuthStateChange(next: AuthListener) {
        listeners.add(next);
        return { data: { subscription: { unsubscribe: () => { listeners.delete(next); } } } };
      },
      getSession: async () => ({ data: { session }, error: checkError }),
      getUser: async () => ({ data: { user: session?.user ?? null }, error: null }),
      async signOut() {
        if (revocationFails) return { error: new Error("Revocation failed") };
        session = null;
        listeners.forEach((listener) => listener("SIGNED_OUT", session));
        return { error: null };
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
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  await GlobalRegistrator.unregister();
});

async function mount() {
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
  const spaces = (await fixture.spaces()).map((space) => ({
    ...space,
    grant_id: space.role === "owner" ? ownGrant : clientGrant,
    access_seen: true,
  }));
  const workspace = await fixture.workspace();
  const [receipt] = await fixture.receipts("inbox");
  assert.ok(receipt);
  const requests = { synchronizeAccountScope: () => true } as unknown as ChatRequestSessionController;
  const writes: { text: string; grant: string | null }[] = [];
  const uploads: { filename: string; grant: string | null }[] = [];
  const navigations: string[] = [];
  const unexpectedRequests: string[] = [];
  let api: BusinessContextValue;
  let logout!: () => Promise<"left" | "failed">;
  let nextRead: Promise<BusinessWorkspaceInfo> | null = null;
  let logoutErrors = 0;

  session = owner;
  revocationFails = true;
  cookieSyncFails = false;
  checkError = null;
  resetLeavingSession();
  synchronizeBusinessAccount(null);
  globalThis.fetch = (async (url) => {
    const path = new URL(String(url)).pathname;
    if (path.endsWith("/auth/logout")) return Response.json({ success: !cookieSyncFails }, { status: cookieSyncFails ? 503 : 200 });
    if (path.endsWith("/business/spaces")) return Response.json({ spaces });
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
    workspace: async () => {
      const deferred = nextRead;
      nextRead = null;
      return deferred ?? workspace;
    },
    captureNote: async (input, key) => {
      writes.push({ text: input.text, grant: getChosenGrant() });
      return fixture.captureNote(input, key);
    },
    uploadReceipt: async (file) => {
      uploads.push({ filename: file.name, grant: getChosenGrant() });
      return { ...receipt, filename: file.name };
    },
  };
  Object.assign(liveBusinessDataSource, source);

  Probe = function BusinessProbe() {
    api = useBusiness();
    const boundary = useChatAccountBoundary(api.userId ?? null, requests, () => {});
    logout = () => leaveSession({
      boundary,
      currentUserId: api.userId ?? null,
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
    act, host, ready, waitFor, navigations, writes, uploads, api: () => api, logoutErrors: () => logoutErrors,
    async signOut() {
      let result: "left" | "failed" | undefined;
      await act(async () => { result = await logout(); });
      return result;
    },
    deferRead: (read: Promise<BusinessWorkspaceInfo>) => { nextRead = read; },
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

test("a failed sign-out leaves new Business reads, notes and uploads usable without reviving old callbacks", async () => {
  const page = await mount();
  try {
    await page.ready();
    await page.act(async () => page.api().chooseBusiness(clientGrant));
    await page.waitFor(() => page.api().records.workspaceGrant === clientGrant, "selected client's records");
    const oldSource = page.api().source;
    const reply = Promise.withResolvers<BusinessWorkspaceInfo>();
    page.deferRead(reply.promise);
    const lateRead = assert.rejects(oldSource.workspace());
    await Promise.resolve();

    assert.equal(await page.signOut(), "failed");
    assert.equal(page.logoutErrors(), 1);
    assert.deepEqual(page.navigations, []);
    reply.resolve(await createWorkspace());
    await lateRead;
    await assert.rejects(oldSource.captureNote({ text: "Old note" }, "old-note"));

    await page.ready();
    const current = page.api();
    assert.equal((await current.source.workspace()).currency, "DOP");
    await current.source.captureNote({ text: "Pagué 300 por transporte" }, "new-note");
    assert.deepEqual(page.writes, [{ text: "Pagué 300 por transporte", grant: clientGrant }]);

    const add = current.actions.create.find((action) => action.id === "upload_receipt");
    assert.ok(add);
    await page.act(async () => add.run());
    const input = page.host.querySelector<HTMLInputElement>('input[type="file"]:not([capture])');
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

async function createWorkspace() {
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  return createFixtureBusinessDataSource().workspace();
}

test("a successful sign-out opens login and fences callbacks captured by the workspace", async () => {
  const page = await mount();
  try {
    await page.ready();
    const source = page.api().source;
    revocationFails = false;
    assert.equal(await page.signOut(), "left");
    assert.deepEqual(page.navigations, ["/?auth=login"]);
    await assert.rejects(source.workspace());
    assert.equal(page.logoutErrors(), 0);
  } finally {
    await page.close();
  }
});
