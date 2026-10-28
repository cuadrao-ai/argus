import {
  exportBusinessReport, listBusinessReportViews, mutateBusinessReportView, queryBusinessReport,
  reportRecipeSchema, reportRequestSchema,
  type ReportAnswer, type ReportProblem, type ReportRecipe, type ReportRequest, type ReportScope, type ReportViewCommand, type SavedReportView, type ReportPresentation,
} from "./business-reports-api";
import type { ReportRecord } from "./business-reports-api";
import type { RecordRow } from "@/components/business-app/transacciones/transacciones-model";
import type { SettlementSummary } from "@/components/business-app/transacciones/records-results-preview";
import type { RecordsSort } from "@/components/business-app/transacciones/records-pagination";
import type { ReportSort } from "./business-reports-api";
import type { RecordsColumnKey, RecordsViewPreferences } from "@/components/business-app/transacciones/records-view-preferences";
import { DENSITIES, DENSITY_ROW_PX } from "@/components/business-app/transacciones/table-density";

const SORT_KEYS = { fecha: "date", contraparte: "name", monto: "amount" } as const;
export function recordsSortToReport(sort: RecordsSort): ReportSort {
  return `${SORT_KEYS[sort.key]}_${sort.direction}`;
}
export function reportSortToRecords(sort: ReportSort): RecordsSort {
  const key = (Object.keys(SORT_KEYS) as RecordsSort["key"][]).find((key) => sort.startsWith(`${SORT_KEYS[key]}_`))!;
  return { key, direction: sort.endsWith("_asc") ? "asc" : "desc" };
}
const COLUMN_KEYS: Record<RecordsColumnKey, ReportPresentation["order"][number]> = { contraparte: "counterparty", fecha: "date", monto: "gross_amount", moneda: "currency", detalle: "family", categoria: "category", estado: "stage", notas: "note", comprobante: "attachment", cuenta: "funding" };
const recordColumnKey = (key: ReportPresentation["order"][number]): RecordsColumnKey => (Object.keys(COLUMN_KEYS) as RecordsColumnKey[]).find((column) => COLUMN_KEYS[column] === key)!;
export function reportPresentationToRecords(presentation: ReportPresentation, sort: ReportSort): RecordsViewPreferences {
  return { order: presentation.order.map(recordColumnKey), hidden: presentation.hidden.map(recordColumnKey), density: DENSITIES.find((density) => DENSITY_ROW_PX[density] === presentation.density)!, sort: reportSortToRecords(sort) };
}
export function recordsPresentationToReport(preferences: RecordsViewPreferences): ReportPresentation {
  return { order: preferences.order.map((key) => COLUMN_KEYS[key]), hidden: preferences.hidden.map((key) => COLUMN_KEYS[key]), density: DENSITY_ROW_PX[preferences.density] };
}

