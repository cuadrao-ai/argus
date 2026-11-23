import assert from "node:assert/strict";
import { test } from "bun:test";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import type { BusinessDossier } from "@/lib/business-dossier";

// The sample answers a purchase's 606 in the server's shape: `written_from` and `inheritance_state`
// (amount_inheritance.py), `net_amount` (purchase_review.py) and `purchase_calculated` (dgii_validation.py).

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
  assert.deepEqual([dossier.dgii ?? null, dossier.inheritance, dossier.dgii_calculated], [null, {}, null]);
  assert.deepEqual(dossier.net_amount, { amount: "3450.00", source: "calculated" });
});

test("the links follow the sample's writes: a held field stays apart until it is restored, and an amount follows its source", async () => {
  const { source, receipt, dossier } = await sample("rcpt-listo-imprenta");
  const fiscal = { rnc: dossier.facts.fiscal!.rnc.value, ncf: dossier.facts.fiscal!.ncf.value, itbis: dossier.facts.fiscal!.itbis.value };
  const later = "2026-12-01";
  const held = await source.reviewFiscal!(dossier.draft_id, dossier.version, { fiscal, declaration: { ...dossier.dgii!, paid_on: later }, montos: { override_inherited: ["paid_on"] } }, "hold-paid-on");
  assert.deepEqual([held.dgii?.paid_on, held.inheritance?.paid_on], [later, link("occurred_on", receipt.occurred_on, false)]);
  const restored = await source.reviewFiscal!(held.draft_id, held.version, { fiscal, declaration: held.dgii!, montos: { restore_inherited: ["paid_on"] } }, "restore-paid-on");
  assert.deepEqual([restored.dgii?.paid_on, restored.inheritance?.paid_on], [receipt.occurred_on, link("occurred_on", receipt.occurred_on)]);
  const edited = await source.reviewMontos!(restored.draft_id, restored.version, { net_amount: { state: "known", value: "3900.00" } }, "edit-subtotal");
  assert.deepEqual(edited.net_amount, { amount: "3900.00", source: "edited" });
  assert.deepEqual([edited.dgii?.services_amount, edited.dgii_calculated?.billed_amount], ["3900.00", "3900.00"]);
  assert.deepEqual(edited.review_flags, [{ code: "amounts_mismatch", field: "amount", confirm: false, difference: "100.00" }], "Total no longer equals its parts");
});

/** The server's rule after any write: a linked field that follows its source holds that source's value, and the calculated total is the two sides it declares. */
function assertInStep(dossier: BusinessDossier, step: string) {
  const cents = (value: unknown) => Math.round(Number(value ?? 0) * 100);
  for (const [name, state] of Object.entries(dossier.inheritance ?? {})) {
    if (!state.inherited) continue;
    const held = dossier.dgii?.[name] ?? null;
    const money = ["net_amount", "itbis", "legal_tip"].includes(state.field);
    assert.ok(held === null || state.value === null ? held === state.value : money ? cents(held) === cents(state.value) : held === state.value, `${step}: ${name} is ${held}, its source says ${state.value}`);
  }
  assert.equal(cents(dossier.dgii_calculated?.billed_amount), cents(dossier.dgii?.services_amount) + cents(dossier.dgii?.goods_amount), `${step}: Total facturado`);
}

async function approved(receiptId: string, before?: (opened: Awaited<ReturnType<typeof sample>>) => Promise<BusinessDossier>) {
  const opened = await sample(receiptId);
  const reviewed = before ? await before(opened) : opened.dossier;
  const taken = Object.fromEntries(Object.entries(reviewed.declaration_suggestions ?? {}).filter(([, suggestion]) => suggestion));
  const dossier = await opened.source.approveDraft!(reviewed.draft_id, reviewed.version, `approve-${receiptId}`, "record_expense", { suggestions: taken });
  assert.equal(dossier.review_state, "accepted");
  assertInStep(dossier, "approved");
  return { ...opened, dossier };
}
const fiscalOf = (dossier: BusinessDossier) => ({ rnc: dossier.facts.fiscal!.rnc.value, ncf: dossier.facts.fiscal!.ncf.value, itbis: dossier.facts.fiscal!.itbis.value });

test("an approved record's linked amount follows a later Subtotal, and the save is kept", async () => {
  const { source, dossier } = await approved("rcpt-listo-imprenta");
  assert.deepEqual([dossier.dgii?.services_amount, dossier.dgii_calculated?.billed_amount], ["4000.00", "4000.00"]);
  const edited = await source.reviewMontos!(dossier.draft_id, dossier.version, { net_amount: { state: "known", value: "3900.00" } }, "approved-subtotal");
  assertInStep(edited, "Subtotal edited");
  assert.deepEqual([edited.dgii?.services_amount, edited.dgii_calculated?.billed_amount, edited.inheritance?.services_amount], ["3900.00", "3900.00", link("net_amount", "3900.00", true, ["goods_amount"])]);
  const reread = await source.dossier!(dossier.draft_id) as BusinessDossier;
  assert.deepEqual([reread.dgii, reread.dgii_calculated], [edited.dgii, edited.dgii_calculated]);
});

