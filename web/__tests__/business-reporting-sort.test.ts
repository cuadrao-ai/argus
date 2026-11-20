import { expect, test } from "bun:test";
import { DEFAULT_RECORDS_SORT, RECORDS_SORT_OPTIONS } from "@/components/business-app/transacciones/records-pagination";
import { createBusinessReportController, recordsSortToReport, reportSortToRecords, reportLocation, restoreReportLocation } from "@/lib/business-reporting-wire";
import { reportRecipeSchema, reportRequestSchema, type ReportRequest } from "@/lib/business-reports-api";
import type { ReportingTransport } from "@/lib/business-reporting-wire";
import { recordedReportAnswer } from "./fixtures/recorded-report-answer";

const sorts = [
  ["date", "desc", "date_desc", "fecha"],
  ["date", "asc", "date_asc", "fecha"],
  ["gross_amount", "desc", "amount_desc", "monto"],
  ["gross_amount", "asc", "amount_asc", "monto"],
  ["counterparty", "asc", "name_asc", "contraparte"],
  ["counterparty", "desc", "name_desc", "contraparte"],
] as const;

test("the sort menu keeps its default and server ordering", () => {
  expect(recordsSortToReport(DEFAULT_RECORDS_SORT)).toBe("date_desc");
  expect(RECORDS_SORT_OPTIONS.map(recordsSortToReport)).toEqual([
    "date_desc", "date_asc", "amount_desc", "amount_asc", "name_asc", "name_desc",
  ]);
});

test.each(sorts)("column %s %s sends %s and restores its column state", (key, direction, serverSort) => {
  expect(recordsSortToReport({ key, direction })).toBe(serverSort);
  expect(reportSortToRecords(serverSort)).toEqual({ key, direction });
});

test.each(sorts)("stored %s %s legacy key loads as %s once at the URL boundary", (key, direction, serverSort, oldKey) => {
  const stored = { schema_version: 2, page: 3, page_size: 50, filters: { currencies: ["DOP"] }, sort: { key: oldKey, direction } };
  const restored = restoreReportLocation(new URLSearchParams({ report: JSON.stringify(stored), report_row: "draft:one" }));
  expect(restored).toEqual({ request: reportRequestSchema.parse({ ...stored, sort: serverSort }), anchor: "draft:one" });
  expect(reportSortToRecords(restored.request.sort)).toEqual({ key, direction });
  const written = new URLSearchParams(reportLocation(restored.request, restored.anchor));
  expect(JSON.parse(written.get("report")!).sort).toBe(serverSort);
  expect(restoreReportLocation(written)).toEqual(restored);
});

test.each([{ key: "unknown", direction: "asc" }, { key: "monto", direction: "sideways" }, null])("invalid stored sort %j keeps the URL fallback", (sort) => {
  expect(restoreReportLocation(new URLSearchParams({ report: JSON.stringify({ schema_version: 2, sort }), report_row: "draft:one" })))
    .toEqual(restoreReportLocation(new URLSearchParams()));
});

test.each(sorts)("saved view for %s %s still queries %s", async (_key, _direction, sort) => {
  const requests: ReportRequest[] = [];
  const transport: ReportingTransport = {
    query: async (_scope, request) => { requests.push(request); return { ...recordedReportAnswer, items: [], page: request.page, page_size: request.page_size }; },
    listViews: async () => [], mutateView: async () => null,
    exportPreview: async () => { throw new Error("unused"); }, exportFile: async () => { throw new Error("unused"); },
  };
  const controller = createBusinessReportController({ userId: "person", businessId: "business", grantId: null }, undefined, transport);
  try {
    await controller.openView({ id: "saved", name: "Saved", recipe: reportRecipeSchema.parse({ schema_version: 2, sort }), version: 1, created_at: "now", updated_at: "now" });
    expect(requests.map((request) => request.sort)).toEqual([sort]);
  } finally { controller.dispose(); }
});
