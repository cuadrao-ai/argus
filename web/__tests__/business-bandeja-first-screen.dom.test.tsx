import { withReceiptReading } from "./support/receipt-reading";
import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
import type { GrantedSpace, ReceiptReading } from "@/lib/business-api";
import type { BusinessDataSource } from "@/components/business-app/business-data";

let search = "";
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push() {}, replace() {} }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

const PHRASE = "Nada aquí es un gasto hasta que lo confirmes.";

const reading = (enabled: boolean): ReceiptReading => ({
  scope_version: 1,
  enabled,
  available: true,
  can_change: true,
  disclosure: "Permiso de prueba",
  disclosure_token: "a".repeat(64),
  route: null,
  consented_at: null,
  revoked_at: null,
});

// A desktop shell's top bar, which holds the one Agregar on every Business screen but Negocio.
const DESKTOP_SHELL = { currentView: "workspace", conversationId: null, isBelowTablet: false, sidebarCollapsed: false, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined, openSearch: undefined };

async function mountInbox(overrides: Partial<BusinessDataSource> = {}, { bar = false }: { bar?: boolean } = {}) {
  search = bar ? "view=inbox" : "";
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { setChosenGrant } = await import("@/lib/business-grant");
  const BusinessInboxPanel = (await import("@/components/business-app/BusinessInboxPanel")).default;
  const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
  setChosenGrant(null);
  function ReadyInbox() {
    return useBusiness().inboxReady ? <BusinessInboxPanel /> : null;
  }
  function Bar() {
    const workspace = useChatWorkspace();
    return <header data-testid="top-bar">{workspace?.headerSearch?.(DESKTOP_SHELL as never)}</header>;
  }
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const source = { ...createFixtureBusinessDataSource({ chatAvailable: false }), ...overrides };
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as BusinessDataSource}>
            {bar ? <Bar /> : null}
            <ReadyInbox />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 40; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
      if (done()) return;
    }
    assert.fail("the inbox did not settle");
  };
  const close = () => act(async () => { root.unmount(); host.remove(); search = ""; });
  return { act, host, settle, close };
}

function ownText(element: Element) {
  return [...element.childNodes].filter((node) => node.nodeType === 3).map((node) => node.textContent ?? "").join("");
}

for (const enabled of [false, true]) test(`reading ${enabled ? "on" : "off"}: the loading list keeps its place when the notice settles`, async () => {
  const fixture = (await import("@/components/business-app/fixture-data")).createFixtureBusinessDataSource();
  let releaseList!: () => void;
  let releaseReading!: () => void;
  const listGate = new Promise<void>(resolve => { releaseList = resolve; });
  const readingGate = new Promise<void>(resolve => { releaseReading = resolve; });
  let separateReads = 0;
  const page = await mountInbox({
    workspace: async () => ({ ...await fixture.workspace(), receipt_reading: reading(enabled) }),
    receiptPage: async (view, signal) => { if (view === "all") await listGate; return fixture.receiptPage!(view, signal); },
    ...{ receiptReading: async () => { separateReads++; await readingGate; return reading(enabled); } },
  });
  const beforeList = () => {
    const list = page.host.querySelector("#reception-list")!;
    return [...list.parentElement!.children].slice(0, [...list.parentElement!.children].indexOf(list))
      .map(node => node.getAttribute("data-testid") ?? node.getAttribute("data-surface-block"));
  };
  try {
    await page.settle(() => page.host.querySelector('[data-testid="reception-pending"]') !== null);
    const loading = beforeList();
    const reserved = page.host.querySelector<HTMLElement>('[data-testid="receipt-reading-control"]');
    if (!enabled) assert.equal(reserved?.style.visibility, "hidden", "the pending notice holds its geometry without offering an action");
    await page.act(async () => { releaseList(); });
    await page.settle(() => page.host.querySelector('[data-testid="reception-row"]') !== null);
    const loaded = beforeList();
    await page.act(async () => { releaseReading(); });
    assert.deepEqual(beforeList(), loaded, "a delayed reading response must not insert a block and push the list down");
    assert.deepEqual(loaded, loading, "the loading view reserves exactly the final notice space");
    assert.equal(reserved !== null, !enabled, "only a Business with reading off reserves the notice");
    assert.equal(separateReads, 0, "the workspace answer is the only reading-setting read");
  } finally { releaseList(); releaseReading(); await page.close(); }
});

