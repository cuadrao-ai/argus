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
import type { previewBusinessAmounts } from "@/lib/business-api";
import { PREVIEW_DELAY_MS } from "@/components/business-app/useAmountsPreview";
import { TOOLTIP_DELAY_MS } from "@/components/ui/Tooltip";
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
  return { ...base, net_amount: { amount: "1000.00", source: "calculated" }, facts: { ...base.facts, legal_tip: known("100.00") }, inheritance: { goods_amount: { field: "net_amount", value: "1000.00", inherited: true, paired_with: ["services_amount"] }, paid_on: { field: "occurred_on", value: "2026-11-12", inherited: true, paired_with: [] }, itbis: { field: "itbis", value: "181.00", inherited: true, paired_with: [] } } } satisfies BusinessDossier;
}
async function mount(content: ReactNode, language = "es-419") {
  const { createRoot } = await import("react-dom/client");
  const i18n = i18next.createInstance(); await i18n.init({ lng: language, resources: { "es-419": { translation: es }, en: { translation: en } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}>{content}</I18nextProvider>));
  cleanup = async () => act(async () => root.unmount());
  return host;
}
const closed = { open: false, saving: false, locked: false, onSave: () => {}, onCancel: () => {}, editor: null };
const montos = (host: Element) => host.querySelector('[data-testid="receipt-facts-montos"]')!;
for (const documentType of ["recibo", "venta"] as const) {
  test(`${documentType} has one Montos card, the last of General, with subtotal, ITBIS, tip, and total`, async () => {
    const base = await dossier(); base.document_type = documentType;
    const host = await mount(<ReceiptRecordFacts dossier={base} accounts={[]} review={{ edit: () => closed, note: () => null, noReceipt: { busy: false, note: null } }} />);
    assert.deepEqual([...host.querySelectorAll("section")].map((section) => section.dataset.testid), ["receipt-facts-comprobante", "receipt-facts-montos"]);
    const amounts = montos(host);
    assert.deepEqual([...amounts.querySelectorAll("li[data-fact]")].map((row) => row.getAttribute("data-fact")), ["net_amount", "itbis", "legal_tip", "amount"]);
    assert.equal(amounts.querySelector('[data-testid="montos-currency"]')?.textContent, "DOP", "the currency is the heading's picker, as its ISO code");
    assert.equal(host.querySelector('[data-testid="receipt-facts-comprobante"] [data-fact="itbis"]'), null);
    const formula = amounts.querySelector('[data-testid="row-status-net_amount"]')!;
    assert.equal(formula.getAttribute("aria-label"), "Calculado: Total − ITBIS − propina");
    assert.equal(formula.textContent, "ƒ", "a calculated subtotal says so in its status slot");
    for (const cell of amounts.querySelectorAll("li[data-fact] [data-row-value]")) assert.ok(cell.classList.contains("cuadrao-amount"));
  });
}
test("only a calculated subtotal gets the formula mark; no tip has the shorter formula", async () => {
  const base = await dossier(); base.facts.legal_tip = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
  let host = await mount(<ReceiptRecordFacts dossier={base} accounts={[]} />);
  assert.equal(host.querySelector('[data-testid="row-status-net_amount"]')?.getAttribute("aria-label"), "Calculado: Total − ITBIS");
  assert.equal(host.querySelector('[data-fact="legal_tip"]'), null);
  await cleanup();
  host = await mount(<ReceiptRecordFacts dossier={{ ...base, net_amount: { amount: "1000.00", source: "read" } }} accounts={[]} />);
  assert.equal(host.querySelector('[data-testid="row-status-net_amount"]'), null);
});
for (const language of ["es-419", "en"]) test(`${language} puts the warning on Total, and the server's difference is its words`, async () => {
  const base = await dossier(); base.review_flags = [{ code: "amounts_mismatch", field: "amount", confirm: false, difference: "1.23" }];
  const host = await mount(<ReceiptRecordFacts dossier={base} accounts={[]} />, language);
  const warnings = host.querySelectorAll('[data-status="warn"]');
  assert.equal(warnings.length, 1);
  assert.equal(warnings[0].getAttribute("data-testid"), "row-status-amount");
  assert.equal(warnings[0].getAttribute("aria-label"), `${language === "es-419" ? "Diferencia" : "Difference"} 1.23`);
  assert.ok(warnings[0].querySelector(".lucide-triangle-alert"));
  assert.equal(warnings[0].closest("[data-fact]")?.firstElementChild?.textContent, "Total");
});
const fields: DgiiFields = { "606": [
  { name: "goods_amount", label: "", kind: "money", options: [] },
  { name: "itbis", label: "", kind: "money", options: [] },
  { name: "paid_on", label: "", kind: "date", options: [] },
  { name: "modified_ncf", label: "", kind: "text", options: [] },
], "607": [] };
const noop = () => {};
test("a record nobody can edit shows the same cards, and Montos follows Comprobante", async () => {
  const host = await mount(<ReceiptRecordFacts dossier={await dossier()} accounts={[]} />);
  const comprobante = host.querySelector('[data-testid="receipt-facts-comprobante"]')!;
  assert.deepEqual([...comprobante.querySelectorAll("[data-fact]")].map((row) => row.getAttribute("data-fact")).slice(0, 4), ["rnc", "counterparty", "fiscal_number", "occurred_on"]);
  assert.equal(comprobante.nextElementSibling?.getAttribute("data-testid"), "receipt-facts-montos");
  assert.equal(host.querySelectorAll("button[data-row-value], [aria-label^='Editar']").length, 0, "no row opens");
});
for (const amount of ["181.00", "200.00"]) test(`Fiscal explicitly overriding ITBIS with ${amount} breaks inheritance and saves only in declaration`, async () => {
  const base = await dossier(); const writes: DgiiReview[] = [];
  const host = await mount(<FiscalDeclarationEditor dossier={base} fields={fields} disabled={false} reviewFiscal={async (_, __, input) => { writes.push(input); return base; }} onChanged={noop} onBusy={noop} onDirty={noop} />);
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
async function tooltip(trigger: Element) {
  await act(async () => { trigger.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })); });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, TOOLTIP_DELAY_MS + 20)); });
  const text = document.querySelector('[role="tooltip"]')?.textContent ?? null;
  await act(async () => { trigger.dispatchEvent(new MouseEvent("mouseout", { bubbles: true })); });
  return text;
}
async function type(input: HTMLInputElement, text: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, text);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
type Links = NonNullable<BusinessDossier["inheritance"]>;
type LinksDraft = Parameters<typeof previewBusinessAmounts>[2];
/** A stand-in for the server's preview: the dossier's links with the draft's holds and restores, and any linked value the case names. */
function server(base: BusinessDossier, values: Record<string, string | null> = {}) {
  const drafts: LinksDraft[] = [];
  const preview = async (_: string, __: number, draft: LinksDraft) => {
    drafts.push(draft);
    const inheritance: Links = Object.fromEntries(Object.entries(base.inheritance ?? {}).map(([name, link]) => {
      const group = [name, ...link.paired_with];
      const inherited = group.some((side) => draft.restore_inherited?.includes(side)) ? true : group.some((side) => draft.override_inherited?.includes(side)) ? false : link.inherited;
      return [name, { ...link, inherited, value: name in values ? values[name] : link.value }];
    }));
    return { net_amount: { amount: null, source: null }, mismatch: null, inheritance };
  };
  return { drafts, preview };
}
const settle = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, PREVIEW_DELAY_MS + 30)); });
async function editing(base: BusinessDossier, options: { values?: Record<string, string | null>; fields?: DgiiFields; fiscal?: () => Promise<BusinessDossier> } = {}) {
  const writes: DgiiReview[] = [];
  const { drafts, preview } = server(base, options.values);
  const host = await mount(<FiscalDeclarationEditor dossier={base} fields={options.fields ?? fields} disabled={false} reviewFiscal={async (_, __, input) => { writes.push(input); return options.fiscal?.() ?? base; }} previewLinks={preview} onChanged={noop} onBusy={noop} onDirty={noop} />);
  const ncf = host.querySelector<HTMLInputElement>('[name="modified_ncf"]')!;
  const amount = (name: string) => host.querySelector<HTMLInputElement>(`input[data-testid="fiscal-declaration-${name}"]`)!;
  const enter = async (name: string, text: string) => act(async () => { const input = amount(name); input.setSelectionRange(0, input.value.length); input.dispatchEvent(new InputEvent("beforeinput", { inputType: "insertText", data: text, bubbles: true, cancelable: true })); });
  const save = async () => act(async () => [...host.querySelectorAll("button")].find((button) => button.textContent === es.business.dgii.save)!.click());
  const restore = (field: string) => host.querySelector<HTMLButtonElement>(`[data-restore-inherited="${field}"]`);
  return { host, get date() { return host.querySelector<HTMLInputElement>("#fiscal-declaration-paid_on")!; }, ncf, amount, enter, writes, drafts, save, restore, linked: (field: string) => host.querySelector(`[data-inherited="${field}"]`) };
}

