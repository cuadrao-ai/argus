import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessPanelState } from "@/components/business-app/BusinessWorkspace";

// The real workspace over the sample source, with the top bar the workspace
// hands the chat shell (Home greeting, search field, the eye) beside the screen
// the panel router shows.
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

const HIDE_KEY = "cuadrao:hide_amounts";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1280, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const unmounts: (() => Promise<void>)[] = [];
afterEach(async () => {
  while (unmounts.length) await unmounts.pop()!();
  const { setAmountsHidden } = await import("@/lib/amounts-hidden");
  setAmountsHidden(false);
  localStorage.removeItem(HIDE_KEY);
  delete document.documentElement.dataset.amountsHidden;
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
});

async function mount({ width = 1280, grant = null, overrides = {}, renderPanel = true }: { width?: number; grant?: string | null; overrides?: Partial<BusinessDataSource>; renderPanel?: boolean } = {}) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 900 });
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
  const { setChosenGrant } = await import("@/lib/business-grant");
  const { clearToasts } = await import("@/components/business-app/foundation/toasts");
  setChosenGrant(grant);
  clearToasts();
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const source = { ...createFixtureBusinessDataSource({ chatAvailable: true }), captures: async () => ({ items: [] }), ...overrides };
  const searches: string[] = [];
  const invitationTriggers: HTMLElement[] = [];
  const below = width < 720;
  const shell = { currentView: "workspace", conversationId: null, greetingName: "Ana", isBelowTablet: below, sidebarCollapsed: false, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined, openSearch: () => searches.push("open"), openPersonalInvitation: (trigger: HTMLElement) => invitationTriggers.push(trigger) };
  let api: ReturnType<typeof useBusiness> | null = null;
  function TopBar() {
    const workspace = useChatWorkspace();
    return (
      <header data-testid="top-bar">
        {below ? null : workspace?.headerSearch?.(shell as never)}
        {workspace?.headerActions?.(shell as never)}
      </header>
    );
  }
  function Probe() {
    api = useBusiness();
    return <div data-testid="screen"><BusinessPanel /></div>;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const tree = (
    <I18nextProvider i18n={i18n}>
      <BusinessConsentTestProvider accepted>
        <BusinessWorkspaceProvider source={source as BusinessDataSource}>
          <TopBar />
          {renderPanel ? <Probe /> : null}
        </BusinessWorkspaceProvider>
      </BusinessConsentTestProvider>
    </I18nextProvider>
  );
  await act(async () => root.render(tree));
  let mounted = true;
  const unmount = async () => { if (mounted) { mounted = false; await act(async () => root.unmount()); } };
  unmounts.push(unmount);
  const wait = (ms: number) => act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });
  const settle = async (done: () => boolean, what: string) => {
    for (let i = 0; i < 80; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      if (done()) return;
    }
    throw new Error(`timed out waiting for ${what}: ${document.body.textContent?.slice(0, 300)}`);
  };
  const bar = () => host.querySelector<HTMLElement>('[data-testid="top-bar"]')!;
  const screen = () => host.querySelector<HTMLElement>('[data-testid="screen"]')!;
  // The forwarding address is read once the chosen Business is known; the sample answers after 240 ms.
  const ready = async () => { await settle(() => api?.chosen != null && api.records.overview !== null, "the chosen Business"); await wait(400); };
  const open = async (panel: BusinessPanelState) => { await act(async () => api!.openPanel(panel)); };
  const menuItems = () => [...document.querySelectorAll<HTMLButtonElement>('[role="menu"] [role="menuitem"]')];
  const openMenu = async (within: ParentNode) => {
    await act(async () => within.querySelector<HTMLButtonElement>('[data-testid="add-menu-more"]')!.click());
    return menuItems();
  };
  const openReceptionMenu = async () => {
    await act(async () => document.querySelector<HTMLButtonElement>('[data-testid="reception-add"] button[aria-haspopup="menu"]')!.click());
    return menuItems();
  };
  return { act, wait, ready, host, bar, screen, settle, open, openMenu, openReceptionMenu, menuItems, searches, invitationTriggers, unmount, api: () => api! };
}

