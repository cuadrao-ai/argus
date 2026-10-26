import assert from "node:assert/strict";
import { test } from "bun:test";
import { defaultRecordsPreferences, toggleRecordsColumn, visibleRecordsColumns } from "@/components/business-app/transacciones/records-view-preferences";
import { previewRecordMetadata, summarizePreviewRecords } from "@/components/business-app/transacciones/records-results-preview";
import type { RecordRow } from "@/components/business-app/transacciones/transacciones-model";
import es from "@/public/locales/es-419/common.json";
import en from "@/public/locales/en/common.json";

const record = (id: string, kind: RecordRow["kind"], amount: string, currency: string): RecordRow => ({ id, kind, occurredOn: "2026-10-25", counterparty: "Sample", money: { amount, currency }, categoryId: null, account: null, hasProof: null, marks: { personal: false, markedBy: null, fiscal: null }, opens: null });
const rows = [record("exp-gas", "gasto", "-2100.00", "DOP"), record("exp-hosting", "gasto", "-24.00", "USD"), record("exp-lunch", "gasto", "-1250.00", "DOP"), record("exp-gas", "venta", "2100.00", "DOP"), record("exp-hosting", "venta", "24.00", "USD"), record("exp-lunch", "venta", "1250.00", "DOP")];

test("preview defaults add Estado, retain seven visible columns and keep Cuenta optional", () => {
  const prefs = defaultRecordsPreferences();
  assert.equal(prefs.order.length, 8);
  assert.deepEqual(visibleRecordsColumns(prefs).map(({ key }) => key), ["contraparte", "fecha", "monto", "detalle", "categoria", "estado", "comprobante"]);
  assert.deepEqual(prefs.hidden, ["cuenta"]);
  assert.equal(visibleRecordsColumns(toggleRecordsColumn(prefs, "cuenta")).length, 8);
  assert.equal(visibleRecordsColumns(toggleRecordsColumn(prefs, "estado")).some(({ key }) => key === "estado"), false);
});

test("summary keeps workflow and financial eligibility separate and never mixes currencies", () => {
  const result = summarizePreviewRecords(rows, "fixture-space");
  assert.equal(result.count, 6); assert.equal(result.review, 2); assert.equal(result.unknownWorkflow, 0);
  assert.deepEqual(result.sales, [{ currency: "DOP", amount: "2100.00" }]);
  assert.deepEqual(result.expenses, [{ currency: "DOP", amount: "2100.00" }, { currency: "USD", amount: "24.00" }], "a reviewed record can still have a confirmed amount");
  assert.deepEqual(result.excluded, { personal: 2, unconfirmed: 1, unavailable: 0 });
  assert.deepEqual(result.excludedByKind, { sales: { personal: 1, unconfirmed: 1, unavailable: 0 }, expenses: { personal: 1, unconfirmed: 0, unavailable: 0 } });
  const purchases = summarizePreviewRecords(rows.filter((row) => row.kind === "gasto"), "fixture-space");
  assert.equal(purchases.count, 3); assert.equal(purchases.review, 1);
  assert.deepEqual(purchases.sales, []); assert.deepEqual(purchases.expenses, result.expenses);
});

test("unknown rows and other businesses receive no invented workflow or eligible total", () => {
  const unknown = record("not-a-fixture", "gasto", "-100.00", "DOP");
  assert.equal(previewRecordMetadata(unknown, "fixture-space"), null);
  for (const businessId of [null, "fixture-client", "local-business-new"]) {
    assert.equal(previewRecordMetadata(rows[0], businessId), null);
    const result = summarizePreviewRecords(rows, businessId);
    assert.equal(result.unknownWorkflow, 6); assert.equal(result.excluded.unavailable, 6);
    assert.deepEqual(result.sales, []); assert.deepEqual(result.expenses, []);
  }
  const result = summarizePreviewRecords([unknown], "fixture-space");
  assert.equal(result.unknownWorkflow, 1); assert.deepEqual(result.expenses, []);
});

test("money remains exact, invalid precision is excluded, personal overrides confirmed eligibility", () => {
  const large = record("exp-hosting", "gasto", "-90071992547409.93", "USD");
  assert.deepEqual(summarizePreviewRecords([large], "fixture-space").expenses, [{ currency: "USD", amount: "90071992547409.93" }]);
  const malformed = { ...large, money: { amount: "-24.001", currency: "USD" } };
  assert.equal(summarizePreviewRecords([malformed], "fixture-space").excluded.unavailable, 1);
  const personal = { ...large, marks: { ...large.marks, personal: true } };
  assert.equal(summarizePreviewRecords([personal], "fixture-space").excluded.personal, 1);
  assert.deepEqual(summarizePreviewRecords([personal], "fixture-space").expenses, []);
});

test("summary labels are available at the same EN and ES layout paths", () => {
  for (const locale of [es, en]) {
    assert.ok(locale.business.transactions.layout.results.title);
    assert.ok(locale.business.transactions.layout.settings.summary);
    assert.deepEqual(Object.keys(locale.business.transactions.layout.results.metrics), ["expenses", "sales"]);
    assert.ok(locale.business.transactions.layout.column_state);
    assert.ok(locale.business.transactions.layout.workflow.unknown);
    assert.equal("results" in locale.business.transactions.layout.filters, false);
  }
});

test("currency and bounds filter original-currency magnitudes with exact arithmetic", async () => {
  const { matchesPreviewAmount } = await import("@/components/business-app/transacciones/records-filter-preview-model");
  const usd = { currency: "USD", min: "9007199254740993.01", max: "9007199254740993.02" } as const;
  assert.equal(matchesPreviewAmount({ currency: "USD", amount: "-9007199254740993.01" }, usd), true);
  assert.equal(matchesPreviewAmount({ currency: "USD", amount: "9007199254740993.00" }, usd), false);
  assert.equal(matchesPreviewAmount({ currency: "DOP", amount: "9007199254740993.01" }, usd), false);
  assert.equal(matchesPreviewAmount({ currency: "USD", amount: "bad" }, usd), false);
  assert.equal(matchesPreviewAmount({ currency: "USD", amount: "24" }, { currency: "USD", min: "25", max: "24" }), false);
});