test("Restaurar on an unsaved edit shows the server's linked value, saves nothing and keeps the other edits", async () => {
  const view = await editing(await dossier(), { values: { paid_on: "2026-11-15" } });
  await type(view.ncf, "E310000000099");
  await type(view.date, "18/11/2026");
  const button = view.restore("paid_on")!;
  assert.equal(button.disabled, false);
  assert.equal(button.getAttribute("aria-label"), "Restaurar: 12 Nov 2026", "the last value the server gave, while its preview is on the way");
  await settle();
  assert.equal(await tooltip(view.restore("paid_on")!), "Restaurar: 15 Nov 2026", "the server's linked value for this draft");
  assert.deepEqual(view.drafts.at(-1)!.override_inherited, ["paid_on"]);
  await act(async () => view.restore("paid_on")!.click());
  assert.equal(view.date.value, "15 Nov 2026");
  assert.ok(view.linked("paid_on"));
  assert.equal(view.restore("paid_on"), null);
  assert.equal(view.ncf.value, "E310000000099");
  assert.deepEqual(view.writes, [], "Restaurar saves nothing");
  await settle();
  assert.deepEqual(view.drafts.at(-1)!.restore_inherited, ["paid_on"]);
  await view.save();
  assert.equal(view.writes.length, 1);
  assert.equal(view.writes[0].declaration.modified_ncf, "E310000000099");
  assert.deepEqual(view.writes[0].montos, { restore_inherited: ["paid_on"] });
});

