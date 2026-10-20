import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import type { GrantedSpace } from "@/lib/business-api";
import type { BusinessContextValue, BusinessPanelState } from "@/components/business-app/BusinessWorkspace";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";
import spanish from "@/public/locales/es-419/common.json";

const cleanups: (() => Promise<void>)[] = [];
const OWN: GrantedSpace = { space_id: "s-own", name: "Ferretería Luna", grant_id: "g-own", role: "owner", capabilities: ["read", "prepare", "approve"], access_seen: true };
const activity = {
  hasEffectiveUnread: () => false,
  selectAttentionCursor: () => null,
  markRead: async () => {},
  markUnread: async () => {},
  isMutationPending: () => false,
};

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  window.localStorage.clear();
  document.body.innerHTML = "";
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function mountRail(options: { storedMode?: string; panel?: BusinessPanelState["kind"] } = {}) {
  if (options.storedMode) window.localStorage.setItem("argus:sidebar_mode", options.storedMode);
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: ChatSidebar } = await import("@/components/sidebar/ChatSidebar");
  const { default: BusinessSidebarNav, BusinessSidebarFooter } = await import("@/components/business-app/BusinessSidebarNav");
  const { default: BusinessSwitcher } = await import("@/components/business-app/BusinessSwitcher");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { businessShellLayout, useSidebarRail } = await import("@/components/chat/useMobileShell");
  const i18n = createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const opened: string[] = [];
  const business = {
    panel: { kind: options.panel ?? "overview" },
    openPanel: (panel: BusinessPanelState) => opened.push(panel.kind),
    records: { inbox: [{ status: "needs_review" }, { status: "needs_review" }, { status: "needs_review" }] },
  } as unknown as BusinessContextValue;
  const rail: { closeRailForDialog?: () => void } = {};

  function DesktopRail() {
    const state = useSidebarRail("business");
    rail.closeRailForDialog = state.closeRailForDialog;
    const layout = businessShellLayout("business", false, false, state.isSidebarOpen);
    const shell = {
      currentView: "workspace",
      conversationId: null,
      isBelowTablet: false,
      sidebarCollapsed: layout.sidebarCollapsed,
      showWorkspace: () => {},
      newChat: () => {},
      prepareQuestion: () => {},
    } as ChatShellBridge;
    return (
      <ChatSidebar
        isOpen={layout.sidebarIsOpen}
        railLocked={layout.railLocked}
        business={layout.businessShell}
        mode={state.sidebarMode}
        onToggle={state.toggleSidebar}
        currentView="workspace"
        conversationId={null}
        conversationActivity={activity}
        isRecentsExpanded={false}
        onToggleRecents={() => {}}
        historyItems={[]}
        historyNextCursor={null}
        isLoadingMoreHistory={false}
        hasRequestedOlderHistory={false}
        historyLoadMoreError={false}
        onNewChat={() => {}}
        onNavigate={() => {}}
        onOpenItem={() => {}}
        onLoadMoreHistory={() => {}}
        onOpenSearch={() => {}}
        onLogout={() => {}}
        onOpenSidebarPreference={() => {}}
        showProfileMenu
        primaryNav={<BusinessSidebarNav shell={shell} />}
        headerSlot={<BusinessSwitcher spaces={[OWN]} chosen={OWN} collapsed={shell.sidebarCollapsed} onChoose={() => {}} onOpenAccess={() => {}} />}
        footerActions={<BusinessSidebarFooter shell={shell} />}
      />
    );
  }

  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessContext.Provider value={business}>
          <DesktopRail />
        </BusinessContext.Provider>
      </I18nextProvider>,
    );
  });
  await act(async () => { await Promise.resolve(); });
  cleanups.push(() => act(async () => root.unmount()));
  return { act, host, opened, rail };
}

const aside = () => document.querySelector("aside") as HTMLElement;
const rows = () => [...document.querySelectorAll<HTMLButtonElement>('[data-sidebar-row="business"]')];
const row = (label: string) => rows().find((button) => button.textContent?.includes(label));
const visibleLabel = (button: HTMLButtonElement | undefined) =>
  [...(button?.querySelectorAll("span") ?? [])].some((span) => span.textContent && !span.className.includes("sr-only") && !span.closest('[aria-hidden="true"]'));

