import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { createBusinessReportHttpFixture } from "./fixtures/business-report-http-fixture";
import { getChosenGrant, setChosenGrant } from "@/lib/business-grant";
import { appendBusinessReportSupportingFile, exportBusinessReport, listBusinessReportViews, mutateBusinessReportView, queryBusinessReport, reportRecordSchema, reportRequestSchema, reportTotalSchema, setBusinessReportCurrentNote, type ReportScope } from "@/lib/business-reports-api";

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
  test("a needs_fiscal_data row with its export fields parses instead of breaking Registros", () => {
    const row = { ...createBusinessReportHttpFixture().records[0], stage: "needs_fiscal_data", export_missing: "ncf_missing", export_line: false };
    const parsed = reportRecordSchema.parse(row);
    expect(parsed.stage).toBe("needs_fiscal_data");
    expect(parsed.export_missing).toBe("ncf_missing");
    expect(parsed.export_line).toBe(false);
  });
  test("large decimal response money stays exact while fractional or infinite minor metadata is rejected", () => {
    const total = { ...answer().totals[0], known_amount_minor: 900719925474099300, known_amount: "9007199254740993.00", amount_minor: -2000, amount: "-20.00" };
    expect(reportTotalSchema.parse(total).known_amount).toBe("9007199254740993.00");
    expect(reportTotalSchema.parse(total).amount).toBe("-20.00");
    expect(reportTotalSchema.safeParse({ ...total, known_amount_minor: 1.5 }).success).toBe(false);
    expect(reportTotalSchema.safeParse({ ...total, amount_minor: Infinity }).success).toBe(false);
  });
  test("refuses unsupported preference/sort keys before sending", async () => {
    const calls = respond(answer());
    await expect(queryBusinessReport(scope, { ...reportRequestSchema.parse({}), density: "compact" } as never)).rejects.toThrow();
    await expect(queryBusinessReport(scope, { ...reportRequestSchema.parse({}), sort: "amount_desc" } as never)).rejects.toThrow();
    expect(calls).toHaveLength(0);
  });
  test("v2 sends complete presentation and keeps intended sort separate from the server fallback", async () => {
    const calls = respond({ ...answer(), overview: { needs_review: 40, awaiting_approval: 60, ready_for_export: 2 }, effective_sort: "date_desc", sort_unavailable_reason: "amount_sort_requires_single_known_currency" });
    const report = reportRequestSchema.parse({ schema_version: 2, sort: "amount_asc", page_size: 100, presentation: { density: 56, hidden: ["funding", "note"] } });
    const result = await queryBusinessReport(scope, report);
    expect(JSON.parse(String(calls[0].options.body))).toEqual(report);
    expect(result.effective_sort).toBe("date_desc");
    expect(result.overview?.needs_review).toBe(40);
    expect(report.sort).toBe("amount_asc");
    expect(report.schema_version === 2 && report.presentation.density).toBe(56);
    expect(() => reportRequestSchema.parse({ ...report, presentation: { ...report.schema_version === 2 ? report.presentation : {}, hidden: ["gross_amount"] } })).toThrow();
  });
  test("a changed grant before or during a response never yields records", async () => {
    const calls = respond(answer());
    setChosenGrant(null);
    await expect(queryBusinessReport(scope, reportRequestSchema.parse({}))).rejects.toThrow("scope changed");
    expect(calls).toHaveLength(0);
    setChosenGrant(scope.grantId);
    globalThis.fetch = (async () => { setChosenGrant(null); return Response.json(answer()); }) as typeof fetch;
    await expect(queryBusinessReport(scope, reportRequestSchema.parse({}))).rejects.toThrow("scope changed");
    setChosenGrant(scope.grantId);
    globalThis.fetch = (async () => { setChosenGrant(null); setChosenGrant(scope.grantId); return Response.json(answer()); }) as typeof fetch;
    await expect(queryBusinessReport(scope, reportRequestSchema.parse({}))).rejects.toThrow("scope changed");
    globalThis.fetch = (async () => {
      const response = Response.json(answer());
      response.json = async () => { setChosenGrant(null); setChosenGrant(scope.grantId); return answer(); };
      return response;
    }) as typeof fetch;
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
    if (recipe.schema_version !== 1) throw new Error("Expected v1 recipe");
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
  test("current-note commands use code point limits and preserve durable replay version separately from the current dossier", async () => {
    const draftId = "00000000-0000-4000-8000-000000000003";
    const dossier = { draft_id: draftId, version: 5, current_note: "Actual", note_edit_available: true, supporting_append_available: true, annotation_unavailable_reason: null };
    const note = "🟢".repeat(500);
    const calls = respond({ result: { draft_id: draftId, version: 3, note }, dossier });
    const result = await setBusinessReportCurrentNote(scope, { draftId, expectedVersion: 2, key: "note-command", note });
    expect(result.result.version).toBe(3);
    expect(result.dossier.version).toBe(5);
    expect(calls[0].options.method).toBe("PUT");
    expect(JSON.parse(String(calls[0].options.body))).toEqual({ expected_version: 2, note });
    expect(new Headers(calls[0].options.headers).get("Idempotency-Key")).toBe("note-command");
    await expect(setBusinessReportCurrentNote(scope, { draftId, expectedVersion: 2, key: "note-too-long", note: note + "x" })).rejects.toThrow();
    expect(calls).toHaveLength(1);
  });
  test("supporting uploads send one raw file with exact version, encoded name and same retry key", async () => {
    const draftId = "00000000-0000-4000-8000-000000000003";
    const dossier = { draft_id: draftId, version: 8, current_note: null, note_edit_available: true, supporting_append_available: true, annotation_unavailable_reason: null };
    const calls = respond({ result: { draft_id: draftId, version: 6, outcome: "duplicate", source_id: "00000000-0000-4000-8000-000000000004", receipt_id: "00000000-0000-4000-8000-000000000005", sha256: "b".repeat(64) }, dossier });
    const file = new File(["synthetic PDF"], "Leche 🐄.pdf", { type: "application/pdf" });
    const result = await appendBusinessReportSupportingFile(scope, { draftId, expectedVersion: 5, file, key: "supporting-command" });
    expect(result.result.outcome).toBe("duplicate");
    expect(result.dossier.version).toBe(8);
    expect(calls[0].options.body).toBe(file);
    const headers = new Headers(calls[0].options.headers);
    expect(headers.get("Content-Type")).toBe("application/pdf");
    expect(headers.get("X-Draft-Version")).toBe("5");
    expect(decodeURIComponent(headers.get("X-Document-Filename")!)).toBe(file.name);
    expect(headers.get("Idempotency-Key")).toBe("supporting-command");
  });
});
