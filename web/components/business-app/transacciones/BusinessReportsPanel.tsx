"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { SlidersHorizontal } from "lucide-react";
import { getMe } from "@/lib/argus-api";
import { getChosenGrant } from "@/lib/business-grant";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "@/lib/browser-auth-generation";
import { businessReportRow, recipeFromRequest, reportSummary, recordsPresentationToReport, recordsSortToReport, reportLocation, reportPresentationToRecords, restoreReportLocation, type ReportFailure, type ReportingTransport } from "@/lib/business-reporting-wire";
import { reportRequestSchema, type ReportAnswer, type ReportFilters, type ReportPeriod, type ReportRequest, type ReportScope } from "@/lib/business-reports-api";
import { PullToRefresh } from "@/components/ui/PullToRefresh";
import { useBusiness } from "../BusinessWorkspace";
import BusinessAddMenu from "../BusinessAddMenu";
import { saveBlobDownload } from "../ExportRecordsPanel";
import { periodRange, todayIso, type Period } from "../business-format";
import { cardClass, quietButtonClass } from "../business-ui";
import { EmptyState } from "../foundation/EmptyState";
import { defaultRecordsPreferences } from "./records-view-preferences";
import { emptyPreviewFilters, type PreviewFilters } from "./records-filter-preview-model";
import { RecordsToolbar, type RecordsFilter } from "./RecordsToolbar";
import RecordsSettingsPreview from "./RecordsSettingsPreview";
import RecordsPagePreview from "./RecordsPagePreview";
import RecordsLoadingPreview from "./RecordsLoadingPreview";
import RecordsOverviewPreview from "./RecordsOverviewPreview";
import { RecordsRefreshButton } from "./RecordsRefreshButton";
import { RecordsSummaryCards } from "./RecordsResultsSummary";
import { RecordsAnnotationsPreview } from "./RecordsAnnotationsPreview";
import { RecordEvidenceContext, RecordGlanceContext } from "./RecordGlanceContext";
import { recordRowKey } from "./records-row-preview";
import type { RecordRow } from "./transacciones-model";
import { useBusinessReport } from "./useBusinessReport";
import { useTransaccionesWords } from "./transacciones-words";

const STAGES = { review: "needs_review", approval: "awaiting_approval", export: "ready_for_export" } as const;
const REPORTING = "business.transactions.reporting.";
export const reportPeriodFromUi = (period: Period): ReportPeriod => period.key === "all" ? { kind: "all" } : period.key === "this_month" || period.key === "last_month" ? { kind: period.key } : { kind: "custom", from_date: period.from, to_date: period.to ?? todayIso() };
function periodForUi(period: ReportPeriod, answer?: ReportAnswer): Period {
  if (period.kind === "all") return { key: "all", from: "", to: null };
  if (period.kind === "custom") return { key: "custom", from: period.from_date, to: period.to_date };
  if (period.kind === "this_year") return { key: "custom", from: answer?.resolved_period.from_date ?? `${new Date().getFullYear()}-01-01`, to: answer?.resolved_period.to_date ?? `${new Date().getFullYear()}-12-31` };
  const fallback = periodRange(period.kind);
  return { key: period.kind, from: answer?.resolved_period.from_date ?? fallback.from, to: answer?.resolved_period.to_date ?? fallback.to };
}
export function reportFiltersForUi(filters: ReportFilters): PreviewFilters {
  const result = emptyPreviewFilters();
  result.review = (Object.keys(STAGES) as PreviewFilters["review"]).filter((key) => filters.review_stages.includes(STAGES[key]));
  result.attachment = filters.has_document === null ? "any" : filters.has_document ? "with" : "without";
  const currency = filters.currencies.length === 1 ? filters.currencies[0] : "";
  result.currencies = filters.currencies;
  result.recordFamilies = filters.record_families;
  result.amount = { currency, min: filters.amount_min ?? "", max: filters.amount_max ?? "" };
  result.counterparty = filters.counterparties; result.category = filters.categories; result.account = filters.funding_sources;
  result.document = filters.document_kinds; result.fiscal = filters.fiscal_classifications.map((value) => value.toLowerCase());
  return result;
}
export function reportFiltersFromUi(current: ReportFilters, filters: PreviewFilters, kind: RecordsFilter["kind"]): ReportFilters {
  return { ...current, record_families: filters.recordFamilies ?? (kind === "all" ? [] : [kind === "venta" ? "sale" : "purchase"]), review_stages: filters.review.map((key) => STAGES[key]), has_document: filters.attachment === "any" ? null : filters.attachment === "with", currencies: filters.currencies ?? (filters.amount.currency ? [filters.amount.currency] : []), amount_min: filters.amount.min || null, amount_max: filters.amount.max || null, counterparties: filters.counterparty, categories: filters.category, funding_sources: filters.account, document_kinds: filters.document as ReportFilters["document_kinds"], fiscal_classifications: filters.fiscal.map((value) => /^[be]\d\d$/i.test(value) ? value.toUpperCase() : value) };
}

