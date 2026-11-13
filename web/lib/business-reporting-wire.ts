import {
  downloadRecordsExport, listBusinessReportViews, mutateBusinessReportView, previewRecordsExport, queryBusinessReport,
  reportRecipeSchema, reportRequestSchema,
  type ReportAnswer, type ReportColumn, type ReportProblem, type ReportRecipe, type ReportRequest, type ReportScope, type ReportViewCommand, type SavedReportView, type ReportPresentation,
} from "./business-reports-api";
import type { ReportRecord } from "./business-reports-api";
import { consumeOverlayEntriesForNavigation } from "./overlay-history";
import type { RecordRow } from "@/components/business-app/transacciones/transacciones-model";
import type { SettlementSummary } from "@/components/business-app/transacciones/records-results-preview";
import type { RecordsSort } from "@/components/business-app/transacciones/records-pagination";
import type { ReportSort } from "./business-reports-api";
import type { RecordsViewPreferences } from "@/components/business-app/transacciones/records-view-preferences";
import { DENSITIES, DENSITY_ROW_PX } from "@/components/business-app/transacciones/table-density";

const SORT_KEYS = { fecha: "date", contraparte: "name", monto: "amount" } as const;
export function recordsSortToReport(sort: RecordsSort): ReportSort {
  return `${SORT_KEYS[sort.key]}_${sort.direction}`;
}
export function reportSortToRecords(sort: ReportSort): RecordsSort {
  const key = (Object.keys(SORT_KEYS) as RecordsSort["key"][]).find((key) => sort.startsWith(`${SORT_KEYS[key]}_`))!;
  return { key, direction: sort.endsWith("_asc") ? "asc" : "desc" };
}
export function reportPresentationToRecords(presentation: ReportPresentation, sort: ReportSort, columns: readonly ReportColumn[]): RecordsViewPreferences {
  return { columns, order: presentation.order, hidden: presentation.hidden, density: DENSITIES.find((density) => DENSITY_ROW_PX[density] === presentation.density)!, sort: reportSortToRecords(sort) };
}
export function recordsPresentationToReport(preferences: RecordsViewPreferences): ReportPresentation {
  return { order: preferences.order, hidden: preferences.hidden, density: DENSITY_ROW_PX[preferences.density] };
}

export function businessReportRow(report: ReportRecord): RecordRow {
  const activityId = report.linked_activity_ids[0];
  return {
    report, id: activityId ?? report.draft_id ?? report.row_id,
    kind: report.family === "sale" ? "venta" : "gasto", occurredOn: report.report_date ?? "", counterparty: report.counterparty,
    money: { amount: report.gross_amount ?? "", currency: report.currency ?? "" }, categoryId: report.category_key === "uncategorized" ? null : report.category_key,
    account: report.funding_kind === "checking" || report.funding_kind === "savings" ? { kind: "bank", name: report.funding_label } : report.funding_kind === "credit_card" ? { kind: "card", name: report.funding_label } : report.funding_kind === "cash" ? { kind: "cash", name: report.funding_label } : null,
    hasProof: report.has_document, marks: { personal: report.personal ?? false, markedBy: null, fiscal: null },
    opens: report.draft_id ? { kind: "draft", draftId: report.draft_id, list: "transactions" } : activityId ? { kind: "expense", expenseId: activityId } : null,
  };
}

const SUMMARY_KIND = { venta: "income", gasto: "expense" } as const;
/** First card: the server's document-family total per currency for the family. Settled and balance stay unavailable until allocation exists. */
export function reportSummary(answer: ReportAnswer | undefined, kind: RecordRow["kind"]): SettlementSummary {
  const currencies = (answer?.totals ?? [])
    .filter((total) => total.basis === "document_family_amount" && total.kind === SUMMARY_KIND[kind])
    .map((total) => ({ currency: total.currency ?? "", total: total.complete ? total.amount : null, known: total.complete ? null : total.known_amount, settled: null, balance: null }))
    .sort((a, b) => Number(!a.currency) - Number(!b.currency) || a.currency.localeCompare(b.currency));
  return { currencies, exclusions: { unconfirmed: 0, personal: answer?.excluded_personal?.[SUMMARY_KIND[kind]] ?? 0, unavailable: 0 } };
}

