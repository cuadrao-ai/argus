import assert from "node:assert/strict";
import { test } from "bun:test";
import { act } from "react";
import { createDossierFixtures } from "@/components/business-app/dossier-fixtures";
import type { DgiiFields } from "@/lib/business-dgii";
import type { BusinessDossier } from "@/lib/business-dossier";
import { mountEditor } from "./fixtures/fiscal-editor";

/** Every field the server's form lists, in its order. */
const serverFields = (): Promise<DgiiFields> => createDossierFixtures([{ id: "cash", type: "cash", currency: "DOP", nickname: "PRÁCTICA caja" }]).dgiiFields();

const LINKS: NonNullable<BusinessDossier["inheritance"]> = {
  id_type: { field: "rnc", value: "1", inherited: true, paired_with: [] },
  paid_on: { field: "occurred_on", value: "2026-10-09", inherited: true, paired_with: [] },
  goods_amount: { field: "net_amount", value: "2923.73", inherited: true, paired_with: ["services_amount"] },
  services_amount: { field: "net_amount", value: null, inherited: true, paired_with: ["goods_amount"] },
  itbis: { field: "itbis", value: "526.27", inherited: true, paired_with: [] },
  legal_tip: { field: "legal_tip", value: "292.37", inherited: true, paired_with: [] },
};
const purchase = (dgii: Record<string, string | boolean | null> = {}) => (dossier: BusinessDossier): BusinessDossier => ({ ...dossier, inheritance: LINKS, dgii: { form: "606", id_type: "1", paid_on: "2026-10-09", goods_amount: "2923.73", itbis: "526.27", legal_tip: "292.37", ...dgii } });
const sale = (dossier: BusinessDossier): BusinessDossier => ({ ...dossier, document_type: "venta", inheritance: {}, dgii: { form: "607" }, facts: { ...dossier.facts, kind: { ...dossier.facts.kind, state: "known", value: "income" } as never } });

const cards = (host: Element) => [...host.querySelectorAll<HTMLElement>("[data-group]")].map((card) => ({
  title: card.querySelector("h3")?.textContent,
  rows: [...card.querySelectorAll<HTMLElement>("ul:not([hidden]) > [data-field]")].map((row) => row.firstElementChild?.textContent),
  line: card.querySelector(":scope > p")?.textContent ?? null,
  add: card.querySelector<HTMLButtonElement>(":scope > div > button[aria-expanded]")?.textContent ?? null,
}));
const status = (host: Element, name: string) => host.querySelector(`[data-testid="row-status-${name}"]`);
const fold = (host: Element, group: string) => host.querySelector<HTMLButtonElement>(`[data-group="${group}"] > div > button[aria-expanded]`);

test("a regular purchase shows the agreed cards and rows, by the board's names and in its order", async () => {
  const view = await mountEditor({ fields: await serverFields(), dossier: purchase() });
  try {
    assert.deepEqual(cards(view.host), [
      { title: "Reporte 606", rows: ["Tipo de ID", "Fecha de pago"], line: null, add: null },
      { title: "Monto facturado", rows: ["Servicios", "Bienes"], line: null, add: null },
      { title: "ITBIS", rows: ["ITBIS facturado", "ITBIS llevado al costo", "ITBIS sujeto a proporcionalidad"], line: null, add: null },
      { title: "Retenciones", rows: [], line: "Sin retenciones.", add: "Agregar retención" },
      { title: "Otros impuestos", rows: [], line: "Sin otros impuestos.", add: "Agregar impuesto" },
    ]);
    for (const gone of ["rnc", "ncf", "category", "payment_method", "legal_tip", "modified_ncf", "itbis_perceived", "income_perceived"]) assert.equal(view.host.querySelector(`[data-field="${gone}"]`), null, gone);
    assert.equal(view.host.querySelector('[data-fact="actual_refund"]'), null, "the refund question belongs to a credit note");
    assert.equal(view.host.querySelector('[data-fact="form"]'), null);
    assert.equal(view.host.querySelector("form, p:not([class])"), null, "no form buttons and no help paragraph");
  } finally { await view.dispose(); }
});

test("the folded cards open into the board's rows", async () => {
  const view = await mountEditor({ fields: await serverFields(), dossier: purchase() });
  try {
    await act(async () => fold(view.host, "retentions")!.click());
    await act(async () => fold(view.host, "other")!.click());
    const [, , , retentions, other] = cards(view.host);
    assert.deepEqual(retentions, { title: "Retenciones", rows: ["Tipo de Retención en ISR", "ITBIS Retenido", "Monto Retención Renta"], line: null, add: "Quitar" });
    assert.deepEqual(other, { title: "Otros impuestos", rows: ["Impuesto Selectivo al Consumo", "Otros Impuestos/Tasas"], line: null, add: "Quitar" });
    await act(async () => fold(view.host, "other")!.click());
    assert.equal(cards(view.host)[4].line, "Sin otros impuestos.");
    assert.equal(cards(view.host)[3].line, null, "each card folds on its own");
  } finally { await view.dispose(); }
});

