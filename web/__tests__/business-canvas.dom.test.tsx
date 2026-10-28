import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessPanelState } from "@/components/business-app/BusinessWorkspace";

// The real workspace in the real main area: one canvas, left-aligned, the same on every screen.
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});
const unmounts: (() => Promise<void>)[] = [];
afterEach(async () => {
  while (unmounts.length) await unmounts.pop()!();
  document.body.innerHTML = "";
});

async function mount() {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
  const { WorkspaceMain } = await import("@/components/chat/WorkspaceMain");
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const source = { ...createFixtureBusinessDataSource({ chatAvailable: false }), captures: async () => ({ items: [] }) };
  const bridge = { currentView: "workspace", conversationId: null, isBelowTablet: false, sidebarCollapsed: false, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined, openSearch: undefined };
  let api: ReturnType<typeof useBusiness> | null = null;
  function Main() {
    api = useBusiness();
    const workspace = useChatWorkspace()!;
    return <WorkspaceMain workspace={workspace} bridge={bridge as never} composerNotice={null} disabled={false} onToast={() => undefined} onSend={() => undefined} setCurrentView={() => undefined} />;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(
    <I18nextProvider i18n={i18n}>
      <BusinessConsentTestProvider accepted>
        <BusinessWorkspaceProvider source={source as BusinessDataSource}><Main /></BusinessWorkspaceProvider>
      </BusinessConsentTestProvider>
    </I18nextProvider>,
  ));
  unmounts.push(async () => { await act(async () => root.unmount()); });
  const settle = async (done: () => boolean, what: string) => {
    for (let i = 0; i < 80; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      if (done()) return;
    }
    throw new Error(`timed out waiting for ${what}`);
  };
  const open = async (panel: BusinessPanelState) => { await act(async () => api!.openPanel(panel)); };
  return { host, open, settle, api: () => api! };
}

const SCREENS = [
  { kind: "overview", column: "canvas", ready: '[data-testid="month-close"]' },
  { kind: "inbox", column: "canvas", ready: '[data-testid="reception-row"]' },
  { kind: "transactions", column: "canvas", ready: '[data-testid="transacciones"]' },
  { kind: "business", column: "canvas", ready: '[data-testid="business-settings"]' },
] as const;

describe("one canvas for every Business screen", () => {
  test("the canvas fills the main area inside its gutters while reading and form columns stay narrow", async () => {
    const page = await mount();
    for (const screen of SCREENS) {
      await page.open({ kind: screen.kind });
      await page.settle(() => page.api().panel.kind === screen.kind && page.host.querySelector(screen.ready) !== null, screen.kind);
      const region = page.host.querySelector<HTMLElement>('[data-testid="workspace-panel-region"]')!;
      const canvas = page.host.querySelector<HTMLElement>('[data-testid="workspace-canvas"]')!;
      assert.match(region.className, /(^|\s)tablet:px-8(\s|$)/, `${screen.kind}: the 2rem gutter`);
      assert.match(region.className, /(^|\s)px-4(\s|$)/, `${screen.kind}: the phone gutter`);
      assert.match(canvas.className, /(^|\s)w-full(\s|$)/, `${screen.kind}: one fluid canvas`);
      assert.doesNotMatch(canvas.className, /max-w-/, `${screen.kind}: no cap on the shared canvas`);
      for (const node of [region.parentElement!, canvas, canvas.firstElementChild as HTMLElement]) {
        assert.doesNotMatch(node.className, /mx-auto/, `${screen.kind}: left-aligned, never centred`);
      }
      assert.doesNotMatch(region.parentElement!.className, /max-w/, `${screen.kind}: the main area spans its width`);
      assert.equal((canvas.firstElementChild as HTMLElement).dataset.column, screen.column, `${screen.kind}'s column inside the canvas`);
      if (screen.column === "reading") assert.match((canvas.firstElementChild as HTMLElement).className, /max-w-3xl/);
      if (screen.column === "form") assert.match((canvas.firstElementChild as HTMLElement).className, /max-w-\[40rem\]/);
      assert.equal(document.documentElement.style.getPropertyValue("--cuadrao-canvas-max"), "", `${screen.kind}: no screen widens the canvas`);
      assert.equal(document.documentElement.style.getPropertyValue("--cuadrao-canvas-column"), "", `${screen.kind}: no screen moves the bar`);
    }
  });

  test("the top bar and canvas share fixed 1rem phone and 2rem tablet gutters", async () => {
    const { WORKSPACE_BAR_PADDING_CLASS, WORKSPACE_CANVAS_CLASS } = await import("@/components/chat/workspace-canvas");
    assert.equal(WORKSPACE_CANVAS_CLASS, "w-full");
    assert.equal(WORKSPACE_BAR_PADDING_CLASS, "tablet:px-8");
  });
});