test("an approved record keeps an amount a person holds apart, while its other links follow", async () => {
  const { source, dossier } = await approved("rcpt-listo-imprenta", ({ source, dossier }) => source.reviewFiscal!(dossier.draft_id, dossier.version, { fiscal: fiscalOf(dossier), declaration: { ...dossier.dgii!, services_amount: "3500.00" }, montos: { override_inherited: ["services_amount"] } }, "hold-services"));
  const subtotal = await source.reviewMontos!(dossier.draft_id, dossier.version, { net_amount: { state: "known", value: "3900.00" } }, "held-subtotal");
  assertInStep(subtotal, "Subtotal edited");
  assert.deepEqual([subtotal.dgii?.services_amount, subtotal.dgii?.goods_amount, subtotal.inheritance?.services_amount?.inherited, subtotal.dgii_calculated?.billed_amount], ["3500.00", null, false, "3500.00"]);
  const taxed = await source.reviewFiscal!(subtotal.draft_id, subtotal.version, { fiscal: { ...fiscalOf(subtotal), itbis: "702.00" }, declaration: subtotal.dgii! }, "held-itbis");
  assertInStep(taxed, "ITBIS edited");
  assert.deepEqual([taxed.dgii?.itbis, taxed.dgii?.services_amount, taxed.dgii_calculated], ["702.00", "3500.00", { billed_amount: "3500.00", itbis_advance: "702.00" }]);
});

test("an approved record's amount changes side with its Tipo de gasto", async () => {
  const { source, dossier } = await approved("rcpt-listo-imprenta");
  const goods = await source.reviewPurchase!(dossier.draft_id, dossier.version, { category: "09" }, "approved-goods");
  assertInStep(goods, "Tipo de gasto changed");
  assert.deepEqual([goods.dgii?.services_amount, goods.dgii?.goods_amount, goods.dgii_calculated?.billed_amount], [null, "4000.00", "4000.00"]);
});

test("an approved record's Fecha de pago follows a corrected date unless a person holds it apart", async () => {
  const corrected = "2026-10-02";
  const followed = await approved("rcpt-listo-imprenta");
  assert.equal(followed.dossier.dgii?.paid_on, followed.receipt.occurred_on);
  const moved = await followed.source.reviewDraft!(followed.dossier.draft_id, followed.dossier.version, { occurred_on: { state: "known", value: corrected } }, "approved-date");
  assert.equal(moved.dgii?.paid_on, corrected);
  const held = await approved("rcpt-listo-limpieza");
  const kept = await held.source.reviewDraft!(held.dossier.draft_id, held.dossier.version, { occurred_on: { state: "known", value: corrected } }, "held-date");
  assert.equal(kept.dgii?.paid_on, held.dossier.dgii?.paid_on);
  assert.notEqual(kept.dgii?.paid_on, corrected);
  const later = "2026-12-01";
  const stated = await followed.source.reviewFiscal!(moved.draft_id, moved.version, { fiscal: fiscalOf(moved), declaration: { ...moved.dgii!, paid_on: later } }, "approved-paid-on");
  const again = await followed.source.reviewDraft!(stated.draft_id, stated.version, { occurred_on: { state: "known", value: "2026-10-03" } }, "approved-date-again");
  assert.equal(again.dgii?.paid_on, later, "a Fecha de pago a person gave after approval is theirs");
});

test("every write to an open sample leaves its links in step", async () => {
  const { source, dossier } = await sample("rcpt-listo-gasolinera");
  const subtotal = await source.reviewMontos!(dossier.draft_id, dossier.version, { net_amount: { state: "known", value: "1700.00" } }, "open-subtotal");
  assertInStep(subtotal, "Subtotal edited");
  assert.equal(subtotal.dgii?.goods_amount, "1700.00");
  const services = await source.reviewPurchase!(subtotal.draft_id, subtotal.version, { category: "02" }, "open-services");
  assertInStep(services, "Tipo de gasto changed");
  assert.deepEqual([services.dgii?.services_amount, services.dgii?.goods_amount], ["1700.00", null]);
  const taxed = await source.reviewFiscal!(services.draft_id, services.version, { fiscal: { ...fiscalOf(services), itbis: "306.00" }, declaration: services.dgii! }, "open-itbis");
  assertInStep(taxed, "ITBIS edited");
  assert.equal(taxed.dgii?.itbis, "306.00");
});

