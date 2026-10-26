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

async function mount(width = 1440, records = [row(false)], language = "es-419", summaryOverride?: ReturnType<typeof import("@/components/business-app/transacciones/records-results-preview").summarizeSettlementPreview>) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 844 });
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: language, resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default }, en: { translation: (await import("@/public/locales/en/common.json")).default } } });
  const { default: Summary, RecordsSummaryCards } = await import("@/components/business-app/transacciones/RecordsResultsSummary");
  const Settings = (await import("@/components/business-app/transacciones/RecordsSettingsPreview")).default;
  const { defaultRecordsPreferences } = await import("@/components/business-app/transacciones/records-view-preferences");
  function Harness() {
    const [preferences, setPreferences] = useState(defaultRecordsPreferences);
    const [kind, setKind] = useState<RecordRow["kind"] | "all">("gasto");
    return <><button onClick={() => setKind("all")}>All</button><button onClick={() => setKind("venta")}>Sales</button><button onClick={() => setKind("gasto")}>Expenses</button><Settings value={preferences} onChange={setPreferences} />{summaryOverride ? <RecordsSummaryCards summary={summaryOverride} kind="gasto" /> : <Summary kind={kind} records={records} businessId="fixture-space" />}</>;
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
  const summary = () => host.querySelector("[data-testid=records-results-summary]");
  const open = async () => {
    await click(host.querySelector<HTMLButtonElement>('button[aria-haspopup="dialog"]')!);
  };
  return { host, act, button, click, key, summary, open };
}

test("summary follows record kind automatically and settings only change table presentation", async () => {
  const page = await mount();
  assert.match(page.summary()!.textContent ?? "", /Gastos.*24.00.*Pagado.*12.00.*Por pagar.*12.00/);
  assert.equal(page.summary()!.querySelectorAll(".cuadrao-amount").length, 3);
  await page.open();
  assert.deepEqual([...document.querySelectorAll('[role="radiogroup"] > [role="radio"]')].map((tab) => tab.textContent), ["Columnas", "Altura de filas"]);
  assert.equal(document.querySelector('[data-summary-setting]'), null);
  await page.click(page.button("Altura de filas"));
  assert.ok(page.summary());
  await page.key(document.activeElement!, "Escape");
  await page.click(page.button("All")); assert.equal(page.summary(), null, "Todos never shows a mixed financial total");
  await page.click(page.button("Sales"));
  assert.match(page.summary()!.textContent ?? "", /Facturado.*Cobrado.*Por cobrar/);
  assert.equal(page.summary()!.querySelectorAll(".cuadrao-amount").length, 0, "unknown sales are not zero");
});

test("phone has automatic summaries without an empty settings control", async () => {
  const page = await mount(390, [row(null)], "en");
  assert.equal(page.host.querySelector('button[aria-haspopup="dialog"]'), null);
  assert.ok(page.summary());
  await page.click(page.button("All"));
  assert.equal(page.summary(), null);
  await page.click(page.button("Expenses")); assert.ok(page.summary());
});

test("two currencies stay visible in three read-only metric cards", async () => {
  const page = await mount(1440, [row(false), { ...row(false), id: "exp-gas", money: { amount: "2100.00", currency: "DOP" } }], "en");
  const summary = page.summary()!;
  assert.equal(summary.querySelectorAll("[data-summary-part]").length, 3);
  assert.equal(summary.querySelectorAll(".cuadrao-amount").length, 6);
  for (const card of summary.querySelectorAll("[data-summary-part]")) {
    assert.deepEqual([...card.querySelectorAll("[data-currency]")].map((cell) => cell.getAttribute("data-currency")), ["DOP", "USD"]);
  }
  assert.equal(summary.querySelector("select"), null);
  assert.equal(summary.querySelector("button"), null, "amount drill-down is not yet connected");
});

for (const width of [1440, 390]) test(`overflow currencies open one shared breakdown and restore focus at ${width}px`, async () => {
  const page = await mount(width, [], "en", {
    currencies: [
      { currency: "DOP", total: "2100.00", settled: "1200.00", balance: "900.00" },
      { currency: "EUR", total: "180.00", settled: null, balance: null },
      { currency: "USD", total: "24.00", settled: "12.00", balance: "12.00" },
    ],
    exclusions: { unconfirmed: 1, personal: 0, unavailable: 0 },
  });
  const summary = page.summary()!;
  assert.equal(summary.querySelectorAll("[data-currency]").length, 6, "only two currency rows per card");
  assert.equal(summary.querySelector('[data-currency="USD"]'), null);
  const trigger = page.button("View all 3 currencies");
  trigger.focus(); await page.click(trigger);
  const panel = document.querySelector('[data-testid="records-currency-breakdown"]')!;
  assert.ok(panel);
  assert.equal(panel.querySelectorAll("[data-currency]").length, 3);
  assert.match(panel.textContent ?? "", /USD.*Expenses.*24.00.*Paid.*12.00.*To pay.*12.00/);
  assert.equal(panel.querySelector('[data-currency="EUR"]')!.querySelectorAll(".cuadrao-amount").length, 1, "missing settlement stays unknown");
  assert.ok(panel.closest(width >= 1024 ? '[role="region"]' : '[role="dialog"]'));
  assert.equal(panel.querySelector("select,input"), null, "breakdown does not add a currency filter");
  await page.key(document.activeElement!, "Escape");
  assert.equal(document.querySelector('[data-testid="records-currency-breakdown"]'), null);
  assert.equal(document.activeElement, trigger);
});
