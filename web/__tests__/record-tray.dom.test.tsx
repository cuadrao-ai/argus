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
  const recordTitle = () => tray()?.querySelector("#receipt-review-title")?.textContent ?? null;
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

/** A press on the page beside the tray: pointerdown, then the click where it lands. */
async function pressBeside(page: Page, target: Element) {
  await page.act(async () => {
    target.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, cancelable: true, button: 0 }));
    target.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
  });
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

  test("beside the Bandeja the dossier is wide with the document beside its tabs, the size button narrows it, and the approve actions sit in the pinned footer", async () => {
    const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
    const page = await mount();
    await openInbox(page);
    await page.open({ kind: "draft", draftId: dossierFixtureIds.ready, list: "inbox" });
    await page.settle(() => page.tray()?.querySelector('[data-footer-slot] [data-testid="receipt-review-footer"]') != null, "the footer in the drawer slot");
    const review = () => page.tray()!.querySelector('[data-testid="business-record-review"]')!;
    const source = () => review().querySelector('[data-testid="receipt-review-source"]');
    assert.equal(page.tray()!.getAttribute("data-width"), "dossier");
    assert.equal(review().getAttribute("data-size"), "regular");
    const order = [...review().querySelectorAll("[data-testid^='receipt-review-']")].map((item) => item.getAttribute("data-testid"));
    assert.deepEqual(order, ["receipt-review-fields", "receipt-review-history", "receipt-review-source"], "the tabs first, the document beside them");
    assert.equal(source()?.closest("[role='tabpanel']"), null, "the document is not a tab");
    assert.equal(review().querySelector('[data-testid="receipt-review-footer"]'), null, "no in-page sticky footer");
    const footer = page.tray()!.querySelector('[data-footer-slot]')!;
    assert.ok([...footer.querySelectorAll("button")].some((button) => button.textContent === "Aceptar"), "Aceptar is in the pinned footer");

    await page.click(page.tray()!.querySelector<HTMLElement>('[data-testid="dossier-size"]'));
    assert.equal(page.tray()!.getAttribute("data-width"), "record", "the size button narrows the drawer");
    assert.equal(review().getAttribute("data-size"), "narrow");
    assert.equal(source()?.closest("[role='tabpanel']")?.getAttribute("data-tab-panel"), "documento", "narrow, the document is the Documento tab");
    await page.click(page.tray()!.querySelector<HTMLElement>('[data-testid="dossier-size"]'));
    assert.equal(page.tray()!.getAttribute("data-width"), "dossier", "and widens it again");
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
    const panel = page.panel();
    assert.ok(panel.kind === "receipt");
    assert.deepEqual({ kind: panel.kind, receiptId: panel.receiptId, list: panel.list }, { kind: "receipt", receiptId: "rcpt-papeleria", list: "inbox" });
    assert.equal(panel.reviewList?.scope, "inbox");
    assert.ok(panel.reviewList.receiptIds.includes("rcpt-papeleria"));
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

  test("an Escape the page claims stays with the page; an unclaimed one beside the tray closes it", async () => {
    const page = await mount();
    await openInbox(page);
    await openRow(page, "Ferretería La Esquina");
    const listButton = page.action("Papelería Central")!;
    listButton.focus();
    listButton.addEventListener("keydown", (event) => event.preventDefault(), { once: true });
    await page.act(async () => { listButton.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })); });
    assert.ok(page.tray(), "the tray is still open");
    await page.act(async () => { listButton.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })); });
    await page.settle(() => page.tray() === null, "the tray to close");
    assert.deepEqual(page.panel(), { kind: "inbox" });
  });

  test("Bandeja: a click on the page beside the dossier closes it, with focus on the row", async () => {
    const page = await mount();
    await openInbox(page);
    await openRow(page, "Ferretería La Esquina");
    await pressBeside(page, page.host.querySelector('[data-testid="panel"]')!);
    await page.settle(() => page.tray() === null, "the dossier to close");
    assert.deepEqual(page.panel(), { kind: "inbox" });
    assert.equal(document.activeElement, page.row("Ferretería La Esquina")?.querySelector("button"), "focus is back on the row");
  });

  test("Registros: a click on blank page closes the record, and a click on another row swaps it", async () => {
    const page = await mount();
    await page.open({ kind: "transactions" });
    const saved = (text: string) => [...page.host.querySelectorAll<HTMLElement>("[data-record-id]")].find((item) => item.textContent?.includes(text)) ?? null;
    await page.settle(() => saved("Estación Ruta 3") !== null, "the saved records");
    await page.click(saved("Estación Ruta 3"));
    await page.settle(() => page.recordTitle() === "Estación Ruta 3", "Estación Ruta 3 in the tray");
    const tray = page.tray();
    await pressBeside(page, saved("Nube Hosting")!.querySelector("td")!);
    await page.click(saved("Nube Hosting"));
    await page.settle(() => page.tray()?.querySelector('[data-testid="business-record-review"]') != null, "the receipt in the tray");
    assert.equal(page.tray(), tray, "the row swapped the record in the same tray");
    await pressBeside(page, page.host.querySelector('[data-testid="panel"]')!);
    await page.settle(() => page.tray() === null, "the record to close");
    assert.deepEqual(page.panel(), { kind: "transactions" });
    assert.equal(document.activeElement, saved("Nube Hosting"), "focus is back on the row");
  });

  test("an unsaved edit in the dossier asks before a click beside it or Escape closes it, and keeping it stays", async () => {
    const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
    const page = await mount();
    await openInbox(page);
    await page.open({ kind: "draft", draftId: dossierFixtureIds.fiscal, list: "inbox" });
    await page.settle(() => page.tray()?.querySelector('[data-fact="counterparty"] button') != null, "the dossier rows");
    await page.click(page.tray()!.querySelector<HTMLElement>('[data-fact="counterparty"] button'));
    const input = page.tray()!.querySelector<HTMLInputElement>('[data-testid="edit-counterparty"] input')!;
    await page.act(async () => {
      input.focus();
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "Otro nombre");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const dialog = () => document.querySelector<HTMLElement>('[role="alertdialog"]');
    await pressBeside(page, page.host.querySelector('[data-testid="panel"]')!);
    assert.ok(dialog()?.textContent?.includes("¿Descartar los cambios?"), "a click beside it asks");
    await page.click([...dialog()!.querySelectorAll("button")].find((button) => button.textContent === "Seguir editando"));
    assert.ok(page.tray(), "keeping the edit keeps the dossier");
    assert.equal(page.tray()!.querySelector<HTMLInputElement>('[data-testid="edit-counterparty"] input')?.value, "Otro nombre", "and what was typed");
    await page.act(async () => { document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })); });
    assert.ok(dialog(), "Escape asks too");
  });

  test("an expense opens beside Transacciones, and the close control returns to Transacciones with focus on its row", async () => {
    const page = await mount();
    await page.open({ kind: "transactions" });
    const saved = (text: string) => [...page.host.querySelectorAll<HTMLElement>("[data-record-id]")].find((item) => item.textContent?.includes(text)) ?? null;
    await page.settle(() => saved("Estación Ruta 3") !== null, "the saved records");
    await page.click(saved("Estación Ruta 3"));
    await page.settle(() => page.recordTitle() === "Estación Ruta 3", "Estación Ruta 3 in the tray");
    assert.equal(page.tray()!.querySelector('[data-testid="business-record-review"]')?.getAttribute("data-presentation"), "tray", "a record with no draft opens the one dossier");
    assert.equal(page.tray()!.querySelector('[data-testid="receipt-review-footer"]'), null, "with nothing to act on");
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

  test("an approved Bandeja row opens beside the Bandeja, and closing returns to the Bandeja with focus on its row", async () => {
    const page = await mount();
    await openInbox(page);
    await page.settle(() => page.row("Nube Hosting") !== null, "the approved row");
    await openRow(page, "Nube Hosting");
    const panel = page.panel();
    assert.ok(panel.kind === "receipt");
    assert.deepEqual({ receiptId: panel.receiptId, list: panel.list }, { receiptId: "rcpt-confirmed", list: "inbox" });
    assert.ok(page.host.querySelector('[data-testid="reception-preview"]'), "the Bandeja list is still on the page");
    assert.equal(page.host.querySelector("[data-record-id]"), null, "Registros is not drawn under the tray");
    assert.equal(page.row("Nube Hosting")?.getAttribute("aria-current"), "true");
    assert.equal(page.host.querySelector('[data-testid="sidebar"] [aria-current="page"]')?.textContent?.includes("Bandeja"), true, "the sidebar marks the Bandeja");
    await page.click(page.tray()!.querySelector<HTMLElement>('button[aria-label="Cerrar"]'));
    await page.settle(() => page.tray() === null, "the tray to close");
    assert.deepEqual(page.panel(), { kind: "inbox" });
    assert.equal(document.activeElement, page.row("Nube Hosting")?.querySelector("button"), "focus is back on the row");
    assert.equal(page.host.querySelector('[data-testid="sidebar"] [aria-current="page"]')?.textContent?.includes("Bandeja"), true);
  });

  test("a link to a saved expense opens its receipt beside Transacciones, and closing returns to Transacciones", async () => {
    const page = await mount();
    await page.open({ kind: "expense", expenseId: "exp-hosting" });
    await page.settle(() => page.recordTitle() === "Nube Hosting" && page.host.querySelector('[data-record-id="exp-hosting"]') !== null, "the receipt beside Registros");
    assert.deepEqual(page.panel(), { kind: "receipt", receiptId: "rcpt-confirmed", list: "transactions" });
    assert.equal(page.host.querySelector('[data-testid="sidebar"] [aria-current="page"]')?.textContent?.includes("Registros"), true);
    await page.click(page.tray()!.querySelector<HTMLElement>('button[aria-label="Cerrar"]'));
    await page.settle(() => page.tray() === null, "the tray to close");
    assert.deepEqual(page.panel(), { kind: "transactions" });
  });

  test("a link to a recorded receipt draws only the tray until it has loaded, then Transacciones beside it, never the Bandeja", async () => {
    const page = await mount();
    const lists: string[] = [];
    const seen = new WeakSet<Element>();
    const record = () => {
      for (const list of page.host.querySelectorAll('[data-testid="reception-preview"], [data-testid="transacciones"]')) {
        if (!seen.has(list)) { seen.add(list); lists.push(list.getAttribute("data-testid")!); }
      }
    };
    const observer = new MutationObserver(record);
    observer.observe(page.host, { subtree: true, childList: true });
    await page.open({ kind: "receipt", receiptId: "rcpt-confirmed" });
    assert.ok(page.tray(), "the tray opens at once");
    assert.equal(page.host.querySelector('[data-testid="reception-preview"], [data-testid="transacciones"]'), null, "no list is drawn before the receipt says which");
    await page.settle(() => page.host.querySelector('[data-record-id="exp-hosting"]') !== null, "the list beside the receipt");
    record();
    observer.disconnect();
    assert.deepEqual(page.panel(), { kind: "receipt", receiptId: "rcpt-confirmed", list: "transactions" });
    assert.equal(page.recordTitle(), "Nube Hosting");
    assert.deepEqual(lists, ["transacciones"]);
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

  test("Registros keeps its narrower tray beside a live list, for an expense and for a receipt behind one", async () => {
    const page = await mount();
    await page.open({ kind: "transactions" });
    const saved = (text: string) => [...page.host.querySelectorAll<HTMLElement>("[data-record-id]")].find((item) => item.textContent?.includes(text)) ?? null;
    await page.settle(() => saved("Estación Ruta 3") !== null, "the saved records");
    await page.click(saved("Estación Ruta 3"));
    await page.settle(() => page.recordTitle() === "Estación Ruta 3", "Estación Ruta 3 in the tray");
    assert.equal(page.tray()!.getAttribute("data-width"), "record");
    assert.equal(covered(page), null, "the list beside the expense stays in the Tab order");
    await page.click(saved("Nube Hosting"));
    await page.settle(() => page.tray()?.querySelector('[data-testid="business-record-review"]') != null, "the receipt in the tray");
    assert.equal(page.tray()!.getAttribute("data-width"), "record");
    assert.equal(covered(page), null, "the list beside the receipt stays in the Tab order");
  });

  test("Tab past either end of the dossier wraps inside it, and a Tab from outside it is not held", async () => {
    const page = await mount();
    await openInbox(page);
    await openRow(page, "Ferretería La Esquina");
    const tray = page.tray()!;
    const stops = [...tray.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])')];
    const press = async (target: HTMLElement, shiftKey: boolean) => {
      const event = new KeyboardEvent("keydown", { key: "Tab", shiftKey, bubbles: true, cancelable: true });
      await page.act(async () => { target.dispatchEvent(event); });
      return event.defaultPrevented;
    };
    assert.ok(stops.length > 2, "the dossier has controls to wrap between");
    stops[stops.length - 1].focus();
    assert.equal(await press(stops[stops.length - 1], false), true);
    assert.equal(document.activeElement, stops[0], "Tab from the last control lands on the first");
    assert.equal(await press(stops[0], true), true);
    assert.equal(document.activeElement, stops[stops.length - 1], "Shift+Tab from the first lands on the last");
    stops[1].focus();
    assert.equal(await press(stops[1], false), false, "inside the dossier the browser keeps its own order");
    const outside = page.action("Papelería Central")!;
    assert.equal(await press(outside, false), false, "a key from outside the dossier is not held");
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
