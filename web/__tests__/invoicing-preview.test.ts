import { describe, test } from "bun:test";
import assert from "node:assert/strict";
import { correctionStatus, invoiceSettlement, invoiceState, invoicePreviewSeed, hundredths, invoiceEmailDraft, invoiceEmailErrors, invoiceDraftErrors, invoiceAmounts, invoiceReducer, matchesInvoice, newInvoice, validDraft } from "../components/business-app/invoicing/invoice-preview-model";

const draft = () => ({ ...newInvoice("one", "M-001"), customer: { id: "c1", name: "Cliente de muestra", email: "test@example.test", address: "", taxId: "" }, items: [{ id: "i1", description: "Servicio", quantity: "1", price: "100.00", tax: "0" }] });
describe("connected invoice preview", () => {
  test("keeps incomplete work as a draft without allowing issuance or overwriting issued invoices", () => {
    const incomplete = { ...newInvoice("one", "M-001"), notes: "Continue later" };
    const saved = invoiceReducer([], { type: "save", invoice: incomplete });
    assert.deepEqual(saved, [incomplete]);
    assert.deepEqual(invoiceReducer(saved, { type: "issue", id: "one" }), saved);
    const issued = { ...draft(), issuance: "issued" as const };
    assert.deepEqual(invoiceReducer([issued], { type: "save", invoice: incomplete }), [issued]);
  });
  test("one identity survives save, issue, preparation and two linked payments", () => {
    let state = invoiceReducer([], { type: "save", invoice: draft() });
    state = invoiceReducer(state, { type: "issue", id: "one" });
    state = invoiceReducer(state, { type: "prepare", id: "one", preparation: { channel: "email", email: "recipient@example.test" } });
    const payment = { id: "pay1", amount: 4000, currency: "DOP" as const, date: draft().issuedOn, method: "transfer" as const, reference: "" };
    state = invoiceReducer(state, { type: "pay", id: "one", payment });
    assert.deepEqual(invoiceAmounts(state[0]), { subtotal: 10000, discount: 0, tax: 0, total: 10000, paid: 4000, balance: 6000 });
    state = invoiceReducer(state, { type: "pay", id: "one", payment });
    assert.equal(state[0].payments.length, 1);
    state = invoiceReducer(state, { type: "pay", id: "one", payment: { ...payment, id: "pay2", amount: 6000 } });
    assert.equal(state.length, 1);
    assert.equal(invoiceAmounts(state[0])?.balance, 0);
    assert.equal(state[0].delivery, "prepared");
    assert.equal(state[0].deliveryPreparation?.email, "recipient@example.test");
    assert.equal(matchesInvoice(state[0], "paid"), true);
  });
  test("rejects overpayment, currency mismatch, draft payments and uncertain reissue", () => {
    const payment = { id: "p", amount: 10001, currency: "DOP" as const, date: draft().issuedOn, method: "cash" as const, reference: "" };
    const issued = { ...draft(), issuance: "issued" as const };
    for (const item of [draft(), issued]) assert.deepEqual(invoiceReducer([item], { type: "pay", id: "one", payment })[0].payments, []);
    assert.deepEqual(invoiceReducer([issued], { type: "pay", id: "one", payment: { ...payment, amount: 100, currency: "USD" } })[0].payments, []);
    const uncertain = { ...draft(), issuance: "uncertain" as const };
    assert.deepEqual(invoiceReducer([uncertain], { type: "issue", id: "one" }), [uncertain]);
  });
  test("validates bounded exact decimal inputs, dates and overlapping overdue scope", () => {
    assert.equal(hundredths("1,25"), 125);
    assert.equal(hundredths("10000000"), null);
    assert.equal(hundredths("1e6"), null);
    assert.equal(validDraft({ ...draft(), dueOn: "2026-02-30" }), false);
    const overdue = { ...draft(), issuance: "issued" as const, dueOn: "2020-01-01" };
    assert.equal(matchesInvoice(overdue, "overdue"), true);
    assert.equal(matchesInvoice(overdue, "outstanding"), true);
  });
  test("rounds each line in minor units and handles maximum supported products exactly", () => {
    const item = draft().items[0];
    assert.deepEqual(invoiceAmounts({ items: [{ ...item, quantity: "3", price: "0.05", tax: "10" }], payments: [] }), { subtotal: 15, discount: 0, tax: 2, total: 17, paid: 0, balance: 17 });
    assert.equal(invoiceAmounts({ items: [{ ...item, quantity: "1000", price: "9999999.99", tax: "100" }], payments: [] })?.total, 1999999998000);
  });
});

