import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessWorkspaceInfo } from "@/lib/business-api";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";

// The server's `invoicing_available` on GET /business/workspace is the one switch for Facturación. The real
// workspace provider reads it: every entry point hides while it is false or unanswered, a deep link to an
// unavailable Facturación lands on Inicio, and the design sample still answers `?invoicePreview` in development.
let search = "";
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

const original = { node: process.env.NODE_ENV, mock: process.env.NEXT_PUBLIC_MOCK_AUTH };
const cleanups: (() => Promise<void>)[] = [];
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  document.body.innerHTML = "";
  window.history.replaceState(null, "", "/biz");
  if (original.node === undefined) Reflect.deleteProperty(process.env, "NODE_ENV"); else Reflect.set(process.env, "NODE_ENV", original.node);
  if (original.mock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = original.mock;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

const shell: ChatShellBridge = { currentView: "workspace", conversationId: null, isBelowTablet: false, sidebarCollapsed: false, greetingName: null, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined };

type Source = ReturnType<typeof import("@/components/business-app/fixture-data").createFixtureBusinessDataSource>;

/**
 * Mounts the real provider over the fixture source, with the server's workspace answer under this test's control,
 * and the desktop top bar the shell would draw from `headerSearch`.
 */
async function mount(answer: { available: boolean } | "hold", url = "/biz", overrides: Partial<Source> = {}) {
  search = url.includes("?") ? url.slice(url.indexOf("?")) : "";
  window.history.replaceState(null, "", url);
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { default: BusinessSidebarNav } = await import("@/components/business-app/BusinessSidebarNav");
  const { default: BusinessPanel } = await import("@/components/business-app/BusinessPanel");
  const { setChosenGrant } = await import("@/lib/business-grant");
  const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  let release: ((workspace: BusinessWorkspaceInfo) => void) | null = null;
  const source = {
    ...fixture,
    workspace: async (): Promise<BusinessWorkspaceInfo> => {
      const workspace = await fixture.workspace();
      if (answer === "hold") return new Promise((resolve) => { release = resolve; });
      return { ...workspace, invoicing_available: answer.available };
    },
    ...overrides,
  };
  let api: ReturnType<typeof useBusiness> | null = null;
  function Probe() {
    api = useBusiness();
    return <p data-testid="probe-panel">{api.panel.kind}</p>;
  }
  function Bar() {
    const workspace = useChatWorkspace();
    return <header data-testid="top-bar">{workspace?.headerSearch?.(shell)}</header>;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as never} userId="user-1">
            <Probe />
            <Bar />
            <BusinessSidebarNav shell={shell} />
            <BusinessPanel />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 40 && !done(); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    assert.ok(done(), "the provider never settled");
  };
  // A held workspace answer holds the whole first load, so that case waits on the directory alone; a failed read settles on its error.
  await settle(() => api !== null && (answer === "hold" ? api.spaces !== null : api.records.inbox !== null || api.records.error));
  cleanups.push(async () => { await act(async () => root.unmount()); host.remove(); });
  const navItems = () => [...host.querySelectorAll('[data-testid="business-sidebar-nav"] button')].map((node) => node.textContent?.trim() ?? "");
  const text = () => host.textContent ?? "";
  const heading = () => host.querySelector('[data-testid="top-bar"] h1')?.textContent?.trim() ?? null;
  return {
    act, host, settle, navItems, text, heading,
    api: () => api!,
    // Waits for the read in flight to hold before answering it, so a reload's fresh read is the one released.
    release: async (workspace: Partial<BusinessWorkspaceInfo>) => {
      await settle(() => release !== null);
      const answer = release!;
      release = null;
      await act(async () => { answer({ ...(await fixture.workspace()), ...workspace }); });
    },
  };
}