test("an amount the sample filled for a chosen Tipo de gasto stays linked", async () => {
  const { source, dossier } = await sample("rcpt-listo-suplidora");
  const chosen = await source.reviewPurchase!(dossier.draft_id, dossier.version, { category: "02" }, "choose-services");
  assertInStep(chosen, "Tipo de gasto chosen");
  assert.deepEqual([chosen.dgii?.services_amount, chosen.inheritance?.services_amount, chosen.inheritance?.goods_amount?.inherited], ["7500.00", link("net_amount", "7500.00", true, ["goods_amount"]), true]);
  const subtotal = await source.reviewMontos!(chosen.draft_id, chosen.version, { net_amount: { state: "known", value: "7000.00" } }, "chosen-subtotal");
  assertInStep(subtotal, "Subtotal edited");
  assert.deepEqual([subtotal.dgii?.services_amount, subtotal.dgii_calculated?.billed_amount], ["7000.00", "7000.00"]);
  const goods = await source.reviewPurchase!(subtotal.draft_id, subtotal.version, { category: "09" }, "chosen-goods");
  assertInStep(goods, "Tipo de gasto changed");
  assert.deepEqual([goods.dgii?.services_amount, goods.dgii?.goods_amount], [null, "7000.00"]);
});

const standing = (dossier: BusinessDossier) => [dossier.bandeja_group?.group, dossier.listo_gaps, dossier.confirmable];
const refusal = (attempt: Promise<unknown>) => attempt.then(() => null, (error: { code?: string }) => error.code);

test("a Subtotal that no longer adds up takes the sample out of Listos until a person accepts over it", async () => {
  const { source, dossier } = await sample("rcpt-listo-imprenta");
  assert.deepEqual(standing(dossier), ["listo", [], []]);
  const off = await source.reviewMontos!(dossier.draft_id, dossier.version, { net_amount: { state: "known", value: "3900.00" } }, "subtotal-off");
  assert.deepEqual(standing(off), ["attention", ["review_flag"], ["review_flag"]]);
  assert.equal(off.bandeja_group?.reason, "review_flag");
  assert.equal(await refusal(source.approveDraft!(off.draft_id, off.version, "approve-unnamed", "record_expense")), "not_listo");
  const fixed = await source.reviewMontos!(off.draft_id, off.version, { net_amount: { state: "known", value: "4000.00" } }, "subtotal-back");
  assert.deepEqual(standing(fixed), ["listo", [], []], "the write that fixes it clears it");
  const again = await source.reviewMontos!(fixed.draft_id, fixed.version, { net_amount: { state: "known", value: "3900.00" } }, "subtotal-off-again");
  const accepted = await source.approveDraft!(again.draft_id, again.version, "approve-named", "record_expense", { acceptGaps: ["review_flag"] });
  assert.equal(accepted.review_state, "accepted");
});

test("a gap the sample seeds stays beside a new one, in the rule's order", async () => {
  const { source, dossier } = await sample("rcpt-remitente");
  assert.deepEqual(standing(dossier), ["attention", ["unverified_sender"], []]);
  const off = await source.reviewMontos!(dossier.draft_id, dossier.version, { net_amount: { state: "known", value: "800.00" } }, "sender-subtotal");
  assert.deepEqual(standing(off), ["attention", ["review_flag", "unverified_sender"], ["review_flag"]]);
});

for (const [receiptId, gap, fiscal] of [
  ["rcpt-falta-rnc", "missing_rnc", { rnc: "131999888" }],
  ["rcpt-falta-ncf", "missing_ncf", { ncf: "B0100000123" }],
  ["rcpt-ferreteria", "sin_comprobante", { rnc: "131999888", ncf: "B0100000123" }],
] as const) {
  test(`the seeded ${gap} gap ends with the write that gives what it lacked`, async () => {
    const { source, dossier } = await sample(receiptId);
    assert.deepEqual(standing(dossier), ["attention", [gap], [gap]]);
    const held = dossier.facts.fiscal;
    const given = await source.reviewFiscal!(dossier.draft_id, dossier.version, { fiscal: { rnc: held?.rnc.value ?? null, ncf: held?.ncf.value ?? null, itbis: held?.itbis.value ?? null, ...fiscal }, declaration: dossier.dgii ?? { form: "606" } }, `give-${gap}`);
    assert.deepEqual(standing(given), ["listo", [], []]);
  });
}

test("a date a person clears takes the sample out of Listos, and nobody can accept over it", async () => {
  const { source, dossier, receipt } = await sample("rcpt-listo-imprenta");
  const cleared = await source.reviewDraft!(dossier.draft_id, dossier.version, { occurred_on: { state: "unknown", value: null } }, "clear-date");
  assert.deepEqual(standing(cleared), ["attention", ["missing_date"], []]);
  assert.equal(await refusal(source.approveDraft!(cleared.draft_id, cleared.version, "approve-undated", "record_expense", { acceptGaps: ["missing_date"] })), "not_listo");
  const given = await source.reviewDraft!(cleared.draft_id, cleared.version, { occurred_on: { state: "known", value: receipt.occurred_on! } }, "give-date");
  assert.deepEqual(standing(given), ["listo", [], []]);
});