describe("invoice corrections", () => {
  const issued = () => ({ ...draft(), issuance: "issued" as const });
  const request = (kind: "full_cancellation" | "partial_credit" = "full_cancellation", amount = 10000) => ({ type: "correct" as const, id: "one", correction: { id: "c1", kind, amount, reason: "Error en el documento" } });
  const resolve = (outcome: "confirmed" | "failed", attempt = 1) => ({ type: "resolve_correction" as const, id: "one", correctionId: "c1", attempt, outcome });
  test("pending and failed preserve the original and cannot enter Void", () => {
    const original = issued();
    let state = invoiceReducer([original], request());
    for (const outcome of [undefined, "failed"] as const) {
      if (outcome) state = invoiceReducer(state, resolve(outcome));
      assert.equal(matchesInvoice(state[0], "void"), false);
      assert.equal(invoiceSettlement(state[0])?.balance, 10000);
      assert.deepEqual({ ...state[0], corrections: [] }, original);
    }
  });
  test("confirmed full cancellation is Void before paid, preserving invoice and payment evidence", () => {
    const original = { ...issued(), payments: [{ id: "p1", amount: 4000, currency: "DOP" as const, date: draft().issuedOn, method: "cash" as const, reference: "" }] };
    let state = invoiceReducer([original], request());
    state = invoiceReducer(state, resolve("confirmed"));
    assert.equal(invoiceState(state[0]), "void");
    assert.equal(matchesInvoice(state[0], "void"), true);
    assert.equal(matchesInvoice(state[0], "paid"), false);
    assert.equal(invoiceAmounts(state[0])?.total, 10000);
    assert.equal(invoiceSettlement(state[0])?.balance, -4000);
    assert.deepEqual({ ...state[0], corrections: [] }, original);
    assert.deepEqual(invoiceReducer(state, resolve("confirmed")), state);
    assert.deepEqual(invoiceReducer(state, request()), state);
  });
  test("partial credits adjust only the current balance and never enter Void", () => {
    let state = invoiceReducer([issued()], request("partial_credit", 2500));
    state = invoiceReducer(state, resolve("confirmed"));
    assert.equal(invoiceSettlement(state[0])?.balance, 7500);
    assert.equal(invoiceSettlement(state[0])?.creditable, 7500);
    assert.equal(invoiceAmounts(state[0])?.total, 10000);
    assert.equal(matchesInvoice(state[0], "void"), false);
    const rest = { ...request(), correction: { ...request().correction, id: "c2", amount: 7500 } };
    state = invoiceReducer(state, rest);
    state = invoiceReducer(state, { ...resolve("confirmed"), correctionId: "c2" });
    assert.equal(invoiceSettlement(state[0])?.credited, 10000);
    assert.equal(matchesInvoice(state[0], "void"), true);
  });
  test("failed retry retains history, rejects stale resolutions and applies only once", () => {
    let state = invoiceReducer([issued()], request());
    state = invoiceReducer(state, resolve("failed"));
    state = invoiceReducer(state, { type: "retry_correction", id: "one", correctionId: "c1" });
    assert.deepEqual(state[0].corrections[0].attempts, [{ number: 1, status: "failed" }, { number: 2, status: "pending" }]);
    assert.deepEqual(invoiceReducer(state, resolve("confirmed")), state);
    assert.deepEqual(invoiceReducer(state, { ...request(), correction: { ...request().correction, id: "another" } }), state);
    state = invoiceReducer(state, resolve("confirmed", 2));
    assert.equal(correctionStatus(state[0].corrections[0]), "confirmed");
    assert.equal(invoiceSettlement(state[0])?.credited, 10000);
    assert.deepEqual(invoiceReducer(state, resolve("confirmed", 2)), state);
  });
  test("rejects invalid amount, missing reason, draft correction and unpaid-only cancellation", () => {
    for (const amount of [0, -1, 10001, 1.5, 6000]) assert.deepEqual(invoiceReducer([issued()], request("full_cancellation", amount)), [issued()]);
    assert.deepEqual(invoiceReducer([draft()], request()), [draft()]);
    assert.deepEqual(invoiceReducer([issued()], { ...request(), correction: { ...request().correction, reason: " " } }), [issued()]);
    assert.deepEqual(invoiceReducer([issued()], request("partial_credit", 10001)), [issued()]);
    const paid = { ...issued(), payments: [{ id: "p", amount: 4000, currency: "DOP" as const, date: draft().issuedOn, method: "cash" as const, reference: "" }] };
    assert.deepEqual(invoiceReducer([paid], request("full_cancellation", 6000)), [paid]);
    assert.equal(invoiceReducer([paid], request())[0].corrections.length, 1);
  });
  test("the default is truly empty and deterministic fixtures distinguish outcomes", () => {
    assert.deepEqual(invoicePreviewSeed(null, "Motivo"), []);
    assert.equal(invoicePreviewSeed("seeded", "Motivo").length, 4);
    assert.equal(matchesInvoice(invoicePreviewSeed("correction-confirmed", "Motivo")[1], "void"), true);
    assert.equal(matchesInvoice(invoicePreviewSeed("correction-pending", "Motivo")[1], "void"), false);
    assert.equal(matchesInvoice(invoicePreviewSeed("partial-confirmed", "Motivo")[1], "void"), false);
    assert.equal(invoiceSettlement(invoicePreviewSeed("credit-balance", "Motivo")[1])?.balance, -20000);
  });
});

