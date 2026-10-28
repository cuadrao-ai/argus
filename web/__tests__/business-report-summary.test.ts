import assert from "node:assert/strict";
import { test } from "bun:test";
import { reportAnswerSchema, reportTotalSchema, type ReportAnswer } from "@/lib/business-reports-api";
import { reportSummary, summaryIncludesUnreviewed } from "@/lib/business-reporting-wire";

const total = (patch: Record<string, unknown>) => reportTotalSchema.parse({ currency: "DOP", kind: "income", basis: "document_family_amount", matching_count: 2, known_amount_minor: 30000, unknown_count: 0, unsupported_count: 0, complete: true, amount_minor: 30000, known_amount: "300.00", amount: "300.00", ...patch });
const answer = (totals: unknown[]): ReportAnswer => reportAnswerSchema.parse({
  items: [], matching_count: 0, page: 1, page_size: 25, page_count: 0, totals, fingerprint: "a".repeat(64), captured_at: "2026-10-27T12:00:00Z",
  resolved_period: { from_date: null, to_date: null, calendar: "America/Santo_Domingo" }, excluded_unknown_dates: 0, counterparties: [], categories: [], funding_sources: [], coverage_notes: [],
});

const wire = answer([
  total({ currency: "USD", amount: "40.00", known_amount: "40.00", amount_minor: 4000, known_amount_minor: 4000 }),
  total({ basis: "recorded_activity_amount", amount: "999.00", known_amount: "999.00", amount_minor: 99900, known_amount_minor: 99900 }),
  total({ basis: "proposed_activity_amount", currency: "EUR", amount: "5.00", known_amount: "5.00", amount_minor: 500, known_amount_minor: 500 }),
  total({ kind: "expense", amount: "70.00", known_amount: "70.00", amount_minor: 7000, known_amount_minor: 7000 }),
  total({}),
  total({ currency: null, unknown_count: 1, complete: false, amount_minor: null, known_amount: null, amount: null, known_amount_minor: 0 }),
  total({ currency: "CAD", unknown_count: 1, complete: false, amount_minor: null, known_amount: "12.50", amount: null, known_amount_minor: 1250 }),
]);

test("card one lists the server's final document totals for the family, one row per currency, never summed", () => {
  const sales = reportSummary(wire, "venta").currencies;
  assert.deepEqual(sales.map(({ currency, total }) => [currency, total]), [["CAD", null], ["DOP", "300.00"], ["USD", "40.00"], ["", null]]);
  assert.deepEqual(reportSummary(wire, "gasto").currencies.map(({ currency, total }) => [currency, total]), [["DOP", "70.00"]]);
});

test("recorded and proposed activity components never become finalized document money", () => {
  const sales = reportSummary(wire, "venta").currencies;
  assert.equal(sales.some(({ currency, total }) => currency === "EUR" || total === "999.00"), false);
});

test("an incomplete total keeps its null amount and carries the labelled known part; unknown currency stays empty", () => {
  const sales = reportSummary(wire, "venta").currencies;
  assert.deepEqual(sales[0], { currency: "CAD", total: null, known: "12.50", settled: null, balance: null });
  assert.deepEqual(sales.at(-1), { currency: "", total: null, known: null, settled: null, balance: null });
});

test("the personal exclusion count is the server's, per family, and zero when the server sends none", () => {
  const counted = reportAnswerSchema.parse({ ...wire, excluded_personal: { income: 1, expense: 2 } });
  assert.equal(reportSummary(counted, "venta").exclusions.personal, 1);
  assert.equal(reportSummary(counted, "gasto").exclusions.personal, 2);
  assert.equal(reportSummary(wire, "gasto").exclusions.personal, 0);
  assert.equal(reportSummary(undefined, "gasto").exclusions.personal, 0);
});

test("settled and balance are never filled and a missing answer is empty rather than zero", () => {
  assert.equal(reportSummary(wire, "venta").currencies.every((currency) => currency.settled === null && currency.balance === null), true);
  assert.deepEqual(reportSummary(undefined, "venta").currencies, []);
});

test("the review qualifier shows unless the stage filter is exactly ready for export or the server reports no review or approval documents", () => {
  const overview = (needs_review: number, awaiting_approval: number) => ({ needs_review, awaiting_approval, ready_for_export: 5 });
  assert.equal(summaryIncludesUnreviewed([], overview(1, 0)), true);
  assert.equal(summaryIncludesUnreviewed([], undefined), true);
  assert.equal(summaryIncludesUnreviewed(["ready_for_export"], overview(60, 40)), false);
  assert.equal(summaryIncludesUnreviewed(["needs_review", "ready_for_export"], overview(60, 40)), true);
  assert.equal(summaryIncludesUnreviewed(["awaiting_approval"], undefined), true);
  assert.equal(summaryIncludesUnreviewed([], overview(0, 0)), false);
  assert.equal(summaryIncludesUnreviewed([], overview(0, 2)), true);
  assert.equal(summaryIncludesUnreviewed([], overview(2, 0)), true);
});
