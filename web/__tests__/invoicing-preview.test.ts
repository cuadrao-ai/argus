import { describe, test } from "bun:test";
import assert from "node:assert/strict";
import { hundredths, invoiceAmounts, invoiceReducer, matchesInvoice, newInvoice, validDraft } from "../components/business-app/invoicing/invoice-preview-model";

const draft = () => ({ ...newInvoice("one", "M-001"), customer: { id: "c1", name: "Cliente de muestra", email: "test@example.test", address: "", taxId: "" }, items: [{ id: "i1", description: "Servicio", quantity: "1", price: "100.00", tax: "0" }] });
describe("connected invoice preview", () => {
  test("one identity survives save, issue, preparation and two linked payments", () => {
    let state = invoiceReducer([], { type: "save", invoice: draft() });
    state = invoiceReducer(state, { type: "issue", id: "one" });
    state = invoiceReducer(state, { type: "prepare", id: "one", preparation: { channel: "email", email: "recipient@example.test" } });
    const payment = { id: "pay1", amount: 4000, currency: "DOP" as const, date: draft().issuedOn, method: "transfer" as const, reference: "" };
    state = invoiceReducer(state, { type: "pay", id: "one", payment });
    assert.deepEqual(invoiceAmounts(state[0]), { subtotal: 10000, tax: 0, total: 10000, paid: 4000, balance: 6000 });
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
    assert.deepEqual(invoiceAmounts({ items: [{ ...item, quantity: "3", price: "0.05", tax: "10" }], payments: [] }), { subtotal: 15, tax: 2, total: 17, paid: 0, balance: 17 });
    assert.equal(invoiceAmounts({ items: [{ ...item, quantity: "1000", price: "9999999.99", tax: "100" }], payments: [] })?.total, 1999999998000);
  });
});
