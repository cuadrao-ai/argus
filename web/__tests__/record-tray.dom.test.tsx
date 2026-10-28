import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

// The real workspace provider over the fixture source. On a desktop a record
// opens in a tray beside the list it came from; below it the record is the page.
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

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
  document.body.innerHTML = "";
});

async function mount({ width = 1280 }: { width?: number } = {}) {
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
  const BusinessSidebarNav = (await import("@/components/business-app/BusinessSidebarNav")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const source = createFixtureBusinessDataSource({ chatAvailable: true });
  let api: ReturnType<typeof useBusiness> | null = null;
  const shell = { currentView: "workspace" as const, conversationId: null, isBelowTablet: false, sidebarCollapsed: false, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined };
  function Probe() {
    api = useBusiness();
    return (
      <div>
        <div data-testid="sidebar"><BusinessSidebarNav shell={shell} /></div>
        <div data-testid="panel"><BusinessPanel /></div>
      </div>
    );
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source}>
            <Probe />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  unmounts.push(() => act(async () => root.unmount()));
  const settle = async (done: () => boolean, what: string) => {
    for (let i = 0; i < 80; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      if (done()) return;
    }
    throw new Error(`timed out waiting for ${what}: ${document.body.textContent?.slice(0, 300)}`);
  };
  const tray = () => document.querySelector<HTMLElement>('[data-testid="side-drawer"]');
  const recordTitle = () => tray()?.querySelector("#receipt-review-title, #expense-detail-title")?.textContent ?? null;
  const row = (text: string) => [...host.querySelectorAll<HTMLElement>('[data-testid="panel"] li')].find((item) => item.textContent?.includes(text)) ?? null;
  const action = (text: string) => row(text)?.querySelector<HTMLElement>('button[class~="rowAction"]') ?? null;
  const click = async (element: HTMLElement | null | undefined) => {
    assert.ok(element, "the control is on the page");
    await act(async () => element.click());
  };
  return { act, host, settle, tray, recordTitle, row, action, click, panel: () => api!.panel, open: (next: Parameters<typeof api.openPanel>[0]) => act(async () => api!.openPanel(next)) };
}

type Page = Awaited<ReturnType<typeof mount>>;

async function openInbox(page: Page) {
  await page.open({ kind: "inbox" });
  await page.settle(() => page.row("Ferretería La Esquina") !== null && page.row("Papelería Central") !== null, "the Bandeja rows");
}

async function openRow(page: Page, merchant: string) {
  await page.click(page.action(merchant));
  await page.settle(() => page.recordTitle() === merchant, `${merchant} in the tray`);
}

describe("a record in the desktop tray", () => {
  test("a receipt opens beside the Bandeja: the list stays, the row is marked open, and focus moves to the tray title", async () => {
    const page = await mount();
    await openInbox(page);
    await openRow(page, "Ferretería La Esquina");
    const tray = page.tray()!;
    assert.equal(tray.getAttribute("role"), "region", "the tray is a labelled region");
    assert.equal(tray.getAttribute("aria-modal"), null, "the tray is not modal");
    assert.equal(document.querySelector('[data-testid="side-drawer"]')?.parentElement, document.body, "no overlay wraps the tray");
    assert.ok(page.host.querySelector('[data-testid="reception-preview"]'), "the Bandeja list is still on the page");
    assert.equal(page.row("Ferretería La Esquina")?.getAttribute("aria-current"), "true");
    assert.equal(page.row("Papelería Central")?.getAttribute("aria-current"), null);
    assert.equal(document.activeElement, tray.querySelector("h2"), "focus is on the tray title");
    assert.equal(tray.querySelector('[data-testid="business-record-review"]')?.getAttribute("data-presentation"), "tray");
    const backToBandeja = [...tray.querySelectorAll("button")].find((button) => button.textContent === "Bandeja");
    assert.equal(backToBandeja, undefined, "the tray has no way back; its close control returns");
    assert.ok(tray.querySelector('button[aria-label="Cerrar"]'), "the tray has a close control");
    assert.equal(page.host.querySelector('[data-testid="sidebar"] [aria-current="page"]')?.textContent?.includes("Bandeja"), true, "the sidebar marks the Bandeja");
  });

  test("the record sits in one column, source first, and the approve actions sit in the pinned footer", async () => {
    const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
    const page = await mount();
    await openInbox(page);
    await page.open({ kind: "draft", draftId: dossierFixtureIds.ready, list: "inbox" });
    await page.settle(() => page.tray()?.querySelector('[data-footer-slot] [data-testid="receipt-review-footer"]') != null, "the footer in the drawer slot");
    const review = page.tray()!.querySelector('[data-testid="business-record-review"]')!;
    const order = [...review.querySelectorAll("[data-testid^='receipt-review-']")].map((item) => item.getAttribute("data-testid"));
    assert.deepEqual(order, ["receipt-review-source", "receipt-review-fields", "receipt-review-history"]);
    assert.equal(review.querySelector('[data-testid="receipt-review-footer"]'), null, "no in-page sticky footer");
    const footer = page.tray()!.querySelector('[data-footer-slot]')!;
    assert.ok([...footer.querySelectorAll("button")].some((button) => button.textContent === "Aprobar"), "Aprobar is in the pinned footer");
  });

  test("clicking another row swaps the record in the same tray", async () => {
    const page = await mount();
    await openInbox(page);
    await openRow(page, "Ferretería La Esquina");
    const tray = page.tray();
    await openRow(page, "Papelería Central");
    assert.equal(page.tray(), tray, "the tray stays open and is not drawn again");
    assert.equal(page.row("Papelería Central")?.getAttribute("aria-current"), "true");
    assert.equal(page.row("Ferretería La Esquina")?.getAttribute("aria-current"), null);
    assert.deepEqual(page.panel(), { kind: "receipt", receiptId: "rcpt-papeleria", list: "inbox" });
  });

  test("Escape inside the tray closes it, returns to the Bandeja, and puts focus on the row", async () => {
    const page = await mount();
    await openInbox(page);
    await openRow(page, "Ferretería La Esquina");
    const title = page.tray()!.querySelector("h2")!;
    await page.act(async () => { title.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
    await page.settle(() => page.tray() === null, "the tray to close");
    assert.deepEqual(page.panel(), { kind: "inbox" });
    assert.equal(document.activeElement, page.row("Ferretería La Esquina")?.querySelector("button"), "focus is back on the row");
  });

  test("an Escape outside the tray leaves it open: the page keeps its own keys", async () => {
    const page = await mount();
    await openInbox(page);
    await openRow(page, "Ferretería La Esquina");
    const listButton = page.action("Papelería Central")!;
    listButton.focus();
    await page.act(async () => { listButton.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
    assert.ok(page.tray(), "the tray is still open");
  });

  test("an expense opens beside Transacciones, and the close control returns to Transacciones with focus on its row", async () => {
    const page = await mount();
    await page.open({ kind: "transactions" });
    const saved = (text: string) => [...page.host.querySelectorAll<HTMLElement>("[data-record-id]")].find((item) => item.textContent?.includes(text)) ?? null;
    await page.settle(() => saved("Estación Ruta 3") !== null, "the saved records");
    await page.click(saved("Estación Ruta 3"));
    await page.settle(() => page.recordTitle() === "Estación Ruta 3", "Estación Ruta 3 in the tray");
    assert.ok(page.host.querySelector('[data-record-id="exp-gas"]'), "the list is still on the page");
    assert.equal(saved("Estación Ruta 3")?.getAttribute("aria-selected"), "true");
    assert.equal([...page.tray()!.querySelectorAll("button")].find((button) => button.textContent === "Transacciones"), undefined, "no way back inside the tray");
    await page.click(page.tray()!.querySelector<HTMLElement>('button[aria-label="Cerrar"]'));
    await page.settle(() => page.tray() === null, "the tray to close");
    assert.deepEqual(page.panel(), { kind: "transactions" });
    assert.equal(document.activeElement, saved("Estación Ruta 3"));
  });

  test("a receipt opened from Transacciones sits beside it, and the sidebar marks Transacciones", async () => {
    const page = await mount();
    await page.open({ kind: "transactions" });
    const saved = (text: string) => [...page.host.querySelectorAll<HTMLElement>("[data-record-id]")].find((item) => item.textContent?.includes(text)) ?? null;
    await page.settle(() => saved("Nube Hosting") !== null, "the saved records");
    await page.click(saved("Nube Hosting"));
    await page.settle(() => page.tray()?.querySelector('[data-testid="business-record-review"]') != null, "the receipt in the tray");
    assert.deepEqual(page.panel(), { kind: "receipt", receiptId: "rcpt-confirmed", list: "transactions" });
    assert.ok(page.host.querySelector('[data-record-id="exp-hosting"]'), "the list is still on the page");
    assert.equal(saved("Nube Hosting")?.getAttribute("aria-selected"), "true");
    assert.equal(page.host.querySelector('[data-testid="sidebar"] [aria-current="page"]')?.textContent?.includes("Registros"), true);
  });

  test("a link to a recorded receipt opens it beside Transacciones once it has loaded", async () => {
    const page = await mount();
    await page.open({ kind: "receipt", receiptId: "rcpt-confirmed" });
    await page.settle(() => page.host.querySelector('[data-record-id="exp-hosting"]') !== null, "the list beside the receipt");
    assert.deepEqual(page.panel(), { kind: "receipt", receiptId: "rcpt-confirmed", list: "transactions" });
    assert.ok(page.tray());
  });
});

describe("what a dossier tray covers", () => {
  const covered = (page: Page) => page.host.querySelector('[data-testid="reception-preview"], [data-record-id]')?.closest("[inert]") ?? null;

  test("an incoming item opens wide over the Bandeja, whose list leaves the Tab order until it closes", async () => {
    const page = await mount();
    await openInbox(page);
    assert.equal(covered(page), null, "nothing is inert before a dossier opens");
    await openRow(page, "Ferretería La Esquina");
    assert.equal(page.tray()!.getAttribute("data-width"), "dossier");
    assert.ok(covered(page), "the list under the dossier is inert");
    assert.equal(page.tray()!.closest("[inert]"), null, "the dossier itself is not");
    const title = page.tray()!.querySelector("h2")!;
    await page.act(async () => { title.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
    await page.settle(() => page.tray() === null, "the tray to close");
    assert.equal(covered(page), null, "the list is live again");
  });

  test("an expense from Transacciones keeps the narrower tray, with its list beside it and live", async () => {
    const page = await mount();
    await page.open({ kind: "transactions" });
    const saved = (text: string) => [...page.host.querySelectorAll<HTMLElement>("[data-record-id]")].find((item) => item.textContent?.includes(text)) ?? null;
    await page.settle(() => saved("Estación Ruta 3") !== null, "the saved records");
    await page.click(saved("Estación Ruta 3"));
    await page.settle(() => page.recordTitle() === "Estación Ruta 3", "Estación Ruta 3 in the tray");
    assert.equal(page.tray()!.getAttribute("data-width"), "record");
    assert.equal(covered(page), null, "the list beside the expense stays in the Tab order");
  });
});

describe("a record below the desktop stop", () => {
  test("a phone keeps the full page with its way back and no tray", async () => {
    const page = await mount({ width: 390 });
    await openInbox(page);
    await page.click(page.action("Ferretería La Esquina"));
    await page.settle(() => page.host.querySelector("#receipt-review-title")?.textContent === "Ferretería La Esquina", "the receipt page");
    assert.equal(page.tray(), null, "no tray and no bottom sheet");
    assert.equal(page.host.querySelector('[data-testid="reception-preview"]'), null, "the record replaces the list");
    assert.equal(page.host.querySelector('[data-testid="business-record-review"]')?.getAttribute("data-presentation"), "page");
    assert.ok([...page.host.querySelectorAll("button")].some((button) => button.textContent === "Bandeja"), "the way back is on the page");
  });
});
