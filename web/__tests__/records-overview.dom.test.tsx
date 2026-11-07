import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import RecordsOverviewPreview from "@/components/business-app/transacciones/RecordsOverviewPreview";
import type { ReportAnswer, ReportFiscalTotal } from "@/lib/business-reports-api";
import spanish from "@/public/locales/es-419/common.json";
import english from "@/public/locales/en/common.json";

beforeAll(() => { GlobalRegistrator.register(); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
let cleanup = async () => {};
afterEach(async () => { await cleanup(); document.body.innerHTML = ""; });
afterAll(() => GlobalRegistrator.unregister());
const fiscal = (patch: Partial<ReportFiscalTotal>): ReportFiscalTotal => ({ basis: "goods", currency: "DOP", kind: "expense", applicable_count: 25, populated_count: 12, known_amount_minor: 500, unknown_count: 13, unsupported_count: 0, complete: false, amount_minor: null, amount: null, known_amount: "5.00", ...patch });
const answer = { matching_count: 1828, totals: [
  { basis: "document_family_amount", currency: "DOP", kind: "expense", matching_count: 500, known_amount_minor: 11111, unknown_count: 0, unsupported_count: 0, complete: true, amount_minor: 11111, amount: "111.11", known_amount: "111.11" },
  { basis: "document_family_amount", currency: "DOP", kind: "income", matching_count: 400, known_amount_minor: 22222, unknown_count: 0, unsupported_count: 0, complete: true, amount_minor: 22222, amount: "222.22", known_amount: "222.22" },
  { basis: "recorded_activity_amount", currency: "DOP", kind: "expense", matching_count: 900, known_amount_minor: 99999, unknown_count: 0, unsupported_count: 0, complete: true, amount_minor: 99999, amount: "999.99", known_amount: "999.99" },
], fiscal_totals: [fiscal({ basis: "itbis", amount: "18.18", complete: true, unknown_count: 0 }), fiscal({ basis: "itbis", kind: "income", amount: "36.36", complete: true, unknown_count: 0 }), fiscal({}), fiscal({ basis: "services", populated_count: 7, known_amount: "9.00", unsupported_count: 2 })] } satisfies Pick<ReportAnswer, "totals" | "fiscal_totals" | "matching_count">;
async function mount(props: Partial<Parameters<typeof RecordsOverviewPreview>[0]> = {}, language = "es-419") {
  const { createRoot } = await import("react-dom/client");
  const i18n = i18next.createInstance(); await i18n.init({ lng: language, resources: { "es-419": { translation: spanish }, en: { translation: english } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host); const chosen: string[] = []; let totalToggles = 0;
  const render = async (extra: Partial<Parameters<typeof RecordsOverviewPreview>[0]> = {}) => act(async () => root.render(<I18nextProvider i18n={i18n}><RecordsOverviewPreview answer={answer} fiscalCount={71} totalExpanded={false} onToggleTotal={() => { totalToggles++; }} selected={[]} onChoose={(key) => chosen.push(key)} waiting={null} onOpenBandeja={() => {}} {...props} {...extra} /></I18nextProvider>));
  await render(); cleanup = async () => act(async () => root.unmount()); return { chosen, render, totalToggles: () => totalToggles };
}
const card = (key: string) => document.querySelector<HTMLElement>(`[data-overview-card="${key}"]`)!;
test("six cards use purchase server totals and four cards have no card action", async () => {
  const page = await mount();
  assert.deepEqual([...document.querySelectorAll("[data-overview-card]")].map((el) => el.getAttribute("data-overview-card")), ["total", "itbis", "quantity", "goods", "services", "fiscal"]);
  assert.match(card("total").textContent!, /Compras.*111\.11/);
  assert.doesNotMatch(card("total").textContent!, /Ventas|222\.22|999\.99|333\.33/);
  assert.equal(card("itbis").querySelector('[data-family="purchase"] .sr-only')?.textContent, "DOP 18.18");
  assert.equal(card("itbis").querySelector('[data-family="sale"]'), null);
  assert.match(card("quantity").textContent!, /1,828/); assert.match(card("fiscal").textContent!, /71/);
  for (const key of ["itbis", "quantity", "goods", "services"]) {
    assert.equal(card(key).tagName, "DIV"); assert.equal(card(key).hasAttribute("tabindex"), false); assert.equal(card(key).getAttribute("role"), null);
    await act(async () => card(key).click());
  }
  assert.deepEqual(page.chosen, []); assert.equal(page.totalToggles(), 0);
  const total = card("total").querySelector<HTMLButtonElement>('button[aria-controls]')!;
  assert.equal(total.type, "button"); assert.equal(total.getAttribute("aria-label"), "Total");
  assert.equal(total.getAttribute("aria-expanded"), "false");
  await act(async () => total.click()); assert.equal(page.totalToggles(), 1); assert.deepEqual(page.chosen, []);
  await page.render({ totalExpanded: true }); assert.equal(total.getAttribute("aria-expanded"), "true");
  assert.equal(card("fiscal").tagName, "BUTTON"); await act(async () => card("fiscal").click()); assert.deepEqual(page.chosen, ["fiscal"]);
  assert.equal(card("fiscal").getAttribute("type"), "button");
  assert.doesNotMatch(document.body.textContent!, /Listos para exportar|Ya exportados/);
});
test("coverage is per metric, partial and unsupported stay explicit, absent values stay unknown", async () => {
  await mount(); assert.match(card("goods").textContent!, /12 de 25 compras/); assert.match(card("services").textContent!, /7 de 25 compras/);
  assert.match(card("goods").textContent!, /Parcial.*5\.00/); assert.match(card("services").textContent!, /2.*no compatibles/);
  assert.equal(card("goods").querySelector(".cuadrao-amount .sr-only")?.textContent, "DOP 5.00"); assert.ok(card("goods").querySelector(".cuadrao-amount")); assert.ok(card("goods").querySelector("sup"));
  await cleanup(); await mount({ answer: undefined, fiscalCount: null }); assert.doesNotMatch(card("total").textContent!, /0\.00/); assert.equal((card("fiscal") as HTMLButtonElement).disabled, true);
});
test("loading clears old answer values while retaining the date-only fiscal count", async () => {
  await mount({ loading: true }); assert.doesNotMatch(card("total").textContent!, /111\.11/); assert.doesNotMatch(card("quantity").textContent!, /1,828/); assert.match(card("fiscal").textContent!, /71/);
});
test("currency overflow opens the existing sheet and returns focus", async () => {
  const rows = ["DOP", "USD", "EUR"].map((currency) => ({ ...answer.totals[0], currency, amount: "9007199254740993.01" }));
  await mount({ answer: { ...answer, totals: rows } }, "en");
  const trigger = card("total").querySelector<HTMLButtonElement>("button:not([aria-controls])")!; assert.ok(trigger); assert.equal(card("total").querySelector("button button"), null); trigger.focus(); await act(async () => trigger.click());
  assert.ok(document.querySelector('[data-testid="records-overview-breakdown"]')); assert.match(document.querySelector('[data-testid="records-overview-breakdown"]')!.textContent!, /EUR/);
  assert.match(card("total").querySelector(".cuadrao-amount[aria-label]")!.getAttribute("aria-label")!, /9,007,199,254,740,993\.01/);
  await act(async () => document.querySelector<HTMLButtonElement>('button[aria-label="Close"]')!.click()); assert.equal(document.activeElement, trigger);
});

test("known zero is an amount while missing and unusable populated values remain unknown", async () => {
  const rows = [fiscal({ applicable_count: 1, populated_count: 1, unknown_count: 0, complete: true, amount: "0.00", known_amount: "0.00" })];
  const page = await mount({ answer: { ...answer, fiscal_totals: rows } });
  assert.match(card("goods").textContent!, /0\.00/); assert.doesNotMatch(card("goods").textContent!, /Parcial/);
  await page.render({ answer: { ...answer, fiscal_totals: [fiscal({ applicable_count: 1, populated_count: 1, unknown_count: 1, known_amount: "0.00" })] } });
  assert.doesNotMatch(card("goods").textContent!, /0\.00|Parcial/); assert.match(card("goods").textContent!, /1 de 1 compras/);
  await page.render({ answer: { ...answer, fiscal_totals: [fiscal({ applicable_count: 1, populated_count: 1, unknown_count: 0, unsupported_count: 1, known_amount: "0.00" })] } });
  assert.doesNotMatch(card("goods").textContent!, /0\.00|Parcial/); assert.match(card("goods").textContent!, /1 importe no compatible/);
  await page.render({ answer: { ...answer, fiscal_totals: [fiscal({ populated_count: 0, unknown_count: 25, known_amount: "0.00" })] } });
  assert.doesNotMatch(card("goods").textContent!, /0\.00|Parcial/); assert.match(card("goods").textContent!, /0 de 25 compras/);
});

test("coverage remains separate for each server currency and each metric", async () => {
  await mount({ answer: { ...answer, fiscal_totals: [fiscal({}), fiscal({ currency: "USD", populated_count: 3, applicable_count: 8, unknown_count: 5, known_amount: "7.00" }), fiscal({ basis: "services", populated_count: 4, applicable_count: 25, unknown_count: 21, known_amount: "8.00" })] } });
  assert.match(card("goods").textContent!, /DOP.*12 de 25 compras.*USD.*3 de 8 compras/);
  assert.doesNotMatch(card("goods").textContent!, /15 de 33|12\.00/);
  assert.match(card("services").textContent!, /4 de 25 compras/);
});
