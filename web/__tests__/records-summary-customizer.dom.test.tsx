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
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: language, resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default }, en: { translation: (await import("@/public/locales/en/common.json")).default } } });
  const Summary = (await import("@/components/business-app/transacciones/RecordsResultsSummary")).default;
  const host = document.createElement("div"); document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<I18nextProvider i18n={i18n}><Summary records={records} businessId="fixture-space" /></I18nextProvider>); });
  cleanups.push(async () => { await act(async () => root.unmount()); });
  const button = (name: string) => {
    const found = [...document.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.getAttribute("aria-label") === name || item.textContent === name);
    assert.ok(found, `button ${name}`); return found;
  };
  const click = async (element: HTMLElement) => { await act(async () => element.click()); };
  const key = async (element: Element, value: string) => { await act(async () => element.dispatchEvent(new KeyboardEvent("keydown", { key: value, bubbles: true, cancelable: true }))); };
  const toggle = async (metric: string) => { const label = document.querySelector<HTMLElement>(`[data-metric-option="${metric}"] label`); assert.ok(label); await click(label); };
  const cards = () => [...host.querySelectorAll("[data-summary-metric]")].map((item) => item.getAttribute("data-summary-metric"));
  return { host, act, button, click, key, toggle, cards };
}

test("summary choices apply as one draft, discard on Escape, recover an empty selection", async () => {
  const page = await mount();
  assert.deepEqual(page.cards(), ["sales", "expenses"]);
  assert.equal(page.host.querySelectorAll(".cuadrao-amount").length, 1, "money retains the privacy hook");
  await page.click(page.button("Personalizar resumen"));
  await page.toggle("count"); await page.toggle("sales");
  assert.deepEqual(page.cards(), ["sales", "expenses"], "draft does not alter cards");
  await page.key(document.activeElement!, "Escape");
  assert.equal(document.querySelector('[role="dialog"]'), null);
  await page.click(page.button("Personalizar resumen"));
  assert.equal(document.querySelector<HTMLInputElement>('[data-metric-option="count"] input')!.checked, false);
  await page.toggle("count"); await page.toggle("sales");
  await page.click(page.button("Aplicar"));
  assert.deepEqual(page.cards(), ["expenses", "count"]);
  await page.click(page.button("Personalizar resumen"));
  await page.toggle("expenses"); await page.toggle("count"); await page.click(page.button("Aplicar"));
  assert.deepEqual(page.cards(), []);
  assert.ok(page.host.textContent?.includes("Personalizar resumen"));
  await page.click(page.button("Personalizar resumen"));
  await page.click(page.button("Restaurar valores iniciales"));
  assert.deepEqual(page.cards(), [], "restore edits the draft only");
  await page.click(page.button("Aplicar"));
  assert.deepEqual(page.cards(), ["sales", "expenses"]);
});

test("keyboard reorder remains a draft and Escape first cancels the grabbed order", async () => {
  const page = await mount();
  await page.click(page.button("Personalizar resumen"));
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

test("phone sheet offers touch reorder and treats unknown backing files as unavailable", async () => {
  const page = await mount(390, [row(null)], "en");
  await page.click(page.button("Customize summary"));
  assert.ok(document.querySelector('[role="dialog"]'));
  assert.equal(document.querySelector("button[draggable]"), null);
  await page.click(page.button("Move Expenses up"));
  await page.toggle("without_document"); await page.click(page.button("Apply"));
  assert.deepEqual(page.cards(), ["expenses", "sales", "without_document"]);
  const missing = page.host.querySelector('[data-summary-metric="without_document"]')!;
  assert.ok(missing.textContent?.includes("Linked file information unavailable"));
  assert.ok(missing.textContent?.includes("1 record with unknown file information"));
  assert.equal(document.activeElement, page.button("Customize summary"));
});

test("pointer drag reorders selected metrics without applying the draft", async () => {
  const page = await mount();
  await page.click(page.button("Personalizar resumen"));
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
