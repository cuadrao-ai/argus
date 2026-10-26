import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { RecordRow } from "@/components/business-app/transacciones/transacciones-model";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
const cleanups: (() => Promise<void>)[] = [];
afterEach(async () => {
  while (cleanups.length) await cleanups.pop()!();
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
});
const row = (hasProof: boolean | null): RecordRow => ({ id: "exp-hosting", kind: "gasto", occurredOn: "2026-10-25", counterparty: "Sample", money: { amount: "-24.00", currency: "USD" }, categoryId: null, account: null, hasProof, marks: { personal: false, markedBy: null, fiscal: null }, opens: null });

async function mount(width = 1440, records = [row(false)], language = "es-419") {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 844 });
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: language, resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default }, en: { translation: (await import("@/public/locales/en/common.json")).default } } });
  const Summary = (await import("@/components/business-app/transacciones/RecordsResultsSummary")).default;
  const Settings = (await import("@/components/business-app/transacciones/RecordsSettingsPreview")).default;
  const { defaultRecordsPreferences } = await import("@/components/business-app/transacciones/records-view-preferences");
  function Harness() {
    const [preferences, setPreferences] = useState(defaultRecordsPreferences);
    return <><Settings value={preferences} onChange={setPreferences} /><Summary selected={preferences.summary} records={records} businessId="fixture-space" /></>;
  }
  const host = document.createElement("div"); document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<I18nextProvider i18n={i18n}><Harness /></I18nextProvider>); });
  cleanups.push(async () => { await act(async () => root.unmount()); });
  const button = (name: string) => {
    const found = [...document.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.getAttribute("aria-label") === name || item.textContent === name);
    assert.ok(found, `button ${name}`); return found;
  };
  const click = async (element: HTMLElement) => { await act(async () => element.click()); };
  const key = async (element: Element, value: string) => { await act(async () => element.dispatchEvent(new KeyboardEvent("keydown", { key: value, bubbles: true, cancelable: true }))); };
  const toggle = async (metric: string) => { const label = document.querySelector<HTMLElement>(`[data-metric-option="${metric}"] label`); assert.ok(label); await click(label); };
  const cards = () => [...host.querySelectorAll("[data-summary-metric]")].map((item) => item.getAttribute("data-summary-metric"));
  const open = async () => {
    await click(host.querySelector<HTMLButtonElement>('button[aria-haspopup="dialog"]')!);
    if (width >= 1024) await click(button(language === "en" ? "Summary" : "Resumen"));
  };
  return { host, act, button, click, key, toggle, cards, open };
}

test("summary choices apply as one draft, discard on Escape, recover an empty selection", async () => {
  const page = await mount();
  assert.deepEqual(page.cards(), ["sales", "expenses"]);
  assert.equal(page.host.querySelectorAll(".cuadrao-amount").length, 1, "money retains the privacy hook");
  await page.open();
  await page.toggle("sales");
  assert.deepEqual(page.cards(), ["sales", "expenses"], "draft does not alter cards");
  await page.key(document.activeElement!, "Escape");
  assert.equal(document.querySelector('[role="dialog"]'), null);
  await page.open();
  assert.equal(document.querySelector<HTMLInputElement>('[data-metric-option="sales"] input')!.checked, true);
  await page.toggle("sales");
  await page.click(page.button("Aplicar"));
  assert.deepEqual(page.cards(), ["expenses"]);
  await page.open();
  await page.toggle("expenses"); await page.click(page.button("Aplicar"));
  assert.deepEqual(page.cards(), []);
  assert.ok(page.host.querySelector('button[aria-haspopup="dialog"]'));
  await page.open();
  await page.click(page.button("Restaurar valores iniciales"));
  assert.deepEqual(page.cards(), [], "restore edits the draft only");
  await page.click(page.button("Aplicar"));
  assert.deepEqual(page.cards(), ["sales", "expenses"]);
});

