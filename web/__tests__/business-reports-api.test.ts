import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { getChosenGrant, setChosenGrant } from "@/lib/business-grant";
import { exportBusinessReport, listBusinessReportViews, mutateBusinessReportView, queryBusinessReport, reportRequestSchema, type ReportScope } from "@/lib/business-reports-api";

const scope: ReportScope = { userId: "synthetic-person", businessId: "synthetic-business", grantId: "00000000-0000-4000-8000-000000000001" };
const answer = () => ({ items: [], matching_count: 102, page: 1, page_size: 25, page_count: 5, totals: [{ currency: "DOP", kind: "expense", basis: "recorded_activity_amount", matching_count: 102, known_amount_minor: 123456789, unknown_count: 1, unsupported_count: 0, complete: false, amount_minor: null, known_amount: "1234567.89", amount: null }], fingerprint: "a".repeat(64), captured_at: "2026-10-26T00:00:00Z", resolved_period: { from_date: null, to_date: null, calendar: "America/Santo_Domingo" }, excluded_unknown_dates: 0, counterparties: [], categories: [], funding_sources: [], coverage_notes: ["legal_cancellation_coverage_unavailable"] });
type Call = { path: string; options: RequestInit };
function respond(body: unknown, status = 200, contentType = "application/json") {
  const calls: Call[] = [];
  globalThis.fetch = (async (path, options) => { calls.push({ path: String(path), options: options ?? {} }); return new Response(status === 204 ? null : contentType === "application/json" ? JSON.stringify(body) : String(body), { status, headers: { "Content-Type": contentType, "X-Request-Id": "synthetic-request" } }); }) as typeof fetch;
  return calls;
}
describe("Business report transport", () => {
  const originalFetch = globalThis.fetch;
  const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
  const originalGrant = getChosenGrant();
  beforeEach(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; setChosenGrant(scope.grantId); });
  afterEach(() => { globalThis.fetch = originalFetch; setChosenGrant(originalGrant); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });
  test("sends only the public request, exact grant and no-store while keeping all-match totals", async () => {
    const calls = respond(answer());
    const report = reportRequestSchema.parse({ filters: { amount_min: "1000.01", currencies: ["DOP"], period: { kind: "all" } } });
    const result = await queryBusinessReport(scope, report);
    expect(result.matching_count).toBe(102);
    expect(result.totals[0].amount).toBeNull();
    expect(result.totals[0].known_amount).toBe("1234567.89");
    expect(calls[0].path.endsWith("/business/reports/query")).toBe(true);
    expect(calls[0].options.cache).toBe("no-store");
    expect(calls[0].options.credentials).toBe("omit");
    expect(new Headers(calls[0].options.headers).get("X-Business-Grant")).toBe(scope.grantId);
    expect(JSON.parse(String(calls[0].options.body))).toEqual(report);
    expect(calls[0].options.body).not.toContain("synthetic-business");
  });
  test("refuses unsupported preference/sort keys before sending", async () => {
    const calls = respond(answer());
    await expect(queryBusinessReport(scope, { ...reportRequestSchema.parse({}), density: "compact" } as never)).rejects.toThrow();
    await expect(queryBusinessReport(scope, { ...reportRequestSchema.parse({}), sort: "amount_desc" } as never)).rejects.toThrow();
    expect(calls).toHaveLength(0);
  });
  test("a changed grant before or during a response never yields records", async () => {
    const calls = respond(answer());
    setChosenGrant(null);
    await expect(queryBusinessReport(scope, reportRequestSchema.parse({}))).rejects.toThrow("scope changed");
    expect(calls).toHaveLength(0);
    setChosenGrant(scope.grantId);
    globalThis.fetch = (async () => { setChosenGrant(null); return Response.json(answer()); }) as typeof fetch;
    await expect(queryBusinessReport(scope, reportRequestSchema.parse({}))).rejects.toThrow("scope changed");
  });
  test("exports the full ZIP with the shown fingerprint, with no automatic changed-set retry", async () => {
    const report = reportRequestSchema.parse({ page: 4, page_size: 50 });
    const calls = respond("complete archive", 200, "application/zip");
    expect(await (await exportBusinessReport(scope, report, "a".repeat(64))).text()).toBe("complete archive");
    expect(JSON.parse(String(calls[0].options.body))).toEqual({ report, expected_fingerprint: "a".repeat(64) });
    const changed = respond({ detail: { code: "business_report_changed" } }, 409);
    const error = await exportBusinessReport(scope, report, "a".repeat(64)).catch((error) => error);
    expect(error.code).toBe("business_report_changed");
    expect(error.requestId).toBe("synthetic-request");
    expect(changed).toHaveLength(1);
  });
  test("private view CRUD preserves preset, expected version and replay key, including an empty DELETE", async () => {
    const recipe = reportRequestSchema.parse({ filters: { period: { kind: "this_month", from_date: null, to_date: null } } });
    const { page, page_size, ...savedRecipe } = recipe;
    expect([page, page_size]).toEqual([1, 25]);
    const view = { id: "00000000-0000-4000-8000-000000000002", name: "Compras", recipe: savedRecipe, version: 2, created_at: "2026-10-26", updated_at: "2026-10-26" };
    respond([view]);
    expect((await listBusinessReportViews(scope))[0].recipe.filters.period.kind).toBe("this_month");
    const calls = respond(view);
    await mutateBusinessReportView(scope, { kind: "update", id: view.id, key: "same-command", body: { name: view.name, recipe: savedRecipe, expected_version: 1 } });
    expect(new Headers(calls[0].options.headers).get("Idempotency-Key")).toBe("same-command");
    expect(JSON.parse(String(calls[0].options.body)).expected_version).toBe(1);
    const deleted = respond(null, 204);
    expect(await mutateBusinessReportView(scope, { kind: "delete", id: view.id, key: "delete-command", body: { expected_version: 2 } })).toBeNull();
    expect(deleted[0].options.method).toBe("DELETE");
  });
});
