import assert from "node:assert/strict";
import { test } from "bun:test";
import { customerActivity, customerErrors, customerReducer, customerSnapshot, matchesCustomer, seedCustomers, type BusinessCustomer } from "../components/business-app/invoicing/customer-preview-model";
import { invoicePreviewSeed, invoiceReducer } from "../components/business-app/invoicing/invoice-preview-model";

const customer = (): BusinessCustomer => ({ id: "customer-one", name: "Café Brisa", email: "brisa@example.test", taxId: "123456789", address: "Calle de muestra 4", status: "active" });

test("customers exist without invoices, validate fields and retain identity through edit, archive and restore", () => {
  let state = customerReducer([], { type: "save", customer: customer() });
  assert.equal(state.length, 1);
  assert.equal(matchesCustomer(state[0], "cafe"), true);
  assert.equal(matchesCustomer(state[0], "123456789"), true);
  state = customerReducer(state, { type: "save", customer: { ...state[0], name: "Nuevo nombre" } });
  state = customerReducer(state, { type: "status", id: "customer-one", status: "archived" });
  assert.equal(state[0].name, "Nuevo nombre");
  assert.equal(state[0].status, "archived");
  assert.deepEqual(customerReducer(state, { type: "save", customer: { ...state[0], name: "" } }), state);
  assert.deepEqual(customerErrors({ ...customer(), email: "bad", taxId: "123" }), { email: "email", taxId: "tax_id" });
  state = customerReducer(state, { type: "status", id: "customer-one", status: "active" });
  assert.equal(state[0].status, "active");
  assert.equal(state[0].name, "Nuevo nombre");
  assert.ok(state[0].createdAt);
  assert.ok(state[0].updatedAt);
});

test("registry edits and archive never rewrite invoice snapshots or regenerate old customer names", () => {
  const invoices = invoicePreviewSeed("seeded", "Correction");
  const original = structuredClone(invoices);
  let registry = seedCustomers(invoices);
  const old = registry[1];
  registry = customerReducer(registry, { type: "save", customer: { ...old, name: "Changed", email: "new@example.test" } });
  registry = customerReducer(registry, { type: "status", id: old.id, status: "archived" });
  const issued = invoiceReducer(invoices, { type: "issue", id: "001" });
  assert.equal(registry[1].name, "Changed");
  assert.equal(registry[1].status, "archived");
  assert.deepEqual(invoices, original);
  assert.deepEqual(issued[1].customer, original[1].customer);
  assert.deepEqual(customerSnapshot(registry[1]), { id: old.id, name: "Changed", email: "new@example.test", address: old.address, taxId: old.taxId });
});

test("customer activity joins stable IDs, excludes draft and uncertain money, and keeps currency and credit truthful", () => {
  const invoices = invoicePreviewSeed("credit-balance", "Correction");
  const target = invoices[1];
  const mixed = [...invoices, { ...target, id: "usd", currency: "USD" as const, payments: [], corrections: [] }, { ...target, id: "unissued", issuance: "draft" as const }, { ...target, id: "unknown", issuance: "uncertain" as const }, { ...target, id: "same-name", customer: { ...target.customer, id: "different" } }];
  const activity = customerActivity(mixed, target.customer.id);
  assert.equal(activity.invoices.length, 4);
  assert.deepEqual(activity.totals, [{ currency: "DOP", total: 180000, paid: 200000, balance: -20000 }, { currency: "USD", total: 240000, paid: 0, balance: 240000 }]);
  assert.equal(activity.payments.length, 1);
  assert.equal(activity.payments[0].invoiceId, target.id);
  assert.deepEqual(customerActivity(mixed, "no-history"), { invoices: [], totals: [], payments: [] });
});
