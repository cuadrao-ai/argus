import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, type ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import ReceiptRecordFacts from "@/components/business-app/ReceiptRecordFacts";
import FiscalDeclarationEditor from "@/components/business-app/FiscalDeclarationEditor";
import type { BusinessDossier, BusinessFact } from "@/lib/business-dossier";
import type { DgiiFields, DgiiReview } from "@/lib/business-dgii";
import { flaggedReceipt } from "./fixtures/review-flags";
import es from "@/public/locales/es-419/common.json";
import en from "@/public/locales/en/common.json";

beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost" }); Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); });
let cleanup = async () => {};
afterEach(async () => { await cleanup(); document.body.innerHTML = ""; });
afterAll(() => GlobalRegistrator.unregister());
const known = (value: string): BusinessFact<string> => ({ state: "known", value, origin: "extracted", verified: false, source_ids: [] });
async function dossier() {
  const base = await flaggedReceipt([], [{ id: "cash", nickname: "Caja", currency: "DOP", type: "cash" }]);
  return { ...base, net_amount: { amount: "1000.00", source: "calculated" }, facts: { ...base.facts, legal_tip: known("100.00") }, inheritance: { goods_amount: { field: "net_amount", value: "1000.00", inherited: true }, paid_on: { field: "occurred_on", value: "2026-11-12", inherited: true }, itbis: { field: "itbis", value: "181.00", inherited: true } } } satisfies BusinessDossier;
}
async function mount(content: ReactNode, language = "es-419") {
  const { createRoot } = await import("react-dom/client");
  const i18n = i18next.createInstance(); await i18n.init({ lng: language, resources: { "es-419": { translation: es }, en: { translation: en } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}>{content}</I18nextProvider>));
  cleanup = async () => act(async () => root.unmount());
  return host;
}
for (const documentType of ["recibo", "venta"] as const) {
  test(`${documentType} has one Montos block between the date and Fiscal, with net, ITBIS, tip, and total`, async () => {
    const base = await dossier(); base.document_type = documentType;
    const host = await mount(<ReceiptRecordFacts dossier={base} accounts={[]} review={{ row: (_, shown) => shown.value, note: () => null, noReceipt: { busy: false, note: null } }} />);
    const blocks = [...host.querySelectorAll("section")].map((section) => section.dataset.testid);
    assert.ok(blocks.indexOf("receipt-facts-activity") < blocks.indexOf("receipt-facts-montos"));
    assert.ok(blocks.indexOf("receipt-facts-montos") < blocks.indexOf("receipt-facts-fiscal"));
    const amounts = host.querySelector('[data-testid="receipt-facts-montos"]')!;
    assert.deepEqual([...amounts.querySelectorAll("[data-fact]")].map((row) => row.getAttribute("data-fact")), ["currency", "net_amount", "itbis", "legal_tip", "amount"]);
    assert.equal(host.querySelector('[data-testid="receipt-facts-fiscal"] [data-fact="itbis"]'), null);
    assert.equal(host.querySelector('[data-testid="amount-calculated"]')?.getAttribute("aria-label"), "Calculado: Total − ITBIS − propina");
    const formula = amounts.querySelector('[data-testid="amount-calculated"]')!;
    assert.equal(formula.closest("dt")?.textContent, "Monto sin ITBISƒ");
    assert.equal(formula.closest("dd"), null);
    for (const cell of amounts.querySelectorAll("dd")) { assert.ok(cell.classList.contains("cuadrao-amount")); assert.ok(cell.classList.contains("text-right")); assert.ok(cell.classList.contains("tabular-nums")); }
  });
}
test("only calculated net gets the formula badge; no tip has the shorter formula", async () => {
  const base = await dossier(); base.facts.legal_tip = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
  let host = await mount(<ReceiptRecordFacts dossier={base} accounts={[]} />);
  assert.equal(host.querySelector('[data-testid="amount-calculated"]')?.getAttribute("aria-label"), "Calculado: Total − ITBIS");
  assert.equal(host.querySelector('[data-fact="legal_tip"]'), null);
  await cleanup();
  host = await mount(<ReceiptRecordFacts dossier={{ ...base, net_amount: { amount: "1000.00", source: "read" } }} accounts={[]} />);
  assert.equal(host.querySelector('[data-testid="amount-calculated"]'), null);
});
for (const language of ["es-419", "en"]) test(`${language} puts the warning on Total and one exact difference line below`, async () => {
  const base = await dossier(); base.review_flags = [{ code: "amounts_mismatch", field: "amount", confirm: false, difference: "1.23" }];
  const host = await mount(<ReceiptRecordFacts dossier={base} accounts={[]} />, language);
  const difference = host.querySelector('[data-testid="amounts-difference"]')!;
  assert.equal(difference.textContent, `${language === "es-419" ? "Diferencia" : "Difference"} 1.23`);
  assert.equal(host.querySelectorAll('[data-testid="amounts-difference"]').length, 1);
  assert.equal(difference.querySelector("svg"), null);
  assert.ok(host.querySelector(".lucide-triangle-alert"));
  const warning = host.querySelector('[data-testid="amounts-warning"]')!;
  assert.equal(warning.closest("[data-fact]")?.getAttribute("data-fact"), "amount");
  assert.equal(warning.closest("dt")?.textContent, language === "es-419" ? "Total (con ITBIS)" : "Total (with ITBIS)");
  assert.match(host.querySelector('[data-fact="amount"] dd')!.className, /9a650d/);
});
const fields: DgiiFields = { "606": [
  { name: "goods_amount", label: "", kind: "money", options: [] },
  { name: "itbis", label: "", kind: "money", options: [] },
  { name: "paid_on", label: "", kind: "date", options: [] },
  { name: "modified_ncf", label: "", kind: "text", options: [] },
], "607": [] };
const noop = () => {};
test("approved documents keep Fecha immediately before Montos", async () => {
  const host = await mount(<ReceiptRecordFacts dossier={await dossier()} accounts={[]} />);
  const activity = host.querySelector('[data-testid="receipt-facts-activity"]')!;
  assert.deepEqual([...activity.querySelectorAll("[data-fact]")].map((row) => row.getAttribute("data-fact")), ["kind", "counterparty", "occurred_on"]);
  assert.equal(activity.nextElementSibling?.getAttribute("data-testid"), "receipt-facts-montos");
});
for (const amount of ["181.00", "200.00"]) test(`Fiscal explicitly overriding ITBIS with ${amount} breaks inheritance and saves only in declaration`, async () => {
  const base = await dossier(); const writes: DgiiReview[] = [];
  const host = await mount(<FiscalDeclarationEditor dossier={base} fields={fields} disabled={false} open reviewFiscal={async (_, __, input) => { writes.push(input); return base; }} onChanged={noop} onBusy={noop} onDirty={noop} reviewMontos={async () => base} />);
  assert.equal(host.querySelector('[data-inherited="goods_amount"]')?.getAttribute("aria-label"), "Viene de Monto sin ITBIS");
  assert.ok(host.querySelector('[data-inherited="paid_on"]'));
  assert.equal(host.querySelector('[data-inherited="modified_ncf"]'), null);
  const input = host.querySelector<HTMLInputElement>('input[data-testid="fiscal-declaration-itbis"]')!;
  assert.ok(input);
  await act(async () => { input.setSelectionRange(0, input.value.length); input.dispatchEvent(new InputEvent("beforeinput", { inputType: "insertText", data: amount, bubbles: true, cancelable: true })); });
  assert.equal(host.querySelector('[data-inherited="itbis"]'), null);
  assert.ok(host.querySelector('[data-restore-inherited="itbis"]'));
  const save = [...host.querySelectorAll("button")].find((button) => button.textContent === es.business.dgii.save)!;
  await act(async () => save.click());
  assert.equal(writes.length, 1);
  assert.equal(writes[0].fiscal.itbis, "181.00");
  assert.equal(writes[0].declaration.itbis, amount);
  assert.deepEqual(writes[0].montos, { override_inherited: ["itbis"] });
});
test("Fiscal restore sends an explicit server restore and uses the source amount in its accessible name", async () => {
  const base = await dossier(); base.inheritance.goods_amount.inherited = false;
  const restored: unknown[] = [];
  const host = await mount(<FiscalDeclarationEditor dossier={base} fields={fields} disabled={false} open reviewFiscal={async () => base} reviewMontos={async (_, __, input) => { restored.push(input); return base; }} onChanged={noop} onBusy={noop} onDirty={noop} />);
  const button = host.querySelector<HTMLButtonElement>('[data-restore-inherited="goods_amount"]')!;
  assert.equal(button.getAttribute("aria-label"), "Usar Montos (RD$ 1,000.00)");
  await act(async () => button.click());
  assert.deepEqual(restored, [{ restore_inherited: ["goods_amount"] }]);
});