test("Otros impuestos cannot fold while it holds a value", async () => {
  const saved = await mountEditor({ fields: await serverFields(), dossier: purchase({ selective_tax: "45.00" }) });
  try {
    assert.equal(fold(saved.host, "other"), null);
    assert.deepEqual(cards(saved.host)[4].rows, ["Impuesto Selectivo al Consumo", "Otros Impuestos/Tasas"]);
    assert.equal(saved.row("selective_tax").querySelector("[data-row-value]")?.textContent, "45.00");
  } finally { await saved.dispose(); }
  const typed = await mountEditor({ fields: await serverFields(), dossier: purchase() });
  try {
    await act(async () => fold(typed.host, "other")!.click());
    await typed.open("other_taxes");
    await typed.input("other_taxes", "10.00");
    assert.equal(fold(typed.host, "other"), null, "a typed value keeps it open");
    await typed.cancel("other_taxes");
    assert.equal(fold(typed.host, "other")?.textContent, "Quitar");
  } finally { await typed.dispose(); }
});

test("Tipo de ID reads from the number and nobody edits it here", async () => {
  const view = await mountEditor({ fields: await serverFields(), dossier: purchase() });
  try {
    const row = view.row("id_type");
    assert.equal(row.querySelector("[data-row-value]")?.textContent, "01 - RNC");
    assert.equal(row.querySelector("button"), null, "no pencil and no value to click");
    assert.equal(status(view.host, "id_type")?.getAttribute("data-status"), "link");
    assert.equal(status(view.host, "id_type")?.getAttribute("aria-label"), "Sale del número");
  } finally { await view.dispose(); }
  const apart = await mountEditor({ fields: await serverFields(), dossier: (dossier) => { const next = purchase({ id_type: "2" })(dossier); return { ...next, inheritance: { ...next.inheritance, id_type: { field: "rnc", value: "1", inherited: false, paired_with: [] } } }; } });
  try {
    assert.equal(apart.row("id_type").querySelector("button"), null, "a saved type that differs still offers no edit here");
    assert.equal(status(apart.host, "id_type"), null, "and the server's word decides the link");
  } finally { await apart.dispose(); }
});

test("each linked row names its source, and an edit to ITBIS facturado holds it apart until Restaurar", async () => {
  const view = await mountEditor({ fields: await serverFields(), dossier: purchase() });
  try {
    const source = (name: string) => status(view.host, name)?.getAttribute("aria-label");
    assert.deepEqual([source("paid_on"), source("goods_amount"), source("itbis")], ["Heredado de la fecha", "Sale del subtotal", "Sale de Montos"]);
    assert.equal(status(view.host, "services_amount"), null, "an empty side shows no link");
    assert.equal(view.row("itbis").querySelector("[data-row-value]")?.textContent, "526.27");
    await view.open("itbis");
    await view.input("itbis", "500.00");
    assert.equal(status(view.host, "itbis"), null, "the edit removes the link");
    const restore = view.row("itbis").querySelector<HTMLButtonElement>('[data-restore-inherited="itbis"]');
    assert.equal(restore?.getAttribute("aria-label"), "Restaurar: RD$ 526.27");
    await view.save("itbis");
    const sent = view.writes[0].input as unknown as { dgii: { declaration: Record<string, unknown> }; montos?: unknown };
    assert.equal(sent.dgii.declaration.itbis, "500.00");
    assert.deepEqual(sent.montos, { override_inherited: ["itbis"] });
  } finally { await view.dispose(); }
  const held = await mountEditor({ fields: await serverFields(), dossier: (dossier) => { const next = purchase({ itbis: "500.00" })(dossier); return { ...next, inheritance: { ...next.inheritance, itbis: { field: "itbis", value: "526.27", inherited: false, paired_with: [] } } }; } });
  try {
    assert.equal(status(held.host, "itbis"), null);
    await act(async () => held.row("itbis").querySelector<HTMLButtonElement>('[data-restore-inherited="itbis"]')!.click());
    assert.equal(status(held.host, "itbis")?.getAttribute("aria-label"), "Sale de Montos", "Restaurar shows the link again");
    await held.save("itbis");
    assert.deepEqual((held.writes[0].input as unknown as { montos?: unknown }).montos, { restore_inherited: ["itbis"] });
  } finally { await held.dispose(); }
});