export const defaultReportRequest = (): ReportRequest => reportRequestSchema.parse({});
export const recipeFromRequest = (request: ReportRequest, presentation?: ReportPresentation): ReportRecipe => {
  const recipe = { schema_version: request.schema_version, filters: request.filters, sort: request.sort };
  return reportRecipeSchema.parse(request.schema_version === 2 ? { ...recipe, presentation: request.presentation ?? presentation, page_size: request.page_size } : recipe);
};
export type ReportFailure = { kind: "access" | "version" | "conflict" | "unavailable" | "uncertain" | "failed"; code: string; requestId?: string };
export function reportFailure(error: unknown, mutation = false): ReportFailure {
  const problem = error as ReportProblem | null;
  const code = typeof problem?.code === "string" ? problem.code : "unknown";
  const status = problem?.status;
  const kind = status === 401 || status === 403 || problem?.name === "ChatAccountChangedError" || problem?.message === "Browser session changed" || ["business_closed", "business_grant_not_live", "business_report_scope_changed"].includes(code) ? "access"
    : code === "business_report_view_changed" || code === "stale_version" ? "version"
    : ["idempotency_conflict", "business_action_conflict", "supporting_file_already_linked"].includes(code) ? "conflict"
    : ["business_report_too_large", "business_pilot_disabled", "business_reports_unavailable", "business_annotation_unavailable", "business_annotation_unsupported", "document_source_unavailable"].includes(code) ? "unavailable"
    : problem?.name === "ZodError" ? "failed"
    : mutation && (status === undefined || status >= 500) ? "uncertain" : "failed";
  return { kind, code, requestId: problem?.requestId };
}
export type ReportLoad =
  | { kind: "idle" | "loading" }
  | { kind: "ready"; answer: ReportAnswer }
  | { kind: "failed"; problem: ReportFailure };
export type ViewLoad = { kind: "idle" | "loading" } | { kind: "ready"; items: SavedReportView[] } | { kind: "failed"; problem: ReportFailure };
export type ReportOperation = { kind: "idle" | "busy" } | { kind: "failed"; problem: ReportFailure } | { kind: "done" };
export type ViewOperation = ReportOperation & { command?: ReportViewCommand };
/** What one view write did: the saved view the server returned, or why it did not land. An unconfirmed write also carries `confirmed`, its outcome once a retry with its key is answered. */
export type ViewWriteResult = { kind: "done"; view: SavedReportView | null } | { kind: "failed"; problem: ReportFailure; confirmed?: Promise<ViewWriteResult> };
export type ReportState = Readonly<{ request: ReportRequest; load: ReportLoad; views: ViewLoad; viewOperation: ViewOperation; anchor: string | null; missingAnchor: boolean }>;
export type ReportingTransport = {
  query: typeof queryBusinessReport; exportPreview: typeof previewRecordsExport; exportFile: typeof downloadRecordsExport;
  listViews: typeof listBusinessReportViews; mutateView: typeof mutateBusinessReportView;
};
export const liveReportingTransport: ReportingTransport = { query: queryBusinessReport, exportPreview: previewRecordsExport, exportFile: downloadRecordsExport, listViews: listBusinessReportViews, mutateView: mutateBusinessReportView };

