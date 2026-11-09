import { describe, expect, test } from "bun:test";
import { fulfillSyntheticBusinessFallback } from "../e2e/support/synthetic-business-fallback";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { defaultReportRequest } from "../lib/business-reporting-wire";
import { reportAnswerSchema } from "../lib/business-reports-api";
import recordedAnswer from "../test-fixtures/records-default-report-answer.json";

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
      presentation: recordedAnswer.presentation,
      items: [],
      overview: { needs_review: 0, needs_fiscal_data: 0, ready_for_export: 0, exported: 0 },
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
      expense_types: [],
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

  test("returns the undismissed state for the known guide card", async () => {
    const route = syntheticRoute("guide-cards/bandeja-intro", "GET");
    await fulfillSyntheticBusinessFallback(route);

    expect(route.responses).toEqual([{ dismissed: false }]);
  });

  test("returns the dismissed state for the known guide card", async () => {
    const route = syntheticRoute("guide-cards/bandeja-intro/dismiss", "POST");
    await fulfillSyntheticBusinessFallback(route);

    expect(route.responses).toEqual([{ dismissed: true }]);
  });

  test("returns the owner-only spaces fixture and accepts the app query string", async () => {
    const source = createFixtureBusinessDataSource({ chatAvailable: false });
    const owner = (await source.spaces())[0];
    const route = syntheticRoute("spaces?include_closed=false", "GET");
    await fulfillSyntheticBusinessFallback(route, { source, owner });

    expect(route.responses).toEqual([{ spaces: [owner], closed_spaces: [] }]);
  });

  test("returns the fixture month-close response for the app query string", async () => {
    const route = syntheticRoute("month-close?month=2026-10", "GET");
    await fulfillSyntheticBusinessFallback(route);

    expect(route.responses).toHaveLength(1);
    expect(route.responses[0]).toMatchObject({ month: "2026-10", from: "2026-10-01" });
  });

  test("accepts name-prompt only as POST", async () => {
    const valid = syntheticRoute("space/name-prompt", "POST");
    await fulfillSyntheticBusinessFallback(valid);
    expect(valid.responses).toEqual([{ id: expect.any(String), name: expect.any(String), name_required: false, name_prompt_seen: true, show_prompt: false }]);

    const invalid = syntheticRoute("space/name-prompt", "GET");
    await expect(fulfillSyntheticBusinessFallback(invalid)).rejects.toThrow("requires POST");
    expect(invalid.responses).toEqual([]);
  });

  test("uses the provided accepted-consent fixture and requires it", async () => {
    const route = syntheticRoute("consent?version=consent-v1", "GET");
    let consentCalls = 0;
    await fulfillSyntheticBusinessFallback(route, {
      fulfillConsent: async () => {
        consentCalls += 1;
        await route.fulfill({ json: { version: "consent-v1", accepted_at: "fixture-owned" } });
      },
    });
    expect(consentCalls).toBe(1);
    expect(route.responses).toEqual([{ version: "consent-v1", accepted_at: "fixture-owned" }]);

    const missingFixture = syntheticRoute("consent", "GET");
    await expect(fulfillSyntheticBusinessFallback(missingFixture)).rejects.toThrow("requires an accepted-consent fixture");
    expect(missingFixture.responses).toEqual([]);
  });

  test.each([
    ["spaces?include_closed=false", "POST"],
    ["receipts?view=inbox", "POST"],
    ["unknown-business-path", "GET"],
    ["unknown-business-path", "POST"],
  ])("rejects unsupported shared endpoint %s with %s", async (path, method) => {
    const route = syntheticRoute(path, method);
    await expect(fulfillSyntheticBusinessFallback(route)).rejects.toThrow();
    expect(route.responses).toEqual([]);
  });

  test.each([
    ["guide-cards/bandeja-intro", "POST"],
    ["guide-cards/bandeja-intro/dismiss", "GET"],
    ["guide-cards/unknown", "GET"],
    ["guide-cards/unknown/dismiss", "POST"],
    ["guide-cards/bandeja-intro/", "GET"],
    ["guide-cards/bandeja-intro/dismiss/", "POST"],
    ["guide-cards/bandeja-intro-extra", "GET"],
    ["guide-cards/bandeja-intro/dismiss-extra", "POST"],
  ])("rejects unsupported guide request %s with %s", async (path, method) => {
    const route = syntheticRoute(path, method);
    await expect(fulfillSyntheticBusinessFallback(route)).rejects.toThrow();
    expect(route.responses).toEqual([]);
  });

  test.each([
    ["guide-cards/bandeja-intro?source=test", "GET"],
    ["guide-cards/bandeja-intro/dismiss?source=test", "POST"],
  ])("rejects query parameters on guide request %s", async (path, method) => {
    const route = syntheticRoute(path, method);
    await expect(fulfillSyntheticBusinessFallback(route)).rejects.toThrow();
    expect(route.responses).toEqual([]);
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