test("a save sends every field the tab leaves out exactly as the record holds it", async () => {
  const view = await mountEditor({ fields: await serverFields(), dossier: (dossier) => { const next = purchase({ itbis_perceived: "0.00", income_perceived: null })(dossier); return { ...next, inheritance: { ...next.inheritance, legal_tip: { ...LINKS.legal_tip, inherited: false } }, dgii: { ...next.dgii!, legal_tip: "300.00" } }; } });
  try {
    await view.open("itbis_cost");
    await view.input("itbis_cost", "12.00");
    await view.save("itbis_cost");
    const { declaration } = view.writes[0].input.dgii;
    assert.equal(declaration.itbis_cost, "12.00");
    assert.deepEqual([declaration.legal_tip, declaration.itbis_perceived, declaration.income_perceived, declaration.modified_ncf, declaration.actual_refund, declaration.purchase_activity_id], ["300.00", "0.00", null, null, false, null]);
  } finally { await view.dispose(); }
});

test("a credit note keeps NCF modificado and the refund question", async () => {
  const view = await mountEditor({ fields: await serverFields(), dossier: (dossier) => ({ ...purchase()(dossier), listo_gaps: ["credit_note"] }) });
  try {
    assert.deepEqual(cards(view.host)[0].rows, ["Tipo de ID", "Fecha de pago", "NCF modificado"]);
    assert.ok(view.host.querySelector('[data-fact="actual_refund"]'));
  } finally { await view.dispose(); }
  const saved = await mountEditor({ fields: await serverFields(), dossier: purchase({ modified_ncf: "B0100000001" }) });
  try {
    assert.equal(saved.row("modified_ncf").querySelector("[data-row-value]")?.textContent, "B0100000001", "a saved reference always shows");
  } finally { await saved.dispose(); }
});

/** The record's comprobante: its number decides whether it is a note. */
const numbered = (number: string, dgii: Record<string, string | boolean | null> = {}) => (dossier: BusinessDossier): BusinessDossier => {
  const next = purchase(dgii)(dossier);
  const fiscal = next.facts.fiscal!;
  const known = { ...fiscal.ncf, state: "known", value: number } as typeof fiscal.ncf;
  const none = { ...fiscal.ecf, state: "unknown", value: null } as typeof fiscal.ecf;
  return { ...next, listo_gaps: [], facts: { ...next.facts, fiscal: { ...fiscal, ncf: number.startsWith("E") ? none : known, ecf: number.startsWith("E") ? known : none } } };
};

for (const number of ["B0300000011", "E330000000011"]) test(`a debit note ${number} with no reference yet shows NCF modificado and saves it, with no refund question`, async () => {
  const view = await mountEditor({ fields: await serverFields(), dossier: numbered(number) });
  try {
    assert.deepEqual(cards(view.host)[0].rows, ["Tipo de ID", "Fecha de pago", "NCF modificado"]);
    assert.equal(view.host.querySelector('[data-fact="actual_refund"]'), null, "a debit note returns no money");
    await view.open("modified_ncf");
    await view.input("modified_ncf", "B0100000001");
    await view.save("modified_ncf");
    const { declaration } = view.writes[0].input.dgii;
    assert.deepEqual([declaration.modified_ncf, declaration.actual_refund, declaration.purchase_activity_id], ["B0100000001", false, null]);
    assert.equal(view.row("modified_ncf").querySelector("[data-row-value]")?.textContent, "B0100000001");
    assert.equal(view.host.querySelector('[data-fact="actual_refund"]'), null, "a saved reference does not make it a credit note");
  } finally { await view.dispose(); }
});

for (const number of ["B0400000011", "E340000000011"]) test(`a credit note ${number} shows NCF modificado and the refund question by its number alone`, async () => {
  const view = await mountEditor({ fields: await serverFields(), dossier: numbered(number) });
  try {
    assert.deepEqual(cards(view.host)[0].rows, ["Tipo de ID", "Fecha de pago", "NCF modificado"]);
    assert.ok(view.host.querySelector('[data-fact="actual_refund"]'));
  } finally { await view.dispose(); }
});

test("a regular purchase hides NCF modificado and the refund question whatever its number says of its series", async () => {
  for (const number of ["B0100000011", "E310000000011", "B1100000011"]) {
    const view = await mountEditor({ fields: await serverFields(), dossier: numbered(number) });
    try {
      assert.equal(view.host.querySelector('[data-field="modified_ncf"]'), null, number);
      assert.equal(view.host.querySelector('[data-fact="actual_refund"]'), null, number);
    } finally { await view.dispose(); }
  }
});

test("a sale shows every field of its form, with nothing folded", async () => {
  const fields = await serverFields();
  const view = await mountEditor({ fields, dossier: sale });
  try {
    const shown = [...view.host.querySelectorAll<HTMLElement>("ul:not([hidden]) > [data-field]")].map((row) => row.dataset.field);
    assert.deepEqual(shown.toSorted(), fields["607"].map((field) => field.name).filter((name) => !["rnc", "ncf"].includes(name)).toSorted());
    assert.equal(view.host.querySelector("button[aria-expanded]"), null);
    assert.equal(view.host.querySelector('[data-fact="actual_refund"]'), null);
  } finally { await view.dispose(); }
});
