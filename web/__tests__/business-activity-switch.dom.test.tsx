import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessWorkspaceInfo } from "@/lib/business-api";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";

// The server's `activity_available` on GET /business/workspace is the one switch for Actividad. Off or unanswered,
// there is no sidebar entry, no phone-menu row, a direct link falls back to Inicio, and the screen (the only thing
// that reads the feed) is never mounted, so no request is made. The feed's own mount count stands in for requests.
let search = "";
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));
let feedMounts = 0;
mock.module("@/components/business-app/actividad/ActivityDraft", () => ({
  default: function ActivityDraftSpy() {
    feedMounts += 1;
    return <p data-testid="activity-screen">Actividad</p>;
  },
}));

const cleanups: (() => Promise<void>)[] = [];
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  document.body.innerHTML = "";
  window.history.replaceState(null, "", "/biz");
  feedMounts = 0;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

const shell: ChatShellBridge = { currentView: "workspace", conversationId: null, isBelowTablet: false, sidebarCollapsed: false, greetingName: null, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined };

async function mount(answer: { activity_available?: boolean } | "hold", url = "/biz") {
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
      const { activity_available: _kept, ...rest } = workspace;
      return "activity_available" in answer ? { ...rest, activity_available: answer.activity_available } : rest;
    },
  };
  let api: ReturnType<typeof useBusiness> | null = null;
  function Probe() {
    api = useBusiness();
    return <p data-testid="probe-panel">{api.panel.kind}</p>;
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
  await settle(() => api !== null && (answer === "hold" ? api.spaces !== null : api.records.inbox !== null || api.records.error));
  cleanups.push(async () => { await act(async () => root.unmount()); host.remove(); });
  return {
    act, host, settle,
    navItems: () => [...host.querySelectorAll('[data-testid="business-sidebar-nav"] button')].map((node) => node.textContent?.trim() ?? ""),
    api: () => api!,
    release: async (workspace: Partial<BusinessWorkspaceInfo>) => {
      await settle(() => release !== null);
      const answerNow = release!;
      release = null;
      await act(async () => { answerNow({ ...(await fixture.workspace()), ...workspace }); });
    },
  };
}

test("only the server's explicit answer turns Actividad on", async () => {
  const { businessActivityAvailable } = await import("@/lib/business-api");
  assert.equal(businessActivityAvailable(null), false);
  assert.equal(businessActivityAvailable({} as never), false);
  assert.equal(businessActivityAvailable({ activity_available: false }), false);
  assert.equal(businessActivityAvailable({ activity_available: true }), true);
});

test("off: no sidebar entry, and the direct link falls back to Inicio without mounting the feed", async () => {
  const page = await mount({ activity_available: false }, "/biz?view=activity");
  await page.settle(() => page.api().panel.kind === "overview");
  assert.equal(page.api().activity, "unavailable");
  assert.ok(!page.navItems().includes("Actividad"), page.navItems().join("|"));
  assert.equal(page.host.querySelector('[data-testid="activity-screen"]'), null);
  assert.equal(new URLSearchParams(window.location.search).get("view"), null);
  assert.equal(feedMounts, 0, "no feed, so no request");
});

test("an older payload without the field is off too", async () => {
  const page = await mount({}, "/biz?view=activity");
  await page.settle(() => page.api().panel.kind === "overview");
  assert.ok(!page.navItems().includes("Actividad"));
  assert.equal(feedMounts, 0);
});

test("opening the panel by hand while off shows nothing and reads nothing", async () => {
  const page = await mount({ activity_available: false });
  await page.act(async () => page.api().openPanel({ kind: "activity" }));
  await page.settle(() => page.api().panel.kind === "overview");
  assert.equal(page.host.querySelector('[data-testid="activity-screen"]'), null);
  assert.equal(feedMounts, 0);
});

test("on: the sidebar entry and the deep link work as before", async () => {
  const page = await mount({ activity_available: true }, "/biz?view=activity");
  await page.settle(() => page.api().activity === "available");
  assert.ok(page.navItems().includes("Actividad"), page.navItems().join("|"));
  assert.equal(page.api().panel.kind, "activity");
  assert.ok(page.host.querySelector('[data-testid="activity-screen"]'));
  assert.ok(feedMounts >= 1);
});

test("until the server answers nothing shows, and its answer then decides", async () => {
  const page = await mount("hold", "/biz?view=activity");
  assert.equal(page.api().activity, null);
  assert.ok(!page.navItems().includes("Actividad"), "no flash of the entry");
  assert.equal(feedMounts, 0, "no request before the answer");
  await page.release({ activity_available: false });
  await page.settle(() => page.api().panel.kind === "overview");
  assert.ok(!page.navItems().includes("Actividad"));
  assert.equal(feedMounts, 0);
});