test("server says unavailable: no entry point anywhere, and the deep link lands on Inicio, never on a refusal", async () => {
  const page = await mount({ available: false }, "/biz?view=invoicing");
  await page.settle(() => page.api().panel.kind === "overview");
  assert.equal(page.api().invoicing, "unavailable");
  assert.ok(!page.navItems().includes("Facturación"), page.navItems().join("|"));
  assert.ok(!page.text().includes("No tienes acceso"), "the no-access line must never show");
  assert.ok(!page.text().includes("Facturación"), "nothing on screen names Facturación");
  assert.equal(new URLSearchParams(window.location.search).get("view"), null);
});

test("server says available: the sidebar item and the deep link show", async () => {
  const page = await mount({ available: true }, "/biz?view=invoicing");
  await page.settle(() => page.api().invoicing === "available");
  assert.ok(page.navItems().includes("Facturación"), page.navItems().join("|"));
  assert.equal(page.api().panel.kind, "invoicing");
  assert.equal(new URLSearchParams(window.location.search).get("view"), "invoicing");
});

test("while the server has not answered nothing shows for Facturación, and its answer then decides", async () => {
  const page = await mount("hold", "/biz?view=invoicing");
  assert.equal(page.api().invoicing, null);
  assert.ok(!page.navItems().includes("Facturación"), "no flash of the sidebar item");
  assert.equal(page.api().panel.kind, "invoicing");
  assert.ok(!page.text().includes("Facturación"), "the screen stays empty until the answer");
  assert.ok(!page.text().includes("No tienes acceso"));
  await page.release({ invoicing_available: false });
  await page.settle(() => page.api().panel.kind === "overview");
  assert.ok(!page.navItems().includes("Facturación"));
});

test("the top bar names Facturación only once the server says available: not while held, not when unavailable", async () => {
  const page = await mount("hold", "/biz?view=invoicing");
  assert.equal(page.api().panel.kind, "invoicing");
  assert.equal(page.heading(), null, "no Facturación heading before the answer");
  assert.ok(!page.text().includes("Facturación"), "nothing on screen names Facturación before the answer");
  await page.release({ invoicing_available: false });
  await page.settle(() => page.api().panel.kind === "overview");
  assert.ok(!page.text().includes("Facturación"), "nothing names Facturación once the server said no");
  // The next answer says yes: the same screen now carries its heading.
  await page.act(async () => page.api().reload());
  await page.release({ invoicing_available: true });
  await page.settle(() => page.api().invoicing === "available");
  await page.act(async () => page.api().openPanel({ kind: "invoicing" }));
  await page.settle(() => page.heading() === "Facturación");
  assert.ok(page.navItems().includes("Facturación"));
});

test("a failed overview read leaves no Facturación heading on a deep link", async () => {
  const page = await mount({ available: true }, "/biz?view=invoicing", { overview: async () => { throw new Error("synthetic overview failure"); } });
  assert.equal(page.api().records.error, true);
  assert.equal(page.api().invoicing, null, "no workspace answer was kept, so Facturación is unanswered");
  assert.equal(page.heading(), null);
  assert.ok(!page.text().includes("Facturación"), page.text().slice(0, 200));
});

test("the design sample answers ?invoicePreview in development with mock auth, whatever the server says", async () => {
  Reflect.set(process.env, "NODE_ENV", "development"); process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  const page = await mount({ available: false }, "/biz?view=invoicing&invoicePreview=seeded");
  await page.settle(() => page.api().invoicing === "sample");
  assert.ok(page.navItems().includes("Facturación"), page.navItems().join("|"));
  assert.equal(page.api().panel.kind, "invoicing");
  await page.settle(() => page.host.querySelector('[data-testid="invoicing-preview"]') !== null);
});

test("outside development the preview query changes nothing", async () => {
  Reflect.set(process.env, "NODE_ENV", "production"); process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  const page = await mount({ available: false }, "/biz?view=invoicing&invoicePreview=seeded");
  await page.settle(() => page.api().panel.kind === "overview");
  assert.equal(page.api().invoicing, "unavailable");
  assert.ok(!page.navItems().includes("Facturación"));
});