/** An instance belongs to one person, Business and selected grant. Replace it when any changes. */
export function createBusinessReportController(scope: ReportScope, initial = defaultReportRequest(), transport: ReportingTransport = liveReportingTransport) {
  let state: ReportState = { request: reportRequestSchema.parse(initial), load: { kind: "idle" }, views: { kind: "idle" }, viewOperation: { kind: "idle" }, anchor: null, missingAnchor: false };
  const listeners = new Set<() => void>();
  let generation = 0;
  let queryVersion = 0;
  let viewsVersion = 0;
  let queryAbort: AbortController | undefined;
  const operations = new Set<AbortController>();
  // View writes run one at a time, in the order asked. A write asked for while another runs waits for it.
  let viewWrites: Promise<unknown> = Promise.resolve();
  // Callers of an unconfirmed write wait here by its key. The next answer to that key settles them, and so does the end of this scope.
  const unconfirmed = new Map<string, { confirmed: Promise<ViewWriteResult>; settle: (result: ViewWriteResult) => void }>();
  const confirmation = (key: string) => {
    const waiting = unconfirmed.get(key);
    if (waiting) return waiting.confirmed;
    let settle: (result: ViewWriteResult) => void = () => undefined;
    const confirmed = new Promise<ViewWriteResult>((resolve) => { settle = resolve; });
    unconfirmed.set(key, { confirmed, settle });
    return confirmed;
  };
  const answer = (key: string, result: ViewWriteResult) => { unconfirmed.get(key)?.settle(result); unconfirmed.delete(key); return result; };
  const abandonUnconfirmed = (problem: ReportFailure) => { for (const key of [...unconfirmed.keys()]) answer(key, { kind: "failed", problem }); };
  const publish = (patch: Partial<ReportState>) => { state = { ...state, ...patch }; listeners.forEach((listener) => listener()); };
  const abortOperations = () => { queryAbort?.abort(); for (const operation of operations) operation.abort(); operations.clear(); };
  const revoke = (problem: ReportFailure) => {
    generation += 1;
    abortOperations();
    publish({ load: { kind: "failed", problem }, views: { kind: "failed", problem }, viewOperation: { kind: "idle" }, anchor: null });
    abandonUnconfirmed(problem);
  };
  const writeView = async (snapshot: ReportViewCommand, currentGeneration: number): Promise<ViewWriteResult> => {
    if (currentGeneration !== generation) return { kind: "failed", problem: { kind: "access", code: "business_report_scope_changed" } };
    // An uncertain write is retried with its own key before any other write runs.
    if (state.viewOperation.kind === "failed" && state.viewOperation.problem.kind === "uncertain" && state.viewOperation.command?.key !== snapshot.key) return { kind: "failed", problem: state.viewOperation.problem };
    const abort = new AbortController();
    operations.add(abort);
    publish({ viewOperation: { kind: "busy", command: snapshot } });
    try {
      const saved = await transport.mutateView(scope, snapshot, abort.signal);
      if (abort.signal.aborted || currentGeneration !== generation) return { kind: "failed", problem: { kind: "access", code: "business_report_scope_changed" } };
      const existing = state.views.kind === "ready" ? state.views.items : [];
      const items = snapshot.kind === "delete" ? existing.filter((view) => view.id !== snapshot.id) : saved ? [...existing.filter((view) => view.id !== saved.id), saved] : existing;
      publish({ views: { kind: "ready", items }, viewOperation: { kind: "done" } });
      return answer(snapshot.key, { kind: "done", view: saved });
    } catch (error) {
      const problem = reportFailure(error, true);
      if (abort.signal.aborted || currentGeneration !== generation) return { kind: "failed", problem };
      if (problem.kind === "access") revoke(problem);
      else publish({ viewOperation: { kind: "failed", problem, command: snapshot } });
      return problem.kind === "uncertain" ? { kind: "failed", problem, confirmed: confirmation(snapshot.key) } : answer(snapshot.key, { kind: "failed", problem });
    } finally { operations.delete(abort); }
  };
  const controller = {
    getSnapshot: () => state,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
    dispose: () => { generation += 1; abortOperations(); abandonUnconfirmed({ kind: "access", code: "business_report_scope_changed" }); },
    revoke: () => revoke({ kind: "access", code: "business_report_scope_changed" }),
    async load(request = state.request): Promise<void> {
      const report = reportRequestSchema.parse(request);
      queryAbort?.abort();
      const abort = new AbortController();
      queryAbort = abort;
      const version = ++queryVersion;
      const currentGeneration = generation;
      publish({ request: report, load: { kind: "loading" }, missingAnchor: false });
      try {
        const answer = await transport.query(scope, report, abort.signal);
        if (abort.signal.aborted || version !== queryVersion || currentGeneration !== generation) return;
        if (answer.page !== report.page || answer.page_size !== report.page_size || answer.items.length > report.page_size) throw new Error("Invalid report page response");
        // A page the records no longer have opens the last one that exists.
        const lastPage = Math.max(1, answer.page_count);
        if (report.page > lastPage) return controller.load({ ...state.request, page: lastPage });
        // The request's layout becomes the server's upgrade of it, unless the person changed it while this answer was on its way.
        const sent = report.schema_version === 2 ? report.presentation : undefined;
        const request = sent && state.request.schema_version === 2 && state.request.presentation === sent ? { ...state.request, presentation: answer.presentation } : state.request;
        publish({ request, load: { kind: "ready", answer }, missingAnchor: state.anchor !== null && !answer.items.some((row) => row.row_id === state.anchor) });
      } catch (error) {
        if (abort.signal.aborted || version !== queryVersion || currentGeneration !== generation) return;
        const problem = reportFailure(error);
        if (problem.kind === "access") revoke(problem);
        else publish({ load: { kind: "failed", problem } });
      }
    },
    setRecipe: (recipe: ReportRecipe) => controller.load({ ...reportRecipeSchema.parse(recipe), page: 1, page_size: recipe.schema_version === 2 ? recipe.page_size : state.request.page_size }),
    setPage: (page: number) => controller.load({ ...state.request, page }),
    setPageSize: (page_size: ReportRequest["page_size"]) => controller.load({ ...state.request, page: 1, page_size }),
    setPresentation(presentation: ReportPresentation) {
      if (state.request.schema_version !== 2) throw new Error("Report presentation requires schema version 2");
      publish({ request: reportRequestSchema.parse({ ...state.request, presentation }) });
    },
    restorePresentation() {
      if (state.request.schema_version !== 2) throw new Error("Report presentation requires schema version 2");
      const request = { ...state.request };
      delete request.presentation;
      return controller.load(request);
    },
    refresh: () => controller.load(),
    rememberAnchor: (rowId: string | null) => publish({ anchor: rowId, missingAnchor: false }),
    async listViews() {
      const currentGeneration = generation;
      const version = ++viewsVersion;
      const abort = new AbortController();
      operations.add(abort);
      publish({ views: { kind: "loading" } });
      try {
        const items = await transport.listViews(scope, abort.signal);
        if (!abort.signal.aborted && generation === currentGeneration && version === viewsVersion) publish({ views: { kind: "ready", items } });
      } catch (error) {
        if (abort.signal.aborted || generation !== currentGeneration || version !== viewsVersion) return;
        const problem = reportFailure(error);
        if (problem.kind === "access") revoke(problem);
        else publish({ views: { kind: "failed", problem } });
      } finally { operations.delete(abort); }
    },
    mutateView(command: ReportViewCommand): Promise<ViewWriteResult> {
      // Keep the exact command and key after an uncertain response. Retrying must not create a second write.
      const snapshot = structuredClone(command);
      const currentGeneration = generation;
      const write = viewWrites.then(() => writeView(snapshot, currentGeneration));
      viewWrites = write.catch(() => undefined);
      return write;
    },
    retryView: (): Promise<ViewWriteResult | null> => state.viewOperation.kind === "failed" && state.viewOperation.problem.kind === "uncertain" && state.viewOperation.command ? controller.mutateView(state.viewOperation.command) : Promise.resolve(null),
    openView: (view: SavedReportView) => controller.setRecipe(view.recipe),
  };
  return controller;
}
export type BusinessReportController = ReturnType<typeof createBusinessReportController>;