test("a turned-on reading stays off the first screen, and a turned-off reading still explains how to turn it on", async () => {
  const on = await mountInbox(withReceiptReading(reading(true)));
  try {
    await on.settle(() => on.host.querySelector('[data-testid="reception-row"]') !== null);
    assert.equal(on.host.querySelector('[data-testid="receipt-reading-control"]'), null);
    assert.equal(on.host.textContent?.includes("La lectura de documentos está activada."), false);
  } finally { await on.close(); }

  const off = await mountInbox(withReceiptReading(reading(false)));
  try {
    await off.settle(() => off.host.querySelector('[data-testid="receipt-reading-control"]') !== null);
    assert.equal(off.host.querySelector('[data-testid="receipt-reading-control"]')?.textContent?.includes("Activar lectura de documentos"), true);
  } finally { await off.close(); }
});

test("reading off is one line under the title with an outlined action; the words agreed to and the switch live in Lectura de documentos", async () => {
  const turnedOn: boolean[] = [];
  const server = withReceiptReading(reading(false));
  const off = await mountInbox({
    ...server,
    setReceiptReading: async (current, enabled) => { turnedOn.push(enabled); return server.setReceiptReading!(current, enabled, "es-419"); },
  });
  try {
    await off.settle(() => off.host.querySelector('[data-testid="receipt-reading-control"]') !== null);
    const notice = off.host.querySelector('[data-testid="receipt-reading-control"]')!;
    const tabs = off.host.querySelector('[role="tablist"]')!;
    assert.ok(tabs.compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING, "the notice sits under the views");
    assert.deepEqual([...notice.querySelectorAll("p")].map((line) => line.textContent), ["Tus documentos están guardados sin leer. Activa la lectura para prepararlos para revisión."]);
    assert.equal(off.host.textContent?.includes("Permiso de prueba"), false, "the consent words are not repeated on the page");
    const action = notice.querySelector("button")!;
    assert.equal(action.textContent, "Activar lectura de documentos");
    assert.ok(action.className.includes("border") && !action.className.includes("bg-[var(--cuadrao-green)]"), "secondary, not the page's primary");
    await off.act(async () => action.click());
    const sheet = document.querySelector('[data-testid="receipt-reading-sheet"]')!;
    assert.ok(sheet.textContent?.includes("Permiso de prueba"));
    const toggle = sheet.querySelector<HTMLButtonElement>('[role="switch"]')!;
    assert.equal(toggle.getAttribute("aria-checked"), "false");
    await off.act(async () => { toggle.click(); await Promise.resolve(); });
    await off.settle(() => off.host.querySelector('[data-testid="receipt-reading-control"]') === null);
    assert.deepEqual(turnedOn, [true]);
    assert.equal(document.querySelector('[data-testid="receipt-reading-sheet"]'), null);
  } finally { await off.close(); }
});

test("a reading setting that did not load claims nothing", async () => {
  const unknown = await mountInbox(withReceiptReading(null));
  try {
    await unknown.settle(() => unknown.host.querySelector('[role="tablist"]') !== null);
    assert.equal(unknown.host.querySelector('[data-testid="receipt-reading-control"]'), null);
    assert.equal(unknown.host.textContent?.includes("sin leer"), false);
  } finally { await unknown.close(); }
});

test("Bandeja shows one Agregar, no subhead or page duplicate, and Reception's views", async () => {
  const page = await mountInbox({}, { bar: true });
  try {
    await page.settle(() => page.host.querySelector('[data-testid="reception-row"]') !== null);
    assert.equal([...page.host.querySelectorAll("p")].some((node) => ownText(node).includes(PHRASE)), false, "the counts live on the views, not in a subhead");
    const views = [...page.host.querySelectorAll<HTMLButtonElement>('[role="tablist"] [role="tab"]')];
    assert.deepEqual(views.map((view) => view.id), ["reception-tab-all", "reception-tab-attention", "reception-tab-listos", "reception-tab-eliminados"]);
    assert.equal(document.querySelector('[data-testid="email-address"]'), null, "the receiving address lives in Negocio");
    assert.equal(page.host.querySelectorAll('[data-testid="top-bar"] [data-testid="add-menu-header"] [data-testid="business-primary-upload"]').length, 1, "the top bar owns Agregar");
    assert.equal(page.host.querySelectorAll('[data-testid="reception-add"] [data-testid="business-primary-upload"]').length, 0, "the toolbar does not repeat it");
    assert.equal(page.host.querySelectorAll('[data-testid="business-primary-upload"]').length, 1, "Agregar is not duplicated");
    assert.equal(page.host.querySelectorAll('[data-testid="add-menu-page"]').length, 0);
  } finally { await page.close(); }
});

