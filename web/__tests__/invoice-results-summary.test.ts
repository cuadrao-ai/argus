import assert from "node:assert/strict";
import { test } from "bun:test";
import { newInvoice, type InvoicePreview } from "../components/business-app/invoicing/invoice-preview-model";
import { summarizeInvoiceResults } from "../components/business-app/invoicing/invoice-results-summary";

test("a selected currency with no matching invoices keeps all three amounts at zero", () => {
  assert.deepEqual(summarizeInvoiceResults([], "EUR", "all").currencies, [
    { currency: "EUR", total: 0, settled: 0, balance: 0 },
  ]);
});

test("no selected currency or an empty draft stage does not invent a financial summary", () => {
  assert.deepEqual(summarizeInvoiceResults([], "all", "all").currencies, []);
  assert.deepEqual(summarizeInvoiceResults([], "EUR", "draft").currencies, []);
});

const invoice = (): InvoicePreview => ({ ...newInvoice("one", "M-001"), currency: "EUR", items: [{ id: "item", description: "Servicio", quantity: "1", price: "100.00", tax: "0" }] });

for (const issuance of ["draft", "uncertain"] as const) {
  test(`matching ${issuance} invoices do not become a zero balance`, () => {
    const summary = summarizeInvoiceResults([{ ...invoice(), issuance }], "EUR", "all");
    assert.deepEqual(summary.currencies, []);
    assert.equal(summary.exclusions.unconfirmed, 1);
  });
}

test("matching issued invoices with unavailable money do not become a zero balance", () => {
  const invalid = { ...invoice(), issuance: "issued" as const, items: [{ ...invoice().items[0], price: "invalid" }] };
  const summary = summarizeInvoiceResults([invalid], "EUR", "all");
  assert.deepEqual(summary.currencies, []);
  assert.equal(summary.exclusions.unconfirmed, 1);
});

test("confirmed invoice totals stay in cents and retain partial payments", () => {
  const issued: InvoicePreview = { ...invoice(), issuance: "issued", payments: [{ id: "payment", amount: 4000, currency: "EUR", date: "2026-10-26", method: "cash", reference: "" }] };
  assert.deepEqual(summarizeInvoiceResults([issued], "EUR", "all").currencies, [
    { currency: "EUR", total: 10000, settled: 4000, balance: 6000 },
  ]);
});
