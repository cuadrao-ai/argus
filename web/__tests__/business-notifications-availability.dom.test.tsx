import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDirectory } from "@/lib/business-api";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";

mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

const cleanups: (() => Promise<void>)[] = [];
const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  globalThis.fetch = originalFetch;
  document.body.innerHTML = "";
});
afterAll(async () => {
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  await GlobalRegistrator.unregister();
});

async function mount(width: number, initial: boolean | undefined | "hold") {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const requests: string[] = [];
  globalThis.fetch = async (url) => { requests.push(String(url)); return Response.json({ items: [], unread_count: 0 }); };
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 900 });
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  let answer = initial;
  let asked = 0;
  let release: ((value: BusinessDirectory) => void) | undefined;
  // The person's directory read carries the switch: the bell is theirs, not a Business's.
  const directory = async (available: boolean | undefined): Promise<BusinessDirectory> => ({ spaces: await fixture.spaces(), closed_spaces: [], ...(available === undefined ? {} : { notifications_available: available }) });
  const source = {
    ...fixture,
    spaceDirectory: async (): Promise<BusinessDirectory> => {
      asked += 1;
      if (answer === "hold") return new Promise((resolve) => { release = resolve; });
      return directory(answer);
    },
  };
  let business: ReturnType<typeof useBusiness> | undefined;
  const shell: ChatShellBridge = { currentView: "workspace", conversationId: null, isBelowTablet: width < 768, sidebarCollapsed: false, greetingName: null, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined };
  function Header() {
    business = useBusiness();
    return <header>{useChatWorkspace()?.headerActions(shell)}</header>;
  }
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  cleanups.push(async () => { await act(async () => root.unmount()); host.remove(); });
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source} userId="notification-user"><Header /></BusinessWorkspaceProvider></BusinessConsentTestProvider></I18nextProvider>));
  const settle = async (ready: () => boolean) => {
    for (let i = 0; i < 40 && !ready(); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    assert.ok(ready(), "workspace did not settle");
  };
  await settle(() => initial === "hold" ? release !== undefined : business?.directoryStatus === "ready" && business.records.workspace != null);
  return {
    act, host, settle,
    bell: () => host.querySelector<HTMLButtonElement>('[aria-label="Notificaciones"]'),
    notificationRequests: () => requests.filter((url) => /\/business\/(?:notifications|invitations|email\/senders)/.test(url)),
    release: async (available: boolean) => { const value = await directory(available); await act(async () => release!(value)); await settle(() => business?.directoryStatus === "ready"); },
    reload: async (available: boolean) => { answer = available; const before = asked; await act(async () => business!.reload()); await settle(() => asked > before && business?.directoryStatus === "ready"); },
  };
}

for (const width of [1440, 390]) {
  for (const available of [false, undefined]) {
    test(`notifications ${String(available)}: no bell or notification requests at ${width}px`, async () => {
      const page = await mount(width, available);
      assert.equal(page.bell() !== null, false);
      assert.deepEqual(page.notificationRequests(), []);
    });
  }
  test(`notifications on: the bell still opens at ${width}px`, async () => {
    const page = await mount(width, true);
    assert.ok(page.bell());
    await page.act(async () => page.bell()!.click());
    assert.ok(document.querySelector('[role="dialog"]'));
  });
}

test("the bell stays absent until the directory answers, then follows refreshed availability", async () => {
  const page = await mount(1440, "hold");
  assert.equal(page.bell() !== null, false);
  assert.deepEqual(page.notificationRequests(), []);
  await page.release(true);
  assert.ok(page.bell());
  await page.reload(false);
  assert.equal(page.bell() !== null, false);
  assert.equal(document.querySelector('[role="dialog"]'), null);
});