test("Entendido hides the access line after a reload, and only for that person and business", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessContextCue } = await import("@/components/business-app/BusinessPanel");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { setChosenGrant } = await import("@/lib/business-grant");
  const seen = new Map<string, Set<string>>();
  const fixture = createFixtureBusinessDataSource();
  const sourceFor = (owner: string) => {
    const spaces = async () => ["one", "two"].map((business): GrantedSpace => ({
      space_id: business,
      name: business === "one" ? "Colmado Peña" : "Taller Brito",
      grant_id: `${owner}-${business}`,
      role: "accountant",
      capabilities: ["read", "prepare"],
      access_seen: seen.get(owner)?.has(business) ?? false,
    }));
    return {
      ...fixture,
      spaces,
      spaceDirectory: async () => ({ spaces: await spaces(), closed_spaces: [], invitations_available: true }),
      markAccessSeen: async (grant: string) => {
        const business = grant.slice(owner.length + 1);
        const items = seen.get(owner) ?? new Set<string>();
        items.add(business);
        seen.set(owner, items);
      },
    };
  };
  const sources = { a: sourceFor("a"), b: sourceFor("b") };
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  let generation = 0;
  const render = async (owner: "a" | "b", business = "one") => {
    setChosenGrant(`${owner}-${business}`);
    await act(async () => {
      root.render(
        <I18nextProvider i18n={i18n}>
          <BusinessWorkspaceProvider key={`${owner}-${business}-${generation++}`} source={sources[owner] as BusinessDataSource}>
            <BusinessContextCue />
          </BusinessWorkspaceProvider>
        </I18nextProvider>,
      );
    });
    await act(async () => { await new Promise((done) => setTimeout(done, 300)); });
  };
  const banner = () => host.querySelector('[data-testid="business-access-line"]');
  try {
    await render("a");
    assert.equal(banner()?.textContent?.includes("Ahora tienes acceso a Colmado Peña"), true);
    assert.equal(banner()?.querySelector("button")?.textContent, "Entendido");
    await act(async () => { banner()?.querySelector("button")?.click(); });
    await act(async () => { await new Promise((done) => setTimeout(done, 300)); });
    assert.equal(banner(), null);
    await render("a", "one");
    assert.equal(banner(), null);
    await render("a", "two");
    assert.equal(banner()?.textContent?.includes("Ahora tienes acceso a Taller Brito"), true);
    await render("b", "one");
    assert.equal(banner()?.textContent?.includes("Ahora tienes acceso a Colmado Peña"), true);
  } finally {
    await act(async () => { root.unmount(); });
    host.remove();
    setChosenGrant(null);
  }
});

test("a failed Entendido leaves the access line up", async () => {
  const page = await mountCueThatFails();
  try {
    assert.equal(page.banner()?.textContent?.includes("Entendido"), true);
    await page.act(async () => { page.banner()?.querySelector("button")?.click(); });
    await page.act(async () => { await new Promise((done) => setTimeout(done, 50)); });
    assert.ok(page.banner());
  } finally { await page.close(); }
});

async function mountCueThatFails() {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessContextCue } = await import("@/components/business-app/BusinessPanel");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { setChosenGrant } = await import("@/lib/business-grant");
  const fixture = createFixtureBusinessDataSource();
  const spaces = async () => [{ space_id: "one", name: "Colmado Peña", grant_id: "a-one", role: "accountant" as const, capabilities: ["read" as const, "prepare" as const], access_seen: false }];
  const source = {
    ...fixture,
    spaces,
    spaceDirectory: async () => ({ spaces: await spaces(), closed_spaces: [], invitations_available: true }),
    markAccessSeen: async () => { throw new Error("synthetic failure"); },
  };
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  setChosenGrant("a-one");
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const view: ReactNode = (
    <I18nextProvider i18n={i18n}>
      <BusinessWorkspaceProvider source={source as BusinessDataSource}>
        <BusinessContextCue />
      </BusinessWorkspaceProvider>
    </I18nextProvider>
  );
  await act(async () => { root.render(view); });
  await act(async () => { await new Promise((done) => setTimeout(done, 300)); });
  return {
    act,
    banner: () => host.querySelector('[data-testid="business-access-line"]'),
    close: async () => { await act(async () => { root.unmount(); }); host.remove(); setChosenGrant(null); },
  };
}