describe("the Business top bar on a desktop", () => {
  test("Home greets the signed-in person, shows today's date, and places search before the eye", async () => {
    const page = await mount();
    const search = page.bar().querySelector<HTMLButtonElement>('[data-testid="header-search"]')!;
    assert.ok(search, "the top bar carries the search field");
    assert.equal(search.querySelector("span")?.textContent, "Busca comercio, monto o nota");
    assert.equal(search.getAttribute("aria-label"), "Busca comercio, monto o nota", "named even when the bar is narrow and only the icon shows");
    await page.act(async () => search.click());
    assert.deepEqual(page.searches, ["open"]);
    const order = [...page.bar().querySelectorAll("[data-testid]")].map((node) => node.getAttribute("data-testid")).filter((id) => ["header-search", "add-menu-header", "amounts-toggle"].includes(id!));
    assert.deepEqual(order, ["header-search", "amounts-toggle"]);
    const greeting = page.bar().querySelector("h1")!;
    assert.match(greeting.querySelector(".sr-only")?.textContent ?? greeting.textContent ?? "", /^(Buenos días|Buenas tardes|Buenas noches|Noche de enfoque), Ana$/);
    assert.ok(page.bar().querySelector("time")?.getAttribute("datetime"));
    assert.equal(page.screen().querySelector("#business-overview-title"), null, "no duplicate desktop greeting");
  });

  test("the owner's Agregar opens the upload, and its menu offers Exportar registros and Copiar dirección de reenvío", async () => {
    const page = await mount();
    await page.ready();
    const menu = page.screen().querySelector('[data-testid="add-menu-header"]')!;
    const add = menu.querySelector<HTMLButtonElement>('[data-testid="business-primary-upload"]')!;
    assert.equal(add.textContent, "Agregar");
    await page.ready();
    assert.deepEqual((await page.openMenu(menu)).map((item) => item.textContent), ["Exportar registros", "Copiar dirección de reenvío"]);
    const copied: string[] = [];
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async (value: string) => { copied.push(value); } } });
    await page.act(async () => page.menuItems()[1].click());
    assert.equal(copied.length, 1);
    assert.match(copied[0], /@/);
    await page.act(async () => add.click());
    await page.settle(() => (document.body.textContent ?? "").includes("Elegir archivos"), "the upload sheet");
  });

  test("a copy the browser refuses opens Negocio, Correo de recibos, where the address is, and shows no toast", async () => {
    const page = await mount();
    await page.ready();
    const menu = page.screen().querySelector('[data-testid="add-menu-header"]')!;
    await page.ready();
    await page.openMenu(menu);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async () => { throw new Error("refused"); } } });
    document.execCommand = () => false;
    await page.act(async () => page.menuItems()[1].click());
    await page.settle(() => (page.api().panel as { tab?: string }).tab === "correo", "Correo de recibos");
    assert.deepEqual(page.api().panel, { kind: "business", tab: "correo" });
    assert.equal(document.querySelector('[data-testid="toast"]'), null, "a failed copy is not a toast");
  });

  test("an owner without a forwarding address gets no Copiar dirección", async () => {
    const page = await mount({ overrides: { emailIntake: async () => ({ enabled: false, receiving_address: null }) as never } });
    await page.ready();
    assert.deepEqual((await page.openMenu(page.screen())).map((item) => item.textContent), ["Exportar registros"]);
  });

  test("a contador gets the menu alone, with no Agregar and no copy of the owner's address", async () => {
    const page = await mount({ grant: "fixture-grant-client" });
    await page.settle(() => page.api().chosen?.role === "accountant", "the client business");
    const menu = page.screen().querySelector('[data-testid="add-menu-header"]')!;
    assert.equal(menu.querySelector('[data-testid="business-primary-upload"]'), null);
    const trigger = menu.querySelector<HTMLButtonElement>('[data-testid="add-menu-more"]')!;
    assert.equal(trigger.getAttribute("aria-haspopup"), "menu");
    assert.ok(trigger.textContent?.trim(), "the lone trigger names itself");
    assert.deepEqual((await page.openMenu(menu)).map((item) => item.textContent), ["Exportar registros"]);
  });

  test("a Viewer, whose grant lacks the export permission, gets no menu trigger at all", async () => {
    const viewer = { space_id: "fixture-client", name: "Colmado Peña", grant_id: "fixture-grant-client", role: "accountant" as const, business_role: "viewer" as const, permissions: ["read" as const], capabilities: ["read" as const], access_seen: true };
    const page = await mount({ grant: "fixture-grant-client", overrides: { spaces: async () => [viewer] } });
    await page.settle(() => page.api().chosen?.business_role === "viewer", "the viewer business");
    await page.wait(400);
    assert.equal(page.screen().querySelector('[data-testid="add-menu-header"]'), null);
    assert.equal(document.querySelector('[data-testid="add-menu-more"]'), null);
    assert.equal(document.body.textContent?.includes("Exportar registros"), false);
  });

  test("on a phone, a Viewer's Inicio has no empty action band, and an owner's keeps its menu", async () => {
    const viewer = { space_id: "fixture-client", name: "Colmado Peña", grant_id: "fixture-grant-client", role: "accountant" as const, business_role: "viewer" as const, permissions: ["read" as const], capabilities: ["read" as const], access_seen: true };
    const page = await mount({ width: 390, grant: "fixture-grant-client", overrides: { spaces: async () => [viewer] } });
    await page.settle(() => page.api().chosen?.business_role === "viewer", "the viewer business");
    await page.wait(400);
    const band = page.screen().querySelector<HTMLElement>('[data-testid="inicio-actions"]');
    assert.ok(band === null || (band.childElementCount === 0 && band.classList.contains("empty:hidden")), "an empty band is hidden, not padded");
    const owner = await mount({ width: 390 });
    await owner.ready();
    const ownerBand = owner.screen().querySelector<HTMLElement>('[data-testid="inicio-actions"]');
    assert.ok(ownerBand?.querySelector('[data-testid="add-menu-page"]'), "an owner's band holds the menu");
  });

  for (const kind of ["overview", "inbox", "transactions"] as const) test(`Exportar registros from the menu opens the one export sheet over ${kind}`, async () => {
    const page = await mount();
    await page.ready();
    await page.open({ kind });
    assert.equal(document.querySelector('[data-testid="export-records-panel"]'), null);
    const items = kind === "inbox" ? await page.openReceptionMenu() : await page.openMenu(page.screen());
    const exportItem = items.find((item) => item.textContent === "Exportar registros")!;
    await page.act(async () => exportItem.click());
    await page.settle(() => document.querySelector('[data-testid="export-records-panel"]') !== null, "the export sheet");
    assert.equal(page.api().panel.kind, kind, "the screen underneath stays");
    assert.equal(document.querySelectorAll('[data-testid="export-records-panel"]').length, 1);
  });

  test("Agregar belongs to each content heading but Negocio's, while the search field belongs only to Home", async () => {
    const page = await mount();
    await page.ready();
    await page.open({ kind: "business" });
    await page.settle(() => page.api().panel.kind === "business", "business");
    assert.equal(page.screen().querySelector('[data-testid="add-menu-header"]'), null, "adding documents is not a Negocio task");
    for (const kind of ["overview", "inbox", "transactions"] as const) {
      await page.open({ kind });
      await page.settle(() => page.api().panel.kind === kind, kind);
      const owner = kind === "inbox" ? "reception-add" : "add-menu-header";
      const add = page.screen().querySelector<HTMLElement>(`[data-testid="${owner}"] [data-testid="business-primary-upload"]`)!;
      assert.match(add.className, /bg-\[var\(--cuadrao-green\)\]/, kind);
      assert.equal(add.getAttribute("data-primary"), "true", kind);
      assert.match((kind === "inbox" ? page.screen().querySelector('[data-testid="reception-add"] button[aria-haspopup="menu"]') : page.screen().querySelector('[data-testid="add-menu-more"]'))!.className, /bg-\[var\(--cuadrao-green\)\]/, kind);
      assert.equal(page.bar().querySelector('[data-testid="add-menu-header"]'), null);
      assert.equal(Boolean(page.bar().querySelector('[data-testid="header-search"]')), kind === "overview");
      assert.ok(page.bar().querySelector('[data-business-search-anchor]'), "Cmd K keeps its anchor on every screen");
    }
  });

  test("the menu has no Ver correos: an email is how a receipt arrived, not a place", async () => {
    const page = await mount();
    await page.ready();
    const items = (await page.openMenu(page.screen())).map((item) => item.textContent);
    assert.equal(items.includes("Ver correos"), false);
  });
});