export function businessReportRow(report: ReportRecord): RecordRow {
  const activityId = report.linked_activity_ids[0];
  return {
    report, id: activityId ?? report.draft_id ?? report.row_id,
    kind: report.family === "sale" ? "venta" : "gasto", occurredOn: report.report_date ?? "", counterparty: report.counterparty,
    money: { amount: report.gross_amount ?? "", currency: report.currency ?? "" }, categoryId: report.category_key === "uncategorized" ? null : report.category_key,
    account: report.funding_kind === "checking" || report.funding_kind === "savings" ? { kind: "bank", name: report.funding_label } : report.funding_kind === "credit_card" ? { kind: "card", name: report.funding_label } : report.funding_kind === "cash" ? { kind: "cash", name: report.funding_label } : null,
    hasProof: report.has_document, marks: { personal: false, markedBy: null, fiscal: null },
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
  return { currencies, exclusions: { unconfirmed: 0, personal: 0, unavailable: 0 } };
}

/** Server totals cover every matching document whatever its stage. They are plain finalized money only for the ready-for-export stage or when the server reports no document to review or approve. */
export function summaryIncludesUnreviewed(reviewStages: readonly string[], overview: ReportAnswer["overview"]): boolean {
  if (reviewStages.length === 1 && reviewStages[0] === "ready_for_export") return false;
  return !(overview && overview.needs_review === 0 && overview.awaiting_approval === 0);
}

export const defaultReportRequest = (): ReportRequest => reportRequestSchema.parse({});
export const recipeFromRequest = (request: ReportRequest): ReportRecipe => {
  const recipe = { schema_version: request.schema_version, filters: request.filters, columns: request.columns, sort: request.sort };
  return reportRecipeSchema.parse(request.schema_version === 2 ? { ...recipe, presentation: request.presentation, page_size: request.page_size } : recipe);
};
export type ReportFailure = { kind: "access" | "changed" | "version" | "conflict" | "unavailable" | "uncertain" | "failed"; code: string; requestId?: string };
export function reportFailure(error: unknown, mutation = false): ReportFailure {
  const problem = error as ReportProblem | null;
  const code = typeof problem?.code === "string" ? problem.code : "unknown";
  const status = problem?.status;
  const kind = status === 401 || status === 403 || problem?.name === "ChatAccountChangedError" || problem?.message === "Browser session changed" || ["business_closed", "business_grant_not_live", "business_report_scope_changed"].includes(code) ? "access"
    : code === "business_report_changed" ? "changed"
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
  | { kind: "invalid-page"; answer: ReportAnswer; recoveryPage: number }
  | { kind: "failed"; problem: ReportFailure };
export type ViewLoad = { kind: "idle" | "loading" } | { kind: "ready"; items: SavedReportView[] } | { kind: "failed"; problem: ReportFailure };
export type ReportOperation = { kind: "idle" | "busy" } | { kind: "failed"; problem: ReportFailure } | { kind: "done" };
export type ViewOperation = ReportOperation & { command?: ReportViewCommand };
export type ReportState = Readonly<{ request: ReportRequest; load: ReportLoad; views: ViewLoad; export: ReportOperation; viewOperation: ViewOperation; anchor: string | null; missingAnchor: boolean }>;
export type ReportingTransport = {
  query: typeof queryBusinessReport; export: typeof exportBusinessReport;
  listViews: typeof listBusinessReportViews; mutateView: typeof mutateBusinessReportView;
};
const liveTransport: ReportingTransport = { query: queryBusinessReport, export: exportBusinessReport, listViews: listBusinessReportViews, mutateView: mutateBusinessReportView };

/** An instance belongs to one person, Business and selected grant. Replace it when any changes. */
export function createBusinessReportController(scope: ReportScope, initial = defaultReportRequest(), transport: ReportingTransport = liveTransport) {
  let state: ReportState = { request: reportRequestSchema.parse(initial), load: { kind: "idle" }, views: { kind: "idle" }, export: { kind: "idle" }, viewOperation: { kind: "idle" }, anchor: null, missingAnchor: false };
  const listeners = new Set<() => void>();
  let generation = 0;
  let queryVersion = 0;
  let viewsVersion = 0;
  let queryAbort: AbortController | undefined;
  const operations = new Set<AbortController>();
  const publish = (patch: Partial<ReportState>) => { state = { ...state, ...patch }; listeners.forEach((listener) => listener()); };
  const abortOperations = () => { queryAbort?.abort(); for (const operation of operations) operation.abort(); operations.clear(); };
  const revoke = (problem: ReportFailure) => {
    generation += 1;
    abortOperations();
    publish({ load: { kind: "failed", problem }, views: { kind: "failed", problem }, export: { kind: "idle" }, viewOperation: { kind: "idle" }, anchor: null });
  };
  const controller = {
    getSnapshot: () => state,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
    dispose: () => { generation += 1; abortOperations(); },
    revoke: () => revoke({ kind: "access", code: "business_report_scope_changed" }),
    async load(request = state.request) {
      const report = reportRequestSchema.parse(request);
      queryAbort?.abort();
      const abort = new AbortController();
      queryAbort = abort;
      const version = ++queryVersion;
      const currentGeneration = generation;
      publish({ request: report, load: { kind: "loading" }, export: { kind: "idle" }, missingAnchor: false });
      try {
        const answer = await transport.query(scope, report, abort.signal);
        if (abort.signal.aborted || version !== queryVersion || currentGeneration !== generation) return;
        if (answer.page !== report.page || answer.page_size !== report.page_size || answer.items.length > report.page_size) throw new Error("Invalid report page response");
        const invalid = report.page > Math.max(1, answer.page_count);
        publish({ load: invalid ? { kind: "invalid-page", answer, recoveryPage: Math.max(1, answer.page_count) } : { kind: "ready", answer }, missingAnchor: state.anchor !== null && !answer.items.some((row) => row.row_id === state.anchor) });
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
    refresh: () => controller.load(),
    recoverPage: () => state.load.kind === "invalid-page" ? controller.setPage(state.load.recoveryPage) : Promise.resolve(),
    rememberAnchor: (rowId: string | null) => publish({ anchor: rowId, missingAnchor: false }),
    async export(): Promise<Blob | null> {
      if (state.load.kind !== "ready" || state.export.kind === "busy" || state.export.kind === "failed" && state.export.problem.kind === "changed") return null;
      const { request, load } = state;
      const currentGeneration = generation;
      const currentQuery = queryVersion;
      const abort = new AbortController();
      operations.add(abort);
      publish({ export: { kind: "busy" } });
      try {
        const blob = await transport.export(scope, request, load.answer.fingerprint, abort.signal);
        if (abort.signal.aborted || currentGeneration !== generation || currentQuery !== queryVersion) return null;
        publish({ export: { kind: "done" } });
        return blob;
      } catch (error) {
        if (abort.signal.aborted || currentGeneration !== generation || currentQuery !== queryVersion) return null;
        const problem = reportFailure(error);
        if (problem.kind === "access") revoke(problem);
        else publish({ export: { kind: "failed", problem } });
        return null;
      } finally { operations.delete(abort); }
    },
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
    async mutateView(command: ReportViewCommand) {
      if (state.viewOperation.kind === "busy") return;
      if (state.viewOperation.kind === "failed" && state.viewOperation.problem.kind === "uncertain" && state.viewOperation.command?.key !== command.key) return;
      // Keep the exact command and key after an uncertain response. Retrying must not create a second write.
      const snapshot = structuredClone(command);
      const currentGeneration = generation;
      const abort = new AbortController();
      operations.add(abort);
      publish({ viewOperation: { kind: "busy", command: snapshot } });
      try {
        const saved = await transport.mutateView(scope, snapshot, abort.signal);
        if (abort.signal.aborted || currentGeneration !== generation) return;
        const existing = state.views.kind === "ready" ? state.views.items : [];
        const items = snapshot.kind === "delete" ? existing.filter((view) => view.id !== snapshot.id) : saved ? [...existing.filter((view) => view.id !== saved.id), saved] : existing;
        publish({ views: { kind: "ready", items }, viewOperation: { kind: "done" } });
      } catch (error) {
        if (abort.signal.aborted || currentGeneration !== generation) return;
        const problem = reportFailure(error, true);
        if (problem.kind === "access") revoke(problem);
        else publish({ viewOperation: { kind: "failed", problem, command: snapshot } });
      } finally { operations.delete(abort); }
    },
    retryView: () => state.viewOperation.kind === "failed" && state.viewOperation.problem.kind === "uncertain" && state.viewOperation.command ? controller.mutateView(state.viewOperation.command) : Promise.resolve(),
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
export function restoreReportLocation(params: URLSearchParams): { request: ReportRequest; anchor: string | null; invalid: boolean } {
  try {
    const encoded = params.get("report");
    return { request: encoded ? reportRequestSchema.parse(JSON.parse(encoded)) : defaultReportRequest(), anchor: params.get("report_row"), invalid: false };
  } catch { return { request: defaultReportRequest(), anchor: null, invalid: true }; }
}