test("Restaurar on a saved override saves nothing, and Guardar sends the restore", async () => {
  const base = await dossier(); base.inheritance.goods_amount.inherited = false;
  const view = await editing(base);
  const button = view.restore("goods_amount")!;
  assert.equal(button.getAttribute("aria-label"), "Restaurar: RD$ 1,000.00");
  assert.equal(await tooltip(button), "Restaurar: RD$ 1,000.00");
  assert.equal(button.disabled, false);
  await act(async () => button.click());
  await settle();
  assert.ok(view.linked("goods_amount"));
  assert.deepEqual(view.writes, [], "Restaurar saves nothing");
  await view.save();
  assert.deepEqual(view.writes[0].montos, { restore_inherited: ["goods_amount", "services_amount"] });
});

test("Restaurar is disabled only while a save is in flight", async () => {
  const base = await dossier(); base.inheritance.goods_amount.inherited = false;
  let release = () => {};
  const view = await editing(base, { fiscal: () => new Promise<BusinessDossier>((resolve) => { release = () => resolve(base); }) });
  await type(view.date, "18/11/2026");
  assert.equal(view.restore("paid_on")!.disabled, false, "an unsaved edit does not disable it");
  assert.equal(view.restore("goods_amount")!.disabled, false, "nor does a preview on the way");
  await view.save();
  assert.equal(view.restore("paid_on")!.disabled, true, "disabled while the save is in flight");
  assert.equal(view.restore("goods_amount")!.disabled, true);
  await act(async () => release());
});

const splitFields: DgiiFields = { "606": [...fields["606"], { name: "services_amount", label: "", kind: "money", options: [] }], "607": [] };
/** A purchase whose goods and services the server pairs, linked or held apart at 900 and 100. */
async function split(inherited: boolean, values?: Record<string, string | null>) {
  const base = await dossier();
  base.dgii = { ...base.dgii!, goods_amount: inherited ? "1000.00" : "900.00", services_amount: inherited ? null : "100.00" };
  base.inheritance = { ...base.inheritance, goods_amount: { field: "net_amount", value: "1000.00", inherited, paired_with: ["services_amount"] }, services_amount: { field: "net_amount", value: null, inherited, paired_with: ["goods_amount"] } };
  return editing(base, { fields: splitFields, values });
}

