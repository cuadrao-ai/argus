import assert from "node:assert/strict";
import { test } from "bun:test";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import type { BusinessDossier } from "@/lib/business-dossier";

// The sample states a purchase's 606 in the server's shape, value by value. It copies no server rule:
// a write keeps what was sent, and no linked or calculated value moves with it.

async function sample(receiptId: string) {
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const receipt = await source.receipt(receiptId);
  const dossier = await source.dossier!(receipt.draft_id!) as BusinessDossier;
  return { source, receipt, dossier };
}

/** Every field `PurchaseDeclaration` dumps for a purchase nobody answered, in its order. */
const declared = (over: Record<string, string | null>) => ({
  id_type: "1", modified_ncf: null, selective_tax: null, other_taxes: null, legal_tip: null, form: "606", category: null, category_suggested: false,
  paid_on: null, services_amount: null, goods_amount: null, itbis_withheld: null, itbis_proportionality: null, itbis_cost: null, itbis_perceived: null,
  income_withholding_type: null, income_withheld: null, income_perceived: null, payment_method: null, actual_refund: false, purchase_activity_id: null, ...over,
});
const link = (field: string, value: string | null, inherited = true, paired: string[] = []) => ({ field, value, inherited, paired_with: paired });

test("a read purchase with suggested answers serves the 606 its approval would save, each linked field at its source", async () => {
  const { receipt, dossier } = await sample("rcpt-listo-imprenta");
  const day = receipt.occurred_on!;
  assert.deepEqual(dossier.declaration_suggestions, { category: { value: "02", source: "last_choice" }, payment_method: { value: "03", source: "last_choice" } });
  // The suggestions stay beside their blank answers; the links already show what they give.
  assert.deepEqual(dossier.dgii, declared({ itbis: "720.00", paid_on: day, services_amount: "4000.00" }));
  assert.deepEqual(dossier.net_amount, { amount: "4000.00", source: "read" });
  assert.deepEqual(dossier.inheritance, {
    goods_amount: link("net_amount", null, true, ["services_amount"]),
    id_type: link("rnc", "1"),
    itbis: link("itbis", "720.00"),
    legal_tip: link("legal_tip", null),
    paid_on: link("occurred_on", day),
    services_amount: link("net_amount", "4000.00", true, ["goods_amount"]),
  });
  assert.deepEqual(dossier.dgii_calculated, { billed_amount: "4000.00", itbis_advance: "720.00" });
  assert.deepEqual(dossier.review_flags, [], "Total, Subtotal and ITBIS were read and add up");
});

test("a suggested goods type links Bienes, and a cash purchase links Fecha de pago", async () => {
  const { receipt, dossier } = await sample("rcpt-listo-gasolinera");
  assert.deepEqual([dossier.dgii?.goods_amount, dossier.dgii?.services_amount, dossier.dgii?.paid_on], ["1779.66", null, receipt.occurred_on]);
  assert.deepEqual(dossier.dgii_calculated, { billed_amount: "1779.66", itbis_advance: "320.34" });
});

test("a read purchase nobody suggested an answer for links only what its facts state", async () => {
  const { dossier } = await sample("rcpt-listo-suplidora");
  assert.deepEqual(dossier.dgii, declared({ itbis: "1350.00" }));
  assert.deepEqual([dossier.inheritance?.paid_on, dossier.inheritance?.services_amount?.value, dossier.inheritance?.goods_amount?.value], [link("occurred_on", null), null, null]);
  assert.deepEqual(dossier.dgii_calculated, { billed_amount: "0.00", itbis_advance: "1350.00" });
});

test("one sample holds Fecha de pago apart from the receipt's date, as a person's save leaves it", async () => {
  const { receipt, dossier } = await sample("rcpt-listo-limpieza");
  const held = dossier.inheritance?.paid_on;
  assert.deepEqual(held, link("occurred_on", receipt.occurred_on, false));
  assert.ok(dossier.dgii?.paid_on && dossier.dgii.paid_on !== receipt.occurred_on, "the saved date is the person's");
  assert.deepEqual(Object.entries(dossier.inheritance ?? {}).filter(([, state]) => !state.inherited).map(([name]) => name), ["paid_on"]);
  const save = dossier.history.at(-1)!;
  assert.deepEqual([save.actor.actor_kind, save.before_dgii ?? null, save.after_dgii?.paid_on], ["member", null, dossier.dgii.paid_on]);
  assert.deepEqual(save.before, save.after, "a fiscal save changes no fact");
  assert.ok(Date.parse(save.created_at) > Date.parse(dossier.history[0].created_at), "the save follows the read");
});

test("a record with no comprobante has no 606 and no links", async () => {
  const { dossier } = await sample("rcpt-ferreteria");
  assert.deepEqual([dossier.dgii ?? null, dossier.inheritance ?? {}, dossier.dgii_calculated ?? null], [null, {}, null]);
  assert.deepEqual(dossier.net_amount, { amount: "3450.00", source: "calculated" });
});

test("a sample write keeps what was sent and works nothing out: no linked or calculated value moves", async () => {
  const { source, dossier } = await sample("rcpt-listo-imprenta");
  const edited = await source.reviewMontos!(dossier.draft_id, dossier.version, { net_amount: { state: "known", value: "3900.00" } }, "edit-subtotal");
  assert.deepEqual(edited.net_amount, { amount: "3900.00", source: "edited" }, "the write's own value");
  assert.deepEqual([edited.dgii, edited.inheritance, edited.dgii_calculated, edited.review_flags, edited.amounts_check], [dossier.dgii, dossier.inheritance, dossier.dgii_calculated, dossier.review_flags, dossier.amounts_check]);
  assert.deepEqual([edited.bandeja_group?.group, edited.listo_gaps], ["listo", []], "and the sample decides no standing from the amounts");
  const chosen = await source.reviewPurchase!(edited.draft_id, edited.version, { category: "09" }, "choose-goods");
  assert.deepEqual([chosen.dgii?.category, chosen.dgii?.services_amount, chosen.dgii?.goods_amount, chosen.dgii_calculated], ["09", "4000.00", null, dossier.dgii_calculated]);
});

test("a sample write holds apart or links again only the fields it names, at the value the record states", async () => {
  const { source, receipt, dossier } = await sample("rcpt-listo-imprenta");
  const fiscal = { rnc: dossier.facts.fiscal!.rnc.value, ncf: dossier.facts.fiscal!.ncf.value, itbis: dossier.facts.fiscal!.itbis.value };
  const later = "2026-12-01";
  const held = await source.reviewFiscal!(dossier.draft_id, dossier.version, { fiscal, declaration: { ...dossier.dgii!, paid_on: later }, montos: { override_inherited: ["paid_on"] } }, "hold-paid-on");
  assert.deepEqual([held.dgii?.paid_on, held.inheritance?.paid_on], [later, link("occurred_on", receipt.occurred_on, false)]);
  assert.deepEqual({ ...held.inheritance, paid_on: null }, { ...dossier.inheritance, paid_on: null }, "no other link moves");
  const restored = await source.reviewFiscal!(held.draft_id, held.version, { fiscal, declaration: held.dgii!, montos: { restore_inherited: ["paid_on"] } }, "restore-paid-on");
  assert.deepEqual([restored.dgii?.paid_on, restored.inheritance?.paid_on], [receipt.occurred_on, link("occurred_on", receipt.occurred_on)]);
});
