import { describe, expect, test } from "bun:test";
import { businessReportRow, createBusinessReportController, defaultReportRequest, recipeFromRequest, recordsPresentationToReport, reportPresentationToRecords, reportFailure, reportLocation, restoreReportLocation, type ReportingTransport } from "@/lib/business-reporting-wire";
import type { ReportAnswer, ReportRequest, ReportViewCommand, SavedReportView } from "@/lib/business-reports-api";
import { reportRequestSchema } from "@/lib/business-reports-api";

const answer = (request: ReportRequest, count = 125): ReportAnswer => ({ items: [], matching_count: count, page: request.page, page_size: request.page_size, page_count: Math.ceil(count / request.page_size), totals: [], fingerprint: "a".repeat(64), captured_at: "2026-10-26", resolved_period: { from_date: null, to_date: null, calendar: "America/Santo_Domingo" }, excluded_unknown_dates: 0, counterparties: [], categories: [], funding_sources: [], coverage_notes: ["legal_cancellation_coverage_unavailable"] });
const scope = { userId: "person", businessId: "business-a", grantId: null };
const problem = (status: number, code: string) => Object.assign(new Error(code), { status, code });
const transport = (overrides: Partial<ReportingTransport> = {}): ReportingTransport => ({ query: async (_scope, request) => answer(request), export: async () => new Blob(["archive"]), listViews: async () => [], mutateView: async () => null, ...overrides });
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>((done) => { resolve = done; }); return { promise, resolve }; }