export function reportLocation(request: ReportRequest, anchor: string | null): string {
  const params = new URLSearchParams({ report: JSON.stringify(request) });
  if (anchor) params.set("report_row", anchor);
  return params.toString();
}
/** The one writer of the report into the address bar. A step taken from an open sheet lands on the entry the sheet pushed; pushed on top, the sheet's closing back() would undo it. */
export function writeReportLocation(request: ReportRequest, anchor: string | null, scopeKey: string, push: boolean): void {
  const url = new URL(window.location.href);
  new URLSearchParams(reportLocation(request, anchor)).forEach((value, key) => url.searchParams.set(key, value));
  if (!anchor) url.searchParams.delete("report_row");
  url.searchParams.set("report_scope", scopeKey);
  if (url.href === window.location.href) return;
  const step = push && !consumeOverlayEntriesForNavigation();
  window.history[step ? "pushState" : "replaceState"](null, "", `${url.pathname}${url.search}`);
}
export function restoreReportLocation(params: URLSearchParams): { request: ReportRequest; anchor: string | null } {
  try {
    const encoded = params.get("report");
    if (!encoded) return { request: defaultReportRequest(), anchor: params.get("report_row") };
    const linked = JSON.parse(encoded);
    // An old link still names the first table's columns, which nothing reads.
    if (linked && typeof linked === "object") delete linked.columns;
    return { request: reportRequestSchema.parse(linked), anchor: params.get("report_row") };
  } catch { return { request: defaultReportRequest(), anchor: null }; }
}