describe("Ocultar montos", () => {
  test("the eye flags the page root, survives a remount and a reload of the stored choice, and turns off again", async () => {
    const first = await mount();
    const eye = () => document.querySelector<HTMLButtonElement>('[data-testid="amounts-toggle"]')!;
    assert.equal(eye().getAttribute("aria-pressed"), "false");
    assert.equal(document.documentElement.dataset.amountsHidden, undefined);
    await first.act(async () => eye().click());
    assert.equal(eye().getAttribute("aria-pressed"), "true");
    assert.equal(document.documentElement.dataset.amountsHidden, "true");
    assert.equal(localStorage.getItem(HIDE_KEY), "true");
    await first.unmount();
    delete document.documentElement.dataset.amountsHidden;

    const second = await mount();
    assert.equal(eye().getAttribute("aria-pressed"), "true", "a remount keeps the choice");
    assert.equal(document.documentElement.dataset.amountsHidden, "true", "a remount puts the flag back");
    await second.act(async () => eye().click());
    assert.equal(document.documentElement.dataset.amountsHidden, undefined);
    assert.equal(localStorage.getItem(HIDE_KEY), "false");
  });

  test("amounts on Inicio, the Bandeja, Transacciones and a record's total carry the mark the eye blurs", async () => {
    const page = await mount();
    const marked = () => page.screen().querySelectorAll(".cuadrao-amount").length;
    await page.settle(() => marked() > 0, "Inicio's amounts");
    await page.open({ kind: "inbox" });
    await page.settle(() => page.screen().querySelector('[data-testid="reception-row"]') !== null, "the Bandeja rows");
    await page.act(async () => page.screen().querySelector<HTMLButtonElement>('button[aria-label="Opciones de vista"]')!.click());
    const monto = [...document.querySelectorAll<HTMLLabelElement>("label")].find((label) => label.textContent === "Monto")!;
    await page.act(async () => monto.querySelector("input")!.click());
    await page.settle(() => page.screen().querySelector('[data-testid="reception-amount"].cuadrao-amount') !== null, "the Bandeja's amounts");
    await page.open({ kind: "transactions" });
    await page.settle(() => page.screen().querySelector('[data-testid="transacciones-records"] .cuadrao-amount') !== null, "Transacciones' amounts");
    await page.open({ kind: "receipt", receiptId: "rcpt-ferreteria" });
    await page.settle(() => document.querySelector('[data-testid="receipt-total"]') !== null, "the record total");
    assert.ok(document.querySelector('[data-testid="receipt-total"]')!.classList.contains("cuadrao-amount"));
  });
});