test("keyboard reorder remains a draft and Escape first cancels the grabbed order", async () => {
  const page = await mount();
  await page.open();
  const grip = document.querySelector<HTMLButtonElement>('[data-metric-option="expenses"] button[draggable]')!;
  await page.key(grip, " "); await page.key(grip, "ArrowUp");
  assert.deepEqual([...document.querySelectorAll("[data-metric-option]")].slice(0, 2).map((item) => item.getAttribute("data-metric-option")), ["expenses", "sales"]);
  await page.key(grip, "Escape");
  assert.ok(document.querySelector('[role="dialog"]'));
  assert.equal(document.querySelector("[data-metric-option]")!.getAttribute("data-metric-option"), "sales");
  await page.key(grip, " "); await page.key(grip, "ArrowUp"); await page.key(grip, " ");
  await page.click(page.button("Aplicar"));
  assert.deepEqual(page.cards(), ["expenses", "sales"]);
});

test("phone settings exposes only summary and supports touch reorder", async () => {
  const page = await mount(390, [row(null)], "en");
  await page.open();
  assert.ok(document.querySelector('[role="dialog"]'));
  assert.equal(document.querySelector("button[draggable]"), null);
  assert.equal(document.querySelector('[data-column-setting]'), null);
  await page.click(page.button("Move Expenses up"));
  await page.click(page.button("Apply"));
  assert.deepEqual(page.cards(), ["expenses", "sales"]);
  assert.equal(document.activeElement, page.host.querySelector('button[aria-haspopup="dialog"]'));
});

test("pointer drag reorders selected metrics without applying the draft", async () => {
  const page = await mount();
  await page.open();
  const sales = document.querySelector<HTMLButtonElement>('[data-metric-option="sales"] button[draggable]')!;
  const expenses = document.querySelector<HTMLElement>('[data-metric-option="expenses"]')!;
  const transfer = { effectAllowed: "", setData: () => undefined };
  const drag = async (element: HTMLElement, type: string) => {
    const event = new Event(type, { bubbles: true, cancelable: true });
    Object.defineProperty(event, "dataTransfer", { value: transfer });
    await page.act(async () => element.dispatchEvent(event));
  };
  await drag(sales, "dragstart"); await drag(expenses, "dragover"); await drag(expenses, "drop");
  assert.equal(document.querySelector("[data-metric-option]")!.getAttribute("data-metric-option"), "expenses");
  assert.deepEqual(page.cards(), ["sales", "expenses"]);
  await page.click(page.button("Aplicar"));
  assert.deepEqual(page.cards(), ["expenses", "sales"]);
});

test("many currencies show two amounts and a bounded read-only disclosure", async () => {
  const currencies = ["USD", "EUR", "DOP", "GBP", "CAD", "AUD", "CHF", "JPY", "CNY", "MXN", "BRL", "ARS", "CLP", "COP", "PEN", "UYU", "PYG", "CRC", "GTQ", "HNL", "NIO", "BZD", "TTD", "JMD", "HTG", "XCD", "BBD", "BSD", "BMD", "KYD"];
  const page = await mount(1440, currencies.map((currency) => ({ ...row(false), money: { amount: "24", currency } })), "en");
  const card = page.host.querySelector('[data-summary-metric="expenses"]')!;
  const details = card.querySelector("details")!;
  assert.equal(details.open, false);
  assert.equal(card.querySelectorAll(":scope > div .cuadrao-amount").length, 2);
  assert.equal(details.querySelector("summary")?.textContent, "View 28 more currencies");
  const styles = (await import("@/components/business-app/transacciones/records-results-preview.module.css")).default;
  assert.ok(details.querySelector("div")!.classList.contains(styles.currencyList), "expanded currencies use the bounded scroll area");
  assert.equal(details.querySelectorAll(".cuadrao-amount").length, 28);
  assert.equal(card.querySelector("select"), null, "this reveals amounts; currency selection stays in Filters");
});