export default function BusinessReportsPanel() {
  const { chosen, period } = useBusiness();
  const [person, setPerson] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const { t } = useTransaccionesWords();
  useEffect(() => {
    let active = true;
    const generation = browserAuthGeneration();
    void getMe().then((me) => { requireBrowserAuthGeneration(generation); if (active) { setPerson(me.user.id); setFailed(false); } }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [attempt]);
  if (failed) return <div className={cardClass}><EmptyState kind="error" compact title={t(`${REPORTING}access_unavailable`)} action={{ label: t("common.retry"), run: () => { setFailed(false); setAttempt((value) => value + 1); } }} /></div>;
  if (!person || !chosen) return <RecordsLoadingPreview preferences={defaultRecordsPreferences()} density="normal" />;
  const scope = { userId: person, businessId: chosen.space_id, grantId: getChosenGrant() };
  return <ConnectedBusinessReports key={`${person}:${chosen.space_id}:${scope.grantId}`} scope={scope} period={period} />;
}

export function ConnectedBusinessReports({ scope, period, transport, initial }: { scope: ReportScope; period: Period; transport?: ReportingTransport; initial?: ReportRequest }) {
  const { t } = useTransaccionesWords();
  const { panel, openPanel, actions, revision } = useBusiness();
  const { isBelowTablet: phone, isBelowDesktop } = useResponsiveLayout();
  const scopeKey = `${scope.userId}:${scope.businessId}`;
  const [restored] = useState(() => {
    const params = typeof window === "undefined" ? new URLSearchParams() : new URLSearchParams(window.location.search);
    const other = params.has("report_scope") && params.get("report_scope") !== scopeKey;
    const saved = restoreReportLocation(other ? new URLSearchParams() : params);
    return { ...saved, invalid: saved.invalid || other, request: initial ?? (params.has("report") && !other ? saved.request : reportRequestSchema.parse({ filters: { period: reportPeriodFromUi(period) } })) };
  });
  const { controller, state } = useBusinessReport(scope, restored.request, transport);
  const answer = state.load.kind === "ready" || state.load.kind === "invalid-page" ? state.load.answer : undefined;
  const v2 = state.request.schema_version === 2;
  const preferences = useMemo(() => state.request.schema_version === 2 ? reportPresentationToRecords(state.request.presentation, state.request.sort) : defaultRecordsPreferences(), [state.request]);
  const periodKey = JSON.stringify(state.request.filters.period);
  const [scopeData, setScopeData] = useState<{ periodKey: string; answer: ReportAnswer } | null>(null);
  useEffect(() => { if (answer) setScopeData({ periodKey, answer }); }, [answer, periodKey]);
  const accessDenied = state.load.kind === "failed" && state.load.problem.kind === "access";
  const overview = !accessDenied ? answer?.overview ?? (scopeData?.periodKey === periodKey ? scopeData.answer.overview : undefined) : undefined;
  const catalogues = !accessDenied ? answer ?? scopeData?.answer : undefined;
  const rows = useMemo(() => answer?.items.map(businessReportRow) ?? [], [answer]);
  const rowNodes = useRef(new Map<string, HTMLElement>());
  const focused = useRef<string | null>(null);
  const screen = useRef<HTMLElement>(null);
  const previousRevision = useRef(revision);
  const [urlInvalid, setUrlInvalid] = useState(restored.invalid);
  const filter: RecordsFilter = { query: state.request.filters.q, kind: state.request.filters.record_families.length === 1 ? state.request.filters.record_families[0] === "sale" ? "venta" : "gasto" : "all" };
  const filters = reportFiltersForUi(state.request.filters);
  const selectedPeriod = periodForUi(state.request.filters.period, answer);
  const updateUrl = (request: ReportRequest, anchor = state.anchor, push = false) => {
    const url = new URL(window.location.href);
    const encoded = new URLSearchParams(reportLocation(request, anchor));
    encoded.forEach((value, key) => url.searchParams.set(key, value));
    if (!anchor) url.searchParams.delete("report_row");
    url.searchParams.set("report_scope", scopeKey);
    if (url.href !== window.location.href) window.history[push ? "pushState" : "replaceState"](null, "", `${url.pathname}${url.search}`);
  };
  useEffect(() => { updateUrl(state.request); }, [state.request, state.anchor]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const restore = () => { const url = new URL(window.location.href); if (url.searchParams.get("report_scope") !== scopeKey) return; const next = restoreReportLocation(url.searchParams); setUrlInvalid(next.invalid); controller.rememberAnchor(next.anchor); void controller.load(next.request); };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [controller, scopeKey]);
  useEffect(() => { controller.rememberAnchor(restored.anchor); }, [controller, restored.anchor]);
  useEffect(() => {
    if (previousRevision.current !== revision) { previousRevision.current = revision; void controller.refresh(); }
  }, [revision, controller]);
  useEffect(() => {
    if (state.load.kind === "ready" && state.request.schema_version === 1 && state.load.answer.overview && state.load.answer.effective_sort) {
      void controller.load(reportRequestSchema.parse({ ...state.request, schema_version: 2 }));
    }
  }, [controller, state.load, state.request]);
  useEffect(() => {
    if (panel.kind !== "transactions" || state.load.kind !== "ready" || !state.anchor || focused.current === state.anchor) return;
    focused.current = state.anchor;
    (rowNodes.current.get(state.anchor) ?? screen.current)?.focus();
  }, [panel.kind, state.load, state.anchor]);
  const load = (request: ReportRequest, push = true) => { updateUrl(request, state.anchor, push); void controller.load(request); };
  const recipe = (patch: Partial<ReportRequest>, push = true) => load(reportRequestSchema.parse({ ...state.request, ...patch, page: 1 }), push);
  const open = (row: RecordRow) => { if (!row.opens) return; const id = recordRowKey(row); focused.current = null; controller.rememberAnchor(id); updateUrl(state.request, id); openPanel(row.opens); };
  const rowRef = (id: string, node: HTMLElement | null) => { if (node) rowNodes.current.set(id, node); else rowNodes.current.delete(id); };
  const exportReport = async () => { const blob = await controller.export(); if (blob) saveBlobDownload(blob, "business-records.zip"); };
  const views = state.views.kind === "ready" ? state.views.items : [];
  const viewProblem = state.viewOperation.kind === "failed" ? state.viewOperation.problem : state.views.kind === "failed" ? state.views.problem : null;
  const uncertain = state.viewOperation.kind === "failed" && state.viewOperation.problem.kind === "uncertain";
  const writeView = async (name: string, id?: string) => {
    const view = views.find((view) => view.id === id);
    if (id && !view) return false;
    await controller.mutateView(id && view ? { kind: "update", id, key: crypto.randomUUID(), body: { name, recipe: view.recipe, expected_version: view.version } } : { kind: "create", key: crypto.randomUUID(), body: { name, recipe: recipeFromRequest(state.request) } });
    return controller.getSnapshot().viewOperation.kind === "done";
  };
  const problem = (failure: ReportFailure, retry: () => void): ReactNode => <p role="alert" className="mb-3 text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{t(`${REPORTING}${failure.kind === "access" ? "access_unavailable" : failure.kind === "changed" ? "report_changed" : failure.kind === "version" ? "view_changed" : failure.kind === "uncertain" ? "uncertain_view" : "unavailable"}`)}{failure.kind !== "access" && failure.kind !== "conflict" ? <button type="button" className={quietButtonClass} onClick={retry}>{t(`${REPORTING}${failure.kind === "uncertain" ? "retry" : "refresh"}`)}</button> : null}{failure.requestId ? <ReferenceCode reference={failure.requestId} /> : null}</p>;
  const recheckAnnotationAccess = () => {
    setScopeData(null); controller.revoke();
    void controller.refresh().then(() => { if (controller.getSnapshot().load.kind === "ready") void controller.listViews(); });
  };
  const create = actions.create.find((action) => action.id === "upload_receipt");
  const add = <BusinessAddMenu placement="header" onExport={() => void exportReport()} exportEnabled={state.load.kind === "ready" && state.export.kind !== "busy" && !(state.export.kind === "failed" && state.export.problem.kind === "changed")} />;
  return <RecordsAnnotationsPreview connected={{ scope, rows, refresh: controller.refresh, revoke: recheckAnnotationAccess }}><PullToRefresh onRefresh={async () => { await controller.refresh(); return controller.getSnapshot().load.kind === "ready" ? "updated" : "failed"; }}>
    <section ref={screen} tabIndex={-1} data-testid="transacciones" data-report-connected data-report-schema={state.request.schema_version} className="pb-6 outline-none">
      {phone || panel.kind !== "transactions" ? <div className="mb-5 flex flex-wrap items-end justify-between gap-3"><h2 className="font-display text-[26px] font-medium tracking-tight text-black dark:text-white">{t("business.transactions.title")}</h2>{add}</div> : null}
      <RecordsOverviewPreview counts={overview ? { review: overview.needs_review, approval: overview.awaiting_approval, export: overview.ready_for_export } : { review: null, approval: null, export: null }} selected={filters.review} loading={state.load.kind === "loading"} onChoose={(key) => recipe({ filters: { ...state.request.filters, review_stages: filters.review.includes(key) ? [] : [STAGES[key]] } })} />
      <RecordsToolbar filter={filter} onChange={(next) => recipe({ filters: { ...state.request.filters, q: next.query, record_families: next.kind === filter.kind ? state.request.filters.record_families : next.kind === "all" ? [] : [next.kind === "venta" ? "sale" : "purchase"] } }, false)} period={selectedPeriod} setPeriod={(next) => recipe({ filters: { ...state.request.filters, period: reportPeriodFromUi(typeof next === "string" ? periodRange(next) : next) } })} preferences={preferences} appliedPeriod={selectedPeriod} onPeriodChange={(next) => recipe({ filters: { ...state.request.filters, period: reportPeriodFromUi(next) } })} appliedFilters={filters} onFiltersChange={(next) => recipe({ filters: reportFiltersFromUi(state.request.filters, next, filter.kind) })} options={<>{!phone ? <RecordsRefreshButton busy={state.load.kind === "loading"} onRefresh={() => void controller.refresh()} /> : null}{!phone ? add : null}{v2 ? <RecordsSettingsPreview value={preferences} onChange={(next) => controller.setPresentation(recordsPresentationToReport(next))} /> : !isBelowDesktop ? <button type="button" className={quietButtonClass} disabled title={t(`${REPORTING}pending_contract`)} aria-label={t("business.transactions.density.options")}><SlidersHorizontal size={18} /></button> : null}</>} connected={{ reportPeriod: state.request.filters.period, onPreset: (kind) => recipe({ filters: { ...state.request.filters, period: { kind } } }), catalogues: catalogues ?? { counterparties: [], categories: [], funding_sources: [] }, applyFilters: (next, kind) => recipe({ filters: reportFiltersFromUi(state.request.filters, next, kind) }), views: { items: views, select: (id) => { const view = views.find((view) => view.id === id); if (view) recipe({ ...view.recipe, page_size: view.recipe.schema_version === 2 ? view.recipe.page_size : state.request.page_size }); }, save: (name) => writeView(name), update: (id, name) => writeView(name, id), remove: (id) => { const view = views.find((view) => view.id === id); if (view) void controller.mutateView({ kind: "delete", id, key: crypto.randomUUID(), body: { expected_version: view.version } }); }, busy: state.viewOperation.kind === "busy" || uncertain, notice: viewProblem ? problem(viewProblem, () => { if (uncertain) void controller.retryView(); else void controller.listViews(); }) : !v2 ? <p>{t(`${REPORTING}pending_contract`)}</p> : null } }} />
      {filter.kind !== "all" ? <><RecordsSummaryCards kind={filter.kind} summary={reportSummary(answer, filter.kind)} /><p className="mb-3 text-[13px] text-[#56635e] dark:text-white/65">{t(`${REPORTING}financial_cards_pending`)}</p></> : null}
      {state.missingAnchor && state.load.kind === "ready" ? <p role="status" className="mb-3 text-[13px] text-[#56635e] dark:text-white/65">{t("business.search.record_unavailable")}<button type="button" className={quietButtonClass} onClick={() => controller.rememberAnchor(null)}>{t("common.done")}</button></p> : null}
      {urlInvalid ? <p role="status">{t(`${REPORTING}invalid_page`)}<button type="button" className={quietButtonClass} onClick={() => { setUrlInvalid(false); void controller.setPage(1); }}>{t(`${REPORTING}refresh`)}</button></p> : null}
      {state.export.kind !== "idle" ? <p role="status" className="mb-3 text-[13px] text-[#56635e] dark:text-white/65">{t(`${REPORTING}records_only`)}</p> : null}
      {state.export.kind === "failed" ? problem(state.export.problem, () => { void controller.refresh(); }) : null}
      {state.load.kind === "failed" ? <div className={cardClass}>{problem(state.load.problem, () => { void controller.refresh(); })}</div> : state.load.kind === "invalid-page" ? <div className={cardClass}><EmptyState kind="filtered" compact title={t(`${REPORTING}invalid_page`)} action={{ label: t(`${REPORTING}refresh`), run: () => { void controller.recoverPage(); } }} /></div> : state.load.kind !== "ready" ? <RecordsLoadingPreview preferences={preferences} density={preferences.density} /> : <RecordGlanceContext.Provider value={open}><RecordEvidenceContext.Provider value={open}>
        <RecordsPagePreview records={rows} preferences={preferences} onSortChange={() => undefined} density={preferences.density} resetKey={scopeKey} rowRef={rowRef} emptyContent={<div className={cardClass}><EmptyState kind="filtered" compact title={t("business.transactions.layout.no_results")} body={!state.request.filters.q && !state.request.filters.record_families.length && create ? t("business.transactions.records.empty_body") : undefined} action={{ label: t("business.transactions.layout.clear"), run: () => recipe({ filters: { ...reportRequestSchema.parse({}).filters, period: state.request.filters.period } }) }} /></div>} connected={{ answer: state.load.answer, onPage: (page) => load({ ...state.request, page }), onPageSize: (page_size) => recipe({ page_size }), onSort: v2 ? (sort) => recipe({ sort: recordsSortToReport(sort) }) : undefined }} />
      </RecordEvidenceContext.Provider></RecordGlanceContext.Provider>}
    </section>
  </PullToRefresh></RecordsAnnotationsPreview>;
}
