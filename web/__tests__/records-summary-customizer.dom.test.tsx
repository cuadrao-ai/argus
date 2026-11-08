import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReportTotal } from "@/lib/business-reports-api";
import { recordedReportAnswer } from "./fixtures/recorded-report-answer";

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
const total = (currency: string, amount: string, minor: number): ReportTotal => ({ basis: "document_family_amount", currency, kind: "expense", matching_count: 1, known_amount_minor: minor, unknown_count: 0, unsupported_count: 0, complete: true, amount_minor: minor, amount, known_amount: amount });

async function mount(width = 1440, totals = [total("USD", "24.00", 2400)], language = "es-419", summaryOverride?: ReturnType<typeof import("@/components/business-app/transacciones/records-results-preview").summarizeSettlementPreview>) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 844 });
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: language, resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default }, en: { translation: (await import("@/public/locales/en/common.json")).default } } });
  const { default: Summary, RecordsSummaryCards } = await import("@/components/business-app/transacciones/RecordsResultsSummary");
  const Settings = (await import("@/components/business-app/transacciones/RecordsSettingsPreview")).default;
  const { sampleRecordsPreferences } = await import("@/components/business-app/transacciones/sample-records-preferences");
  function Harness() {
    const [preferences, setPreferences] = useState(sampleRecordsPreferences);
    const [kind, setKind] = useState<"gasto" | "venta">("gasto");
    const [showPurchaseTotal, setShowPurchaseTotal] = useState(false);
    return <div data-current-family={kind}><button onClick={() => setKind("venta")}>Sales</button><button onClick={() => setKind("gasto")}>Expenses</button><button aria-expanded={showPurchaseTotal} onClick={() => setShowPurchaseTotal((shown) => !shown)}>Total</button><Settings value={preferences} onChange={setPreferences} onRestore={() => setPreferences(sampleRecordsPreferences())} />{showPurchaseTotal ? summaryOverride ? <RecordsSummaryCards summary={summaryOverride} kind="gasto" /> : <Summary kind={kind} answer={{ ...recordedReportAnswer, totals }} /> : null}</div>;
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

test("Total controls the purchase subcard independently of family and table settings", async () => {
  const page = await mount();
  assert.equal(page.summary(), null);
  await page.click(page.button("Expenses")); assert.equal(page.summary(), null);
  await page.click(page.button("Total"));
  assert.match(page.summary()!.textContent ?? "", /Compras.*24.00/);
  assert.doesNotMatch(page.summary()!.textContent ?? "", /Pagado|Por pagar|Cobrado|Por cobrar/);
  assert.equal(page.summary()!.querySelectorAll(".cuadrao-amount").length, 1);
  await page.open();
  assert.deepEqual([...document.querySelectorAll('[role="radiogroup"] > [role="radio"]')].map((tab) => tab.textContent), ["Columnas", "Altura de filas"]);
  assert.equal(document.querySelector('[data-summary-setting]'), null);
  await page.click(page.button("Altura de filas"));
  assert.ok(page.summary());
  await page.key(document.activeElement!, "Escape");
  await page.click(page.button("Total")); assert.equal(page.summary(), null);
  await page.click(page.button("Sales")); assert.equal(page.summary(), null);
});

test("phone keeps the Total toggle without an empty settings control", async () => {
  const page = await mount(390, undefined, "en");
  assert.equal(page.host.querySelector('button[aria-haspopup="dialog"]'), null);
  assert.equal(page.summary(), null);
  await page.click(page.button("Total")); assert.ok(page.summary());
  await page.click(page.button("Total")); assert.equal(page.summary(), null);
  await page.click(page.button("Expenses")); assert.equal(page.summary(), null);
});

test("one server currency stays visible in the static purchase subcard without a breakdown control", async () => {
  const page = await mount(1440, [total("USD", "24.00", 2400)], "en");
  await page.click(page.button("Total"));
  const summary = page.summary()!;
  assert.equal(summary.querySelectorAll("[data-summary-part]").length, 1);
  assert.equal(summary.querySelectorAll(".cuadrao-amount").length, 1);
  assert.deepEqual([...summary.querySelectorAll("[data-currency]")].map((cell) => cell.getAttribute("data-currency")), ["USD"]);
  assert.equal(summary.querySelector("select,button"), null);
});
