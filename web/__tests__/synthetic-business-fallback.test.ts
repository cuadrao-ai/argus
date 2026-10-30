import { describe, expect, test } from "bun:test";
import { fulfillSyntheticBusinessFallback } from "../e2e/support/synthetic-business-fallback";
import { defaultReportRequest } from "../lib/business-reporting-wire";
import { reportAnswerSchema } from "../lib/business-reports-api";

function syntheticRoute(path = "reports/query", method = "POST", body = JSON.stringify(defaultReportRequest())) {
  const responses: unknown[] = [];
  return {
    responses,
    request: () => ({
      url: () => `http://127.0.0.1:3198/api/v1/business/${path}`,
      method: () => method,
      postDataJSON: () => JSON.parse(body),
    }),
    fulfill: async ({ json }: { json: unknown }) => { responses.push(json); },
  };
}

describe("synthetic Business fallback", () => {
  test("fulfills the app's default report request with a complete empty report", async () => {
    const route = syntheticRoute();
    await fulfillSyntheticBusinessFallback(route);

    expect(route.responses).toHaveLength(1);
    const answer = reportAnswerSchema.parse(route.responses[0]);
    expect(answer).toEqual({
      items: [],
      overview: { needs_review: 0, awaiting_approval: 0, ready_for_export: 0 },
      effective_sort: "date_desc",
      sort_unavailable_reason: null,
      matching_count: 0,
      page: 1,
      page_size: 25,
      page_count: 0,
      totals: [],
      fingerprint: "0".repeat(64),
      captured_at: "2026-10-21T17:45:00Z",
      resolved_period: { from_date: null, to_date: null, calendar: "America/Santo_Domingo" },
      excluded_unknown_dates: 0,
      excluded_personal: { income: 0, expense: 0 },
      counterparties: [],
      categories: [],
      funding_sources: [],
      coverage_notes: [
        "records_only_evidence_separate",
        "legal_cancellation_coverage_unavailable",
        "source_document_subtype_may_be_unknown",
        "counterparty_identity_requires_explicit_tax_id",
      ],
    });
  });

  test("echoes valid pagination in a deterministic report", async () => {
    const body = JSON.stringify({ ...defaultReportRequest(), page: 3, page_size: 50 });
    const first = syntheticRoute("reports/query", "POST", body);
    const second = syntheticRoute("reports/query", "POST", body);
    await fulfillSyntheticBusinessFallback(first);
    await fulfillSyntheticBusinessFallback(second);

    expect(first.responses).toEqual(second.responses);
    expect(reportAnswerSchema.parse(first.responses[0])).toMatchObject({ page: 3, page_size: 50, page_count: 0, items: [] });
  });

  test.each(["reports/export", "report-views", "reports/query/", "unknown"])("keeps %s unmapped", async (path) => {
    const route = syntheticRoute(path);
    await expect(fulfillSyntheticBusinessFallback(route)).rejects.toThrow(`Unmapped synthetic endpoint ${path}`);
    expect(route.responses).toEqual([]);
  });

  test.each(["GET", "PUT", "DELETE"])("rejects %s on the query endpoint", async (method) => {
    const route = syntheticRoute("reports/query", method);
    await expect(fulfillSyntheticBusinessFallback(route)).rejects.toThrow();
    expect(route.responses).toEqual([]);
  });

  test.each([
    "{",
    "null",
    "[]",
    JSON.stringify({ ...defaultReportRequest(), page: 0 }),
    JSON.stringify({ ...defaultReportRequest(), page_size: 10 }),
    JSON.stringify({ ...defaultReportRequest(), unexpected: true }),
    JSON.stringify({ ...defaultReportRequest(), filters: { period: { kind: "this_month" } } }),
    JSON.stringify({ ...defaultReportRequest(), schema_version: 2, sort: "amount_desc" }),
  ])("rejects malformed or unsupported report bodies %#", async (body) => {
    const route = syntheticRoute("reports/query", "POST", body);
    await expect(fulfillSyntheticBusinessFallback(route)).rejects.toThrow();
    expect(route.responses).toEqual([]);
  });

  test("rejects query parameters rather than silently ignoring them", async () => {
    const route = syntheticRoute("reports/query?page=2");
    await expect(fulfillSyntheticBusinessFallback(route)).rejects.toThrow();
    expect(route.responses).toEqual([]);
  });
});