test("Restaurar on one side puts back every field the server pairs with it, at the server's values", async () => {
  const view = await split(false, { goods_amount: "700.00", services_amount: "300.00" });
  await act(async () => view.restore("goods_amount")!.click());
  assert.deepEqual([view.amount("goods_amount").value, view.amount("services_amount").value], ["1,000.00", ""], "the last values the server gave");
  await settle();
  assert.deepEqual(view.drafts.at(-1)!.restore_inherited?.toSorted(), ["goods_amount", "services_amount"]);
  assert.deepEqual([view.amount("goods_amount").value, view.amount("services_amount").value], ["700.00", "300.00"], "the server's linked values for this draft");
  assert.ok(view.linked("goods_amount") && view.linked("services_amount"));
  assert.deepEqual(view.writes, []);
  await view.save();
  assert.deepEqual(view.writes[0].montos?.restore_inherited?.toSorted(), ["goods_amount", "services_amount"]);
  assert.equal(view.writes[0].montos?.override_inherited, undefined);
});

test("typing one side holds apart every field the server pairs with it, also after a restore", async () => {
  const view = await split(false);
  await act(async () => view.restore("goods_amount")!.click());
  await settle();
  await view.enter("services_amount", "600");
  assert.ok(view.restore("goods_amount"), "goods is held apart with services");
  assert.equal(view.amount("goods_amount").value, "1,000.00", "and keeps the value it showed");
  await view.save();
  assert.deepEqual(view.writes[0].montos?.override_inherited?.toSorted(), ["goods_amount", "services_amount"]);
  assert.equal(view.writes[0].montos?.restore_inherited, undefined);
  assert.deepEqual([view.writes[0].declaration.goods_amount, view.writes[0].declaration.services_amount], ["1000.00", "600"]);
});

test("the fiscal form names no goods or services field: the pairing is the server's", async () => {
  const source = await Bun.file(new URL("../components/business-app/FiscalDeclarationEditor.tsx", import.meta.url)).text();
  assert.doesNotMatch(source, /goods_amount|services_amount|AMOUNT_SIDES/);
});

test("Restaurar to an empty date source clears invalid typed text and leaves no hidden error", async () => {
  const base = await dossier(); base.inheritance.paid_on = { field: "occurred_on", value: null, inherited: true, paired_with: [] };
  const view = await editing(base);
  await type(view.date, "99/99/2026");
  assert.equal(view.date.value, "99/99/2026");
  await act(async () => view.restore("paid_on")!.click());
  assert.equal(view.date.value, "");
  assert.equal(view.date.getAttribute("aria-invalid"), "false");
  await view.save();
  assert.equal(view.host.querySelector('[role="alert"]'), null);
  assert.equal(view.writes[0].declaration.paid_on, null);
  assert.deepEqual(view.writes[0].montos, { restore_inherited: ["paid_on"] });
});

test("switching the form clears typed text that never became a value", async () => {
  const base = await dossier(); base.inheritance = {}; base.dgii = { ...base.dgii!, form: "606" }; base.facts.kind = { ...base.facts.kind, state: "unknown" };
  const both: DgiiFields = { "606": [{ name: "paid_on", label: "", kind: "date", options: [] }], "607": [{ name: "paid_on", label: "", kind: "date", options: [] }] };
  const host = await mount(<FiscalDeclarationEditor dossier={base} fields={both} disabled={false} reviewFiscal={async () => base} onChanged={noop} onBusy={noop} onDirty={noop} />);
  await type(host.querySelector<HTMLInputElement>("#fiscal-declaration-paid_on")!, "99/99/2026");
  const select = [...host.querySelectorAll("select")].find((element) => [...element.options].some((option) => option.value === "607"))!;
  await act(async () => { select.value = "607"; select.dispatchEvent(new Event("change", { bubbles: true })); });
  assert.equal(host.querySelector<HTMLInputElement>("#fiscal-declaration-paid_on")!.value, "");
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
    goods_amount: { field: "net_amount", value: null, inherited: false, paired_with: ["services_amount"] },
    paid_on: { field: "occurred_on", value: null, inherited: false, paired_with: [] },
  } };
  const host = await mount(<FiscalDeclarationEditor dossier={empty} fields={fields} disabled={false} reviewFiscal={async () => empty} onChanged={noop} onBusy={noop} onDirty={noop} />);
  const label = (field: string) => host.querySelector(`[data-restore-inherited="${field}"]`)?.getAttribute("aria-label");
  assert.equal(label("goods_amount"), "Restaurar: -");
  assert.equal(label("paid_on"), "Restaurar: -");
});

