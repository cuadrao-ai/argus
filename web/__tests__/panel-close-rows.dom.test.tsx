import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { keepOwnListSearch } from "./fixtures/own-list-search";

/**
 * A row beside an open tray does its own job: a click anywhere on it swaps the record instead of
 * closing the tray, because the row is a control the tray can recognize. A click on the page itself
 * still closes the tray.
 */

await keepOwnListSearch();

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz?view=invoicing&invoicePreview=seeded" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mountInvoicing() {
  (window as unknown as { happyDOM: { setWindowSize: (size: { width: number; height: number }) => void } }).happyDOM.setWindowSize({ width: 1440, height: 900 });
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18next = (await import("i18next")).default;
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { default: InvoicingPreview } = await import("@/components/business-app/invoicing/InvoicingPreview");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={{ chosen: { space_id: crypto.randomUUID(), name: "Ferretería La Esquina" }, openPanel: () => undefined } as unknown as BusinessContextValue}><InvoicingPreview /></BusinessContext.Provider></I18nextProvider>);
  });
  const row = (reference: string) => [...document.querySelectorAll<HTMLTableRowElement>("table tbody tr")].find((item) => item.querySelector("td")?.textContent === reference)!;
  const tray = () => document.querySelector<HTMLElement>('[data-testid="side-drawer"]');
  const press = async (target: Element) => {
    await act(async () => {
      target.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, cancelable: true, button: 0 }));
      target.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
    });
  };
  const key = async (target: Element, name: string) => {
    await act(async () => { target.dispatchEvent(new KeyboardEvent("keydown", { key: name, bubbles: true, cancelable: true })); });
  };
  return { act, row, tray, press, key, unmount: async () => { await act(async () => root.unmount()); host.remove(); } };
}

test("Facturación: a click on another invoice's cell swaps the dossier, and a click on the page beside it closes it", async () => {
  const page = await mountInvoicing();
  try {
    await page.press(page.row("M-001").querySelectorAll("td")[1]);
    assert.ok(page.tray()?.textContent?.includes("Taller Brisa"), "a click on a row's customer cell opens its dossier");
    await page.press(page.row("M-002").querySelectorAll("td")[2]);
    assert.ok(page.tray()?.textContent?.includes("Colmado Aurora"), "a click on another row's date cell swaps the dossier");
    assert.equal(page.row("M-002").dataset.selected, "true");
    await page.press(document.querySelector('[data-testid="invoice-results-summary"]')!);
    assert.equal(page.tray(), null, "a click on the page beside it closes it");
  } finally {
    await page.unmount();
  }
});

test("Facturación: a focused invoice row opens its dossier on Enter", async () => {
  const page = await mountInvoicing();
  try {
    const row = page.row("M-003");
    row.focus();
    assert.equal(document.activeElement, row, "the row takes focus");
    await page.key(row, "Enter");
    assert.ok(page.tray()?.textContent?.includes("Estudio Palma"), "Enter opens the row's dossier");
  } finally {
    await page.unmount();
  }
});