test("Montos has no provenance words or tax warning text, and edited net has no source badge", async () => {
  const base = await dossier();
  base.facts.amount = { ...known("1181.00"), origin: "member_set" };
  base.facts.fiscal!.itbis = { ...known("181.00"), origin: "member_set" };
  base.review_flags = [{ code: "itbis_high", field: "itbis", confirm: false }];
  const host = await mount(<ReceiptRecordFacts dossier={{ ...base, net_amount: { amount: "1000.00", source: "edited" } }} accounts={[]} />);
  const block = host.querySelector('[data-testid="receipt-facts-montos"]')!;
  assert.equal(block.querySelector("[data-origin], [data-doubtful], [data-testid=itbis-high], [data-testid=amount-calculated]"), null);
  assert.doesNotMatch(block.textContent!, /revisor|revisar/);
});


test("Fiscal restore shows unknown for null money and date targets", async () => {
  const base = await dossier();
  const empty: BusinessDossier = { ...base, inheritance: {
    ...base.inheritance,
    goods_amount: { field: "net_amount", value: null, inherited: false },
    paid_on: { field: "occurred_on", value: null, inherited: false },
  } };
  const host = await mount(<FiscalDeclarationEditor dossier={empty} fields={fields} disabled={false} open reviewFiscal={async () => empty} reviewMontos={async () => empty} onChanged={noop} onBusy={noop} onDirty={noop} />);
  for (const field of ["goods_amount", "paid_on"]) {
    assert.equal(host.querySelector(`[data-restore-inherited="${field}"]`)?.getAttribute("aria-label"), "Usar Montos (-)");
  }
});

for (const currency of ["DOP", "USD", "EUR", null]) test(`Montos names ${currency ?? "missing currency"} once and rows contain only numbers`, async () => {
  const base = await dossier();
  base.facts.currency = currency ? known(currency) : { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
  const host = await mount(<ReceiptRecordFacts dossier={base} accounts={[]} />);
  const block = host.querySelector('[data-testid="receipt-facts-montos"]')!;
  assert.ok(block.textContent?.includes(currency ? `Montos · ${currency}` : "Falta la moneda"));
  assert.doesNotMatch(block.querySelector("dl")!.textContent!, /RD\$|US\$|€/);
});