describe("the Business top bar on a phone", () => {
  test("the top bar has no Agregar; Inicio, the Bandeja and Transacciones each start with their own", async () => {
    const page = await mount({ width: 390 });
    assert.equal(page.bar().querySelector('[data-testid="add-menu-header"]'), null);
    assert.ok(page.bar().querySelector('[data-testid="amounts-toggle"]'), "the eye stays");
    const search = page.bar().querySelector<HTMLButtonElement>('[data-testid="business-phone-search"]')!;
    assert.equal(search.getAttribute("aria-label"), "Buscar", "a phone keeps its search icon");
    await page.act(async () => search.click());
    assert.deepEqual(page.searches, ["open"]);
    for (const kind of ["overview", "inbox", "transactions"] as const) {
      await page.open({ kind });
      const selector = kind === "inbox" ? '[data-testid="reception-add"]' : `[data-testid="add-menu-${kind === "overview" ? "page" : "header"}"]`;
      await page.settle(() => page.screen().querySelector(selector) !== null, `${kind}'s Agregar`);
      const menu = page.screen().querySelector(selector)!;
      assert.equal(menu.querySelector('[data-testid="business-primary-upload"]')?.textContent, "Agregar", kind);
      assert.equal(page.screen().querySelectorAll('[data-testid="business-primary-upload"]').length, 1, kind);
    }
  });
});

for (const width of [1280, 390]) {
  test(`personal invitation shortcut is desktop-only at ${width}px`, async () => {
    const previousMode = process.env.NODE_ENV;
    const previousMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
    Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
    try {
      const page = await mount({ width, renderPanel: false });
      const shortcut = page.bar().querySelector<HTMLButtonElement>('[data-testid="personal-invitation-shortcut"]');
      assert.equal(Boolean(shortcut), width >= 720);
      if (shortcut) {
        const actions = [...page.bar().querySelectorAll('[data-testid="personal-invitation-shortcut"], [data-testid="amounts-toggle"]')];
        assert.equal(actions[0], shortcut);
        assert.equal(shortcut.getAttribute("aria-label"), "Invitar a Cuadrao");
        await page.act(async () => shortcut.click());
        assert.deepEqual(page.invitationTriggers, [shortcut]);
      }
      await page.unmount();
    } finally {
      Object.assign(process.env, { NODE_ENV: previousMode });
      if (previousMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
      else process.env.NEXT_PUBLIC_MOCK_AUTH = previousMock;
    }
  });
}

test("personal invitation shortcut stays hidden outside mock auth", async () => {
  const previousMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  try {
    const page = await mount();
    assert.equal(page.bar().querySelector('[data-testid="personal-invitation-shortcut"]'), null);
  } finally {
    if (previousMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = previousMock;
  }
});