test("document types require customer identity only for fiscal credit and separate processing from payment", () => {
  assert.equal(validDraft({ ...draft(), documentType: "E31" }), false);
  assert.equal(validDraft({ ...draft(), documentType: "E31", customer: { ...draft().customer, taxId: "123456789" } }), true);
  const state = invoiceReducer([draft()], { type: "issue", id: "one" });
  assert.equal(state[0].fiscal.status, "processing");
  assert.equal(state[0].delivery, "not_sent");
  assert.equal(state[0].payments.length, 0);
  assert.deepEqual(invoiceReducer(state, { type: "issue", id: "one" }), state);
});

test("debit notes preserve original evidence and add to the balance only when confirmed", () => {
  const original = { ...draft(), issuance: "issued" as const };
  const request = { type: "correct" as const, id: "one", correction: { id: "debit1", kind: "debit_adjustment" as const, reason: "Ajuste", amount: 2500 } };
  let state = invoiceReducer([original], request);
  assert.equal(invoiceSettlement(state[0])?.balance, 10000);
  const result = { type: "resolve_correction" as const, id: "one", correctionId: "debit1", attempt: 1, outcome: "confirmed" as const };
  state = invoiceReducer(state, result);
  assert.equal(invoiceSettlement(state[0])?.balance, 12500);
  assert.equal(invoiceSettlement(state[0])?.creditable, 12500);
  assert.equal(invoiceAmounts(state[0])?.total, 10000);
  assert.deepEqual({ ...state[0], corrections: [] }, original);
  assert.deepEqual(invoiceReducer(state, result), state);
  assert.equal(matchesInvoice(state[0], "void"), false);
});

test("fiscal fixture outcomes cannot duplicate issue or invent payments and delivery", () => {
  for (const [variant, status] of [["fiscal-processing", "processing"], ["fiscal-accepted", "accepted"], ["fiscal-observations", "accepted_observations"], ["fiscal-rejected", "rejected"], ["fiscal-failed", "failed"], ["fiscal-uncertain", "uncertain"]]) {
    const invoice = invoicePreviewSeed(variant, "Motivo")[1];
    assert.equal(invoice.fiscal.status, status);
    assert.equal(invoice.payments.length, 0);
    assert.equal(invoice.delivery, "not_sent");
    assert.deepEqual(invoiceReducer([invoice], { type: "issue", id: invoice.id }), [invoice]);
  }
});


test("item discounts reduce the taxable base using exact minor units", () => {
  const original = draft();
  const invoice = { ...original, items: [{ ...original.items[0], quantity: "3", price: "0.05", tax: "10", discount: "0.05" }] };
  assert.deepEqual(invoiceAmounts(invoice), { subtotal: 15, discount: 5, tax: 1, total: 11, paid: 0, balance: 11 });
  for (const discount of ["0.16", "-1", "1e2", "0.001"]) {
    const invalid = { ...invoice, items: [{ ...invoice.items[0], discount }] };
    assert.equal(invoiceAmounts(invalid), null);
    assert.equal(invoiceDraftErrors(invalid)["i1-discount"], "discount");
  }
});

test("email preparation is retained without issuing, delivering, or blocking draft saves", () => {
  const original = draft();
  assert.deepEqual(invoiceEmailDraft(original), { to: original.customer.email, cc: "", message: "" });
  const invoice = { ...original, emailDraft: { to: "wrong", cc: "also-wrong", message: "Separate email message" } };
  assert.deepEqual(invoiceEmailErrors(invoice.emailDraft), { to: "email", cc: "email_cc" });
  assert.equal(validDraft(invoice), true);
  const saved = invoiceReducer([], { type: "save", invoice })[0];
  assert.deepEqual(saved.emailDraft, invoice.emailDraft);
  assert.equal(saved.issuance, "draft");
  assert.equal(saved.delivery, "not_sent");
  assert.equal(saved.fiscal.status, "not_submitted");
  assert.deepEqual(invoiceEmailErrors({ to: "customer@example.test", cc: "one@example.test;two@example.test", message: "" }), {});
  assert.equal(invoiceEmailErrors({ to: "customer@example.test", cc: Array(6).fill("one@example.test").join(","), message: "" }).cc, "email_cc");
});
