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
  const { default: BusinessSwitcher, BusinessMark } = await import("@/components/business-app/BusinessSwitcher");
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
  // A desktop Business keeps the person's account at the top right of the canvas.
  const profileSlot = document.createElement("div");
  profileSlot.dataset.testid = "canvas-header";
  document.body.appendChild(profileSlot);

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
    } as unknown as ChatShellBridge;
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
        profileSlot={profileSlot}
        primaryNav={<BusinessSidebarNav shell={shell} />}
        headerSlot={<BusinessSwitcher spaces={[OWN]} chosen={OWN} collapsed={shell.sidebarCollapsed} onChoose={() => {}} onOpenSettings={() => opened.push("settings")} />}
        headerMark={<BusinessMark name={OWN.name} />}
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
  // A faded label (opacity-0) still names the row for assistive tech, as sr-only did, but is not on screen.
  [...(button?.querySelectorAll("span") ?? [])].some((span) => span.textContent && !span.className.includes("sr-only") && !/\bopacity-0\b/.test(span.className) && !span.closest('[aria-hidden="true"]'));

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

test("the labeled rail stacks Inicio to Gastos under the business card, with the Cuadrao mark at the foot", async () => {
  await mountRail();
  assert.match(aside().className, /\bw-60\b/);
  assert.match(aside().className, /bg-\[var\(--cuadrao-cream\)\]/);
  assert.match(aside().className, /\bborder-r\b/);
  assert.deepEqual(
    rows().map((button) => button.textContent?.replace(/Ctrl.*$|⌘.*$/, "").replace(/\d+$/, "").trim()),
    ["Inicio", "Bandeja", "Gastos"],
  );
  for (const button of rows()) {
    assert.match(button.className, /\bh-11\b/, button.textContent ?? "");
    assert.doesNotMatch(button.className, /min-h-/, button.textContent ?? "");
    assert.equal(visibleLabel(button), true, button.textContent ?? "");
  }
  const nav = document.querySelector('[data-testid="business-sidebar-nav"]') as HTMLElement;
  assert.ok(nav.contains(row("Gastos")!));
  // The smallest box holding the toggle that also holds the business card: the header row.
  let header = document.querySelector('[data-testid="sidebar-rail-toggle"]')?.parentElement ?? null;
  while (header && header.tagName !== "ASIDE" && !header.querySelector('[data-testid="business-switcher"]')) header = header.parentElement;
  assert.ok(header?.querySelector('[data-testid="business-switcher"]'), "the business card sits beside the toggle at the top");
  assert.equal(header?.querySelector('[data-testid="business-current-name"]')?.textContent, "Ferretería Luna");
  assert.ok(header?.textContent?.includes("Dueño"), "the card names the role");
  assert.equal(header?.textContent?.includes("cuadrao"), false, "the product mark left the top");
  const brand = aside().querySelector('[data-testid="sidebar-brand"]') as HTMLElement;
  assert.ok(brand?.querySelector('img[src*="cuadrao-mark"]'));
  assert.ok(brand.textContent?.includes("cuadrao"));
  assert.ok(nav.compareDocumentPosition(brand) & Node.DOCUMENT_POSITION_FOLLOWING, "the mark sits below the screens");
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
  assert.match(active[0].className, /rounded-item/);
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
  assert.ok(document.querySelector('[data-testid="business-switcher"]'), "the open header stays while the rail closes, so nothing jumps");
  // The closed header takes over once the rail's 200ms close has run.
  await view.act(async () => { await new Promise((resolve) => setTimeout(resolve, 260)); });
  const toggles = [...document.querySelectorAll<HTMLButtonElement>('[data-testid="sidebar-rail-toggle"]')];
  assert.equal(toggles.length, 1, "the closed rail has one header button");
  const expand = toggles[0];
  assert.equal(document.querySelector('[data-testid="business-switcher"]'), null, "the closed rail drops the business card");
  assert.equal(expand.getAttribute("aria-label"), "Expandir");
  const face = expand.querySelector(":scope > span")!;
  assert.equal(face.textContent, "F", "the business's initial is the button's face");
  assert.match(face.className, /group-hover:opacity-0/, "hovering fades the mark out");
  assert.match(face.className, /group-focus-visible:opacity-0/, "focusing fades the mark out");
  const icon = expand.querySelector("svg")!;
  assert.match(icon.getAttribute("class") ?? "", /\bopacity-0\b/, "the expand icon waits hidden");
  assert.match(icon.getAttribute("class") ?? "", /group-hover:opacity-100/);
  assert.match(icon.getAttribute("class") ?? "", /group-focus-visible:opacity-100/);
  await view.act(async () => {
    expand.dispatchEvent(new MouseEvent("mouseover", { bubbles: true, relatedTarget: document.body }));
    await new Promise((resolve) => setTimeout(resolve, 350));
  });
  assert.equal(document.getElementById(expand.getAttribute("aria-describedby") ?? "")?.textContent, "Abrir barra lateral");
  for (const button of rows()) {
    // The row keeps its shape (the 64px rail's inset leaves it 44px wide) and its label fades instead of leaving.
    assert.match(button.className, /\bh-11\b/);
    assert.match(button.className, /\bw-full\b/);
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
  assert.ok(document.querySelector('[data-testid="business-switcher"]'), "open again, the business card is back");
  assert.equal(document.querySelector('[data-testid="sidebar-rail-toggle"]')?.getAttribute("aria-label"), "Contraer");
});

test("the tablet strip keeps the business card and no toggle", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: SidebarHeader } = await import("@/components/sidebar/SidebarHeader");
  const i18n = createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <SidebarHeader variant="rail" isOpen={false} railLocked business businessSlot={<span data-testid="card">Ferretería Luna</span>} businessMark={<span>F</span>} onToggle={() => {}} />
      </I18nextProvider>,
    );
  });
  cleanups.push(() => act(async () => root.unmount()));
  assert.ok(host.querySelector('[data-testid="card"]'));
  assert.equal(host.querySelector('[data-testid="sidebar-rail-toggle"]'), null);
});

test("the account lives at the top right, and the rail has no Negocio, Acceso or Ajustes row", async () => {
  const view = await mountRail();
  assert.equal(row("Negocio"), undefined, "the business card's menu is the door to Negocio");
  assert.equal(row("Acceso"), undefined);
  assert.equal(row("Ajustes"), undefined);
  const trigger = document.querySelector<HTMLButtonElement>('[data-testid="header-profile-trigger"]');
  assert.ok(trigger?.closest('[data-testid="canvas-header"]'), "the account trigger is in the canvas header");
  assert.equal(aside().contains(trigger), false);
  await view.act(async () => trigger!.click());
  assert.equal(trigger!.getAttribute("aria-expanded"), "true");
  assert.ok(!(document.body.textContent ?? "").includes(spanish.settings.sidebar.title), "Business offers no rail preference");
});

test("the business card menu opens the Negocio page", async () => {
  const view = await mountRail();
  await view.act(async () => document.querySelector<HTMLButtonElement>('[data-testid="business-switcher"] button[aria-haspopup="menu"]')!.click());
  const settings = [...document.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')].find((item) => item.textContent?.includes("Configurar negocio"));
  await view.act(async () => settings!.click());
  assert.deepEqual(view.opened, ["settings"]);
});