test("a field that follows a code, a text or a date names its source and restores to that value", async () => {
  const base = await dossier();
  const linkedFields: DgiiFields = { "606": [...fields["606"], { name: "id_type", label: "", kind: "select", options: ["1", "2"] }], "607": [] };
  const links = { id_type: { field: "rnc", value: "1", paired_with: [] }, modified_ncf: { field: "original_ncf", value: "E310000000007", paired_with: [] }, paid_on: { field: "occurred_on", value: "2026-11-12", paired_with: [] } } as const;
  const state = (inherited: boolean): BusinessDossier => ({ ...base, inheritance: { ...base.inheritance, ...Object.fromEntries(Object.entries(links).map(([name, link]) => [name, { ...link, inherited }])) } });
  const editor = (value: BusinessDossier) => <FiscalDeclarationEditor dossier={value} fields={linkedFields} disabled={false} reviewFiscal={async () => value} onChanged={noop} onBusy={noop} onDirty={noop} />;
  const linked = await mount(editor(state(true)));
  const from = (field: string) => linked.querySelector(`[data-inherited="${field}"]`)?.getAttribute("aria-label");
  assert.deepEqual([from("id_type"), from("modified_ncf"), from("paid_on")], ["Viene de RNC", "Viene de NCF de la compra original", "Viene de Fecha del comprobante"]);
  assert.equal(linked.querySelector<HTMLSelectElement>('[name="id_type"]')?.value, "1");
  assert.equal(linked.querySelector<HTMLInputElement>('[name="modified_ncf"]')?.value, "E310000000007");
  await cleanup();
  const overridden = await mount(editor(state(false)));
  const restore = (field: string) => overridden.querySelector(`[data-restore-inherited="${field}"]`)?.getAttribute("aria-label");
  assert.equal(restore("id_type"), `Restaurar: ${es.business.dgii.option.id_type["1"]}`);
  assert.equal(restore("modified_ncf"), "Restaurar: E310000000007");
  assert.equal(restore("paid_on"), "Restaurar: 12 Nov 2026");
});

test("a linked field shows its link icon only while it holds a value", async () => {
  const base = await dossier();
  const link = { field: "net_amount", value: null, inherited: true, paired_with: [] } as const;
  const linked: BusinessDossier = { ...base, dgii: { ...base.dgii!, goods_amount: "1000.00", services_amount: null, legal_tip: null }, inheritance: { ...base.inheritance, goods_amount: { ...link, value: "1000.00", paired_with: ["services_amount"] }, services_amount: { ...link, paired_with: ["goods_amount"] }, legal_tip: { ...link, field: "legal_tip" } } };
  const montos: DgiiFields = { "606": [...fields["606"], ...(["services_amount", "legal_tip"] as const).map((name) => ({ name, label: "", kind: "money" as const, options: [] }))], "607": [] };
  const host = await mount(<FiscalDeclarationEditor dossier={linked} fields={montos} disabled={false} reviewFiscal={async () => linked} onChanged={noop} onBusy={noop} onDirty={noop} />);
  assert.ok(host.querySelector('[data-inherited="goods_amount"]'));
  for (const field of ["services_amount", "legal_tip"]) {
    assert.ok(host.querySelector(`[name="${field}"], [data-testid="fiscal-declaration-${field}"]`));
    assert.equal(host.querySelector(`[data-inherited="${field}"]`), null);
    assert.equal(host.querySelector(`[data-restore-inherited="${field}"]`), null);
  }
});

for (const currency of ["DOP", "USD", "EUR", null]) test(`Montos names ${currency ?? "missing currency"} once and rows contain only numbers`, async () => {
  const base = await dossier();
  base.facts.currency = currency ? known(currency) : { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
  const host = await mount(<ReceiptRecordFacts dossier={base} accounts={[]} />);
  const block = montos(host);
  const picker = block.querySelector('[data-testid="montos-currency"]')!;
  assert.equal(picker.textContent, currency ?? "Elegir");
  assert.equal(picker.getAttribute("aria-label"), `Moneda: ${currency ?? "Falta la moneda"}`);
  assert.equal(picker.getAttribute("data-missing"), currency ? null : "true");
  assert.doesNotMatch(block.querySelector("ul")!.textContent!, /RD\$|US\$|€/);
});