test("a saved collapsed or hover preference does not collapse the Business rail", async () => {
  for (const storedMode of ["collapsed", "hover"]) {
    const view = await mountRail({ storedMode });
    assert.match(aside().className, /\bw-60\b/, storedMode);
    assert.equal(visibleLabel(row("Inicio")), true, storedMode);
    await view.act(async () => {
      aside().dispatchEvent(new MouseEvent("mouseout", { bubbles: true, relatedTarget: document.body }));
    });
    assert.match(aside().className, /\bw-60\b/, `${storedMode} after the pointer leaves`);
    for (const cleanup of cleanups.splice(0)) await cleanup();
    window.localStorage.clear();
  }
});

test("the labeled rail stacks Inicio to Gastos on top, Acceso and Ajustes at the foot", async () => {
  await mountRail();
  assert.match(aside().className, /\bw-60\b/);
  assert.match(aside().className, /bg-\[var\(--cuadrao-cream\)\]/);
  assert.match(aside().className, /\bborder-r\b/);
  assert.deepEqual(
    rows().map((button) => button.textContent?.replace(/Ctrl.*$|⌘.*$/, "").replace(/\d+$/, "").trim()),
    ["Inicio", "Bandeja", "Gastos", "Acceso", "Ajustes"],
  );
  for (const button of rows()) {
    assert.match(button.className, /\bh-11\b/, button.textContent ?? "");
    assert.doesNotMatch(button.className, /min-h-/, button.textContent ?? "");
    assert.equal(visibleLabel(button), true, button.textContent ?? "");
  }
  const nav = document.querySelector('[data-testid="business-sidebar-nav"]') as HTMLElement;
  assert.ok(nav.contains(row("Gastos")!));
  assert.ok(!nav.contains(row("Acceso")!));
  assert.equal(document.querySelector('[data-testid="business-current-name"]')?.textContent, "Ferretería Luna");
  assert.equal(document.querySelector('[data-testid="business-switcher"] button[aria-haspopup="menu"]') !== null, true);
  const header = document.querySelector('[data-testid="sidebar-rail-toggle"]')?.parentElement;
  assert.match(header?.className ?? "", /\bh-14\b/);
  assert.ok(header?.textContent?.includes("cuadrao"));
  assert.equal(row("Bandeja")?.querySelector('[data-testid="business-inbox-count"]')?.textContent, "3");
});

test("the active fill is the row itself, in the approved green", async () => {
  await mountRail({ panel: "inbox" });
  const active = rows().filter((button) => button.getAttribute("aria-current") === "page");
  assert.equal(active.length, 1);
  assert.ok(active[0].textContent?.includes("Bandeja"));
  assert.match(active[0].className, /bg-\[#e3ebe1\]/);
  assert.match(active[0].className, /text-\[#2f5a49\]/);
  assert.match(active[0].className, /font-medium/);
  assert.match(active[0].className, /\bh-11\b/);
  assert.match(active[0].className, /rounded-\[12px\]/);
  for (const button of rows().filter((candidate) => candidate !== active[0])) {
    assert.doesNotMatch(button.className, /bg-\[#e3ebe1\] /);
  }
});

test("only the toggle collapses the rail to 64px icons with tooltips", async () => {
  const view = await mountRail();
  await view.act(async () => view.rail.closeRailForDialog?.());
  assert.match(aside().className, /\bw-60\b/, "a dialog does not collapse the Business rail");
  await view.act(async () => {
    (document.querySelector('[data-testid="sidebar-rail-toggle"]') as HTMLButtonElement).click();
  });
  assert.match(aside().className, /\bw-16\b/);
  for (const button of rows()) {
    assert.match(button.className, /\bh-11\b/);
    assert.match(button.className, /\bw-11\b/);
    assert.equal(visibleLabel(button), false, button.textContent ?? "");
  }
  const inicio = row("Inicio")!;
  await view.act(async () => {
    inicio.dispatchEvent(new MouseEvent("mouseover", { bubbles: true, relatedTarget: document.body }));
    await new Promise((resolve) => setTimeout(resolve, 350));
  });
  const tooltip = document.getElementById(inicio.getAttribute("aria-describedby") ?? "");
  assert.ok(tooltip?.textContent?.includes("Inicio"), "the collapsed row names itself in a tooltip");
  await view.act(async () => {
    (document.querySelector('[data-testid="sidebar-rail-toggle"]') as HTMLButtonElement).click();
  });
  assert.match(aside().className, /\bw-60\b/);
});

test("Acceso opens the access panel and the rail has no sidebar preference entry", async () => {
  const view = await mountRail();
  await view.act(async () => row("Acceso")!.click());
  assert.deepEqual(view.opened, ["access"]);
  await view.act(async () => row("Ajustes")!.click());
  const menuText = document.body.textContent ?? "";
  assert.ok(!menuText.includes(spanish.settings.sidebar.title), "Business offers no rail preference");
});