describe("Business report controller", () => {
  test("annotation failures keep stale versions, command conflicts and uncertain storage outcomes distinct", () => {
    expect(reportFailure(problem(409, "stale_version"), true).kind).toBe("version");
    expect(reportFailure(problem(409, "business_action_conflict"), true).kind).toBe("conflict");
    expect(reportFailure(problem(422, "business_annotation_unavailable"), true).kind).toBe("unavailable");
    expect(reportFailure(problem(422, "supporting_file_already_linked"), true).kind).toBe("conflict");
    expect(reportFailure(problem(503, "document_storage_unavailable"), true).kind).toBe("uncertain");
  });
  test("canonical row facts keep unknowns and exact amounts without deriving payment or readiness", () => {
    const report = { row_id: "draft:one", draft_id: "one", linked_activity_ids: ["activity-one"], revision: 4, report_date: null, date_basis: "document_issue" as const, family: null, stage: null, technical_state: "processing", workflow_blockers: ["waiting_for_evidence"], currency: "DOP", gross_amount: "9007199254740.01", recorded_amount: null, recorded_currency: null, proposed_amount: null, money_kind: "unknown", money_effect: "unknown" as const, adjustment_effect: null, counterparty: null, counterparty_key: null, category_key: "uncategorized", funding_key: null, funding_label: null, funding_kind: null, has_document: true, document_kind: "unknown" as const, fiscal_classification: "unknown", fiscal_number: null, note: "Current note", settlement_status: "paid", dependency_fingerprint: "dependency" };
    const row = businessReportRow(report);
    expect(row.report).toBe(report);
    expect(row.money).toEqual({ amount: "9007199254740.01", currency: "DOP" });
    expect(row.occurredOn).toBe("");
    expect(row.opens).toEqual({ kind: "draft", draftId: "one", list: "transactions" });
    expect(row.hasProof).toBe(true);
    expect(row.report?.stage).toBeNull();
    expect(businessReportRow({ ...report, currency: null, gross_amount: null }).money).toEqual({ amount: "", currency: "" });
  });
  test("server page/count/totals remain authoritative and page size/recipe reset page one", async () => {
    const requests: ReportRequest[] = [];
    const controller = createBusinessReportController(scope, { ...defaultReportRequest(), page: 4 }, transport({ query: async (_scope, request) => { requests.push(request); return answer(request); } }));
    await controller.load();
    expect(controller.getSnapshot().load.kind).toBe("ready");
    await controller.setPageSize(100);
    expect(controller.getSnapshot().request.page).toBe(1);
    await controller.setRecipe({ ...recipeFromRequest(defaultReportRequest()), filters: { ...defaultReportRequest().filters, period: { kind: "this_year" } } });
    expect(requests.at(-1)?.filters.period).toEqual({ kind: "this_year" });
    expect(requests.at(-1)?.page).toBe(1);
  });
  test("a v2 saved recipe preserves relative period, presentation, intended sort and saved size at page one", async () => {
    const request = reportRequestSchema.parse({ schema_version: 2, page: 4, page_size: 100, filters: { period: { kind: "last_month" } }, sort: "name_asc", presentation: { density: 40, hidden: ["attachment"] } });
    const recipe = recipeFromRequest(request);
    const controller = createBusinessReportController(scope, undefined, transport());
    await controller.openView({ id: "saved", name: "Compras", recipe, version: 3, created_at: "now", updated_at: "now" });
    expect(controller.getSnapshot().request).toEqual({ ...request, page: 1 });
    expect(recipe).not.toHaveProperty("page");
  });
  test("presentation round trips all columns and changes density without another query or page reset", async () => {
    const request = reportRequestSchema.parse({ schema_version: 2, page: 4 });
    if (request.schema_version !== 2) throw new Error("Expected v2 request");
    const preferences = reportPresentationToRecords(request.presentation, "name_desc");
    expect(recordsPresentationToReport(preferences)).toEqual(request.presentation);
    let reads = 0;
    const controller = createBusinessReportController(scope, request, transport({ query: async (_scope, query) => { reads++; return answer(query); } }));
    await controller.load();
    const before = controller.getSnapshot().load;
    controller.setPresentation({ ...request.presentation, density: 56 });
    expect(reads).toBe(1);
    expect(controller.getSnapshot().request.page).toBe(4);
    expect(controller.getSnapshot().load).toBe(before);
    expect(controller.getSnapshot().request.schema_version === 2 && controller.getSnapshot().request.presentation.density).toBe(56);
  });
  test("late query and disposed Business responses cannot replace current scope", async () => {
    const first = deferred<ReportAnswer>();
    let calls = 0;
    const controller = createBusinessReportController(scope, undefined, transport({ query: async (_scope, request) => ++calls === 1 ? first.promise : answer(request, 70) }));
    const old = controller.load();
    await controller.setPage(2);
    first.resolve(answer(defaultReportRequest(), 999));
    await old;
    const current = controller.getSnapshot().load;
    expect(current.kind === "ready" && current.answer.matching_count).toBe(70);
    const pending = deferred<ReportAnswer>();
    const other = createBusinessReportController(scope, undefined, transport({ query: () => pending.promise }));
    const read = other.load(); other.revoke(); pending.resolve(answer(defaultReportRequest())); await read;
    expect(other.getSnapshot().load.kind).toBe("failed");
    expect(other.getSnapshot().views.kind).toBe("failed");
  });
  test("a removed last page has explicit current-page recovery and missing anchor state", async () => {
    const controller = createBusinessReportController(scope, { ...defaultReportRequest(), page: 8 }, transport({ query: async (_scope, request) => answer(request, 30) }));
    controller.rememberAnchor("draft:removed"); await controller.load();
    expect(controller.getSnapshot().load.kind).toBe("invalid-page");
    expect(controller.getSnapshot().missingAnchor).toBe(true);
    await controller.recoverPage();
    expect(controller.getSnapshot().request.page).toBe(2);
  });
  test("export 409 stays failed until explicit refresh; it never retries with a new set", async () => {
    let exports = 0; let reads = 0;
    const controller = createBusinessReportController(scope, undefined, transport({ query: async (_scope, request) => { reads++; return answer(request); }, export: async () => { exports++; throw problem(409, "business_report_changed"); } }));
    await controller.load(); await controller.export();
    expect(controller.getSnapshot().export).toEqual({ kind: "failed", problem: { kind: "changed", code: "business_report_changed", requestId: undefined } });
    expect([reads, exports]).toEqual([1, 1]);
    await controller.refresh(); expect(reads).toBe(2);
  });
  test("an uncertain view write replays the frozen command/key, while stale versions require reconciliation", async () => {
    const commands: ReportViewCommand[] = [];
    const command: ReportViewCommand = { kind: "create", key: "original-key", body: { name: "Compras", recipe: recipeFromRequest(defaultReportRequest()) } };
    const controller = createBusinessReportController(scope, undefined, transport({ mutateView: async (_scope, snapshot) => { commands.push(snapshot); if (commands.length === 1) throw new TypeError("connection lost"); return { ...snapshot.body, id: "saved", version: 1, created_at: "now", updated_at: "now" } as SavedReportView; } }));
    await controller.mutateView(command); command.body.name = "Changed after request";
    await controller.retryView();
    expect(commands.map((value) => [value.key, value.kind === "create" ? value.body.name : ""])).toEqual([["original-key", "Compras"], ["original-key", "Compras"]]);
    const stale = createBusinessReportController(scope, undefined, transport({ mutateView: async () => { throw problem(409, "business_report_view_changed"); } }));
    await stale.mutateView(command); await stale.retryView();
    expect(stale.getSnapshot().viewOperation.kind === "failed" && stale.getSnapshot().viewOperation.problem.kind).toBe("version");
  });
  test("revoked access clears existing rows and private views", async () => {
    let forbidden = false;
    const controller = createBusinessReportController(scope, undefined, transport({ query: async (_scope, request) => { if (forbidden) throw problem(403, "business_grant_not_live"); return answer(request); } }));
    await controller.load(); await controller.listViews(); forbidden = true; await controller.refresh();
    expect(controller.getSnapshot().load.kind).toBe("failed"); expect(controller.getSnapshot().views.kind).toBe("failed");
  });
  test("URL restores later numbered page and stable row; malformed or unsupported state reports recovery", () => {
    const request = { ...defaultReportRequest(), page: 4, page_size: 50 as const };
    expect(restoreReportLocation(new URLSearchParams(reportLocation(request, "draft:one")))).toEqual({ request, anchor: "draft:one", invalid: false });
    expect(restoreReportLocation(new URLSearchParams({ report: JSON.stringify({ ...request, sort: "amount_desc" }) })).invalid).toBe(true);
  });
});
