import assert from "node:assert/strict";
import { test } from "bun:test";
import { sampleRecordsOverview } from "@/components/business-app/transacciones/records-overview-sample";
import { matchesPreviewWorkflow } from "@/components/business-app/transacciones/records-results-preview";
import type { RecordRow } from "@/components/business-app/transacciones/transacciones-model";

const record = (id: string, kind: RecordRow["kind"], amount: string, currency = "DOP"): RecordRow => ({ id, kind, occurredOn: "2026-11-02", counterparty: "Sample", money: { amount, currency }, categoryId: null, account: null, hasProof: null, marks: { personal: false, markedBy: null, fiscal: null }, opens: null });
const purchases = [record("exp-gas", "gasto", "-2100.00"), record("exp-imprenta", "gasto", "-4800.00")];
const rows = [...purchases, ...Array.from({ length: 5 }, (_, index) => record(`venta-${index + 1}`, "venta", "500.00"))];
const sample = (visible: readonly RecordRow[], sourceMode: "fixture" | "live" = "fixture", businessId = "fixture-space") => sampleRecordsOverview({ sourceMode, businessId, rows: visible, kind: "gasto" });

test("sample cards count and sum selected purchases and retain partial fiscal facts", () => {
  const result = sample(rows)!;
  assert.equal(result.answer.matching_count, 2);
  assert.equal(result.answer.totals[0].amount, "6900.00");
  assert.equal(result.answer.totals[0].matching_count, 2);
  assert.equal(result.fiscalCount, 2);
  assert.deepEqual(result.answer.fiscal_totals?.map(({ basis, amount, known_amount, populated_count, unknown_count }) => ({ basis, amount, known_amount, populated_count, unknown_count })), [
    { basis: "itbis", amount: "1052.54", known_amount: "1052.54", populated_count: 2, unknown_count: 0 },
    { basis: "goods", amount: null, known_amount: "1779.66", populated_count: 1, unknown_count: 1 },
    { basis: "services", amount: null, known_amount: "4067.80", populated_count: 1, unknown_count: 1 },
  ]);
  assert.equal(result.summary.currencies[0].total, "6900.00");
});

test("search and fiscal subsets change totals and the fiscal count", () => {
  assert.equal(sample([purchases[0]])!.answer.totals[0].amount, "2100.00");
  assert.equal(sample([purchases[0]])!.answer.matching_count, 1);
  assert.equal(sample([purchases[0]])!.fiscalCount, 1);
  const fiscalRows = rows.filter((row) => matchesPreviewWorkflow(row, "fixture-space", ["fiscal"]));
  assert.equal(sample(fiscalRows)!.answer.matching_count, 2);
  assert.equal(sample(fiscalRows)!.answer.totals[0].amount, "6900.00");
  assert.equal(sample([])!.fiscalCount, 0);
  assert.deepEqual(sample([])!.answer, { matching_count: 0, totals: [], fiscal_totals: [] });
});

test("known zero stays known, currencies stay separate, and unknown rows stay incomplete", () => {
  const hosting = record("exp-hosting", "gasto", "-24.00", "USD");
  const result = sample([...purchases, hosting])!;
  assert.deepEqual(result.answer.totals.map(({ currency, amount }) => ({ currency, amount })), [{ currency: "DOP", amount: "6900.00" }, { currency: "USD", amount: "24.00" }]);
  assert.equal(result.answer.fiscal_totals?.find((line) => line.currency === "USD" && line.basis === "itbis")?.amount, "0.00");
  const unknown = sample([purchases[0], record("unknown", "gasto", "100.00")])!;
  assert.equal(unknown.answer.totals[0].amount, null);
  assert.equal(unknown.answer.totals[0].known_amount, "2100.00");
  assert.equal(unknown.answer.totals[0].unknown_count, 1);
  assert.equal(unknown.summary.currencies[0].total, null);
  assert.equal(unknown.summary.currencies[0].known, "2100.00");
  assert.equal(sample([record("exp-gas", "gasto", "-999.00")])!.answer.fiscal_totals?.[0].amount, null);
});

test("sample money stays exact for large amounts and never populates live or other businesses", () => {
  assert.equal(sample([record("exp-gas", "gasto", "-90071992547409.93")])!.answer.totals[0].amount, "90071992547409.93");
  assert.equal(sample(rows, "live"), undefined);
  assert.equal(sample(rows, "fixture", "fixture-client"), undefined);
});
