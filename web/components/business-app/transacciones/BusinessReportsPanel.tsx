"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { SlidersHorizontal } from "lucide-react";
import { getMe } from "@/lib/argus-api";
import { getChosenGrant } from "@/lib/business-grant";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "@/lib/browser-auth-generation";
import { isProgrammaticPop } from "@/lib/overlay-history";
import { businessReportRow, liveReportingTransport, recipeFromRequest, recordsPresentationToReport, recordsSortToReport, reportFailure, reportPresentationToRecords, restoreReportLocation, writeReportLocation, type ReportFailure, type ReportingTransport, type ViewWriteResult } from "@/lib/business-reporting-wire";
import { queryBusinessReport, recordsCurrencySchema, reportFiltersSchema, reportPeriodSchema, reportRequestSchema, type RecordsCurrency, type ReportAnswer, type ReportFilters, type ReportPeriod, type ReportRecipe, type ReportRequest, type ReportScope, type ReportViewCommand } from "@/lib/business-reports-api";
import { PullToRefresh } from "@/components/ui/PullToRefresh";
import { useBusiness } from "../BusinessWorkspace";
import BusinessAddMenu from "../BusinessAddMenu";
import { RecordsExportButton } from "./RecordsExportButton";
import RecordsExportPanel from "./RecordsExportPanel";
import { clearRecordsExportRequest, useRecordsExportRequested } from "./records-export-request";
import { useRecordsPeriodLabel } from "./RecordsDatePreview";
import { periodRange, todayIso, type Period } from "../business-format";
import { cardClass, quietButtonClass } from "../business-ui";
import { EmptyState } from "../foundation/EmptyState";
import GuideCard from "../foundation/GuideCard";
import FullscreenLoading from "@/components/FullscreenLoading";
import { activeFilterGroups, emptyPreviewFilters, REVIEW_FILTERS, STAGE_OF, type PreviewFilters } from "./records-filter-preview-model";
import { showToast } from "../foundation/toasts";
import { RecordsToolbar, type RecordsFilter } from "./RecordsToolbar";
import { sameRecipe, type RecordsViews } from "./RecordsViewsPreview";
import RecordsTypeTabs from "./RecordsTypeTabs";
import RecordsSettingsPreview from "./RecordsSettingsPreview";
import RecordsPagePreview from "./RecordsPagePreview";
import RecordsLoadingPreview from "./RecordsLoadingPreview";
import RecordsOverviewPreview from "./RecordsOverviewPreview";
import { RecordsRefreshButton } from "./RecordsRefreshButton";
import { RecordsAnnotationsPreview } from "./RecordsAnnotationsPreview";
import { RecordEvidenceContext, RecordGlanceContext } from "./RecordGlanceContext";
import { focusKey, focusRequest } from "./records-focus";
import { recordRowKey } from "./records-row-preview";
import type { RecordRow } from "./transacciones-model";
import { useFiscalStageToggle } from "./useFiscalStageToggle";
import { useBusinessReport } from "./useBusinessReport";
import { useTransaccionesWords } from "./transacciones-words";

const REPORTING = "business.transactions.reporting.";
const EMPTY_COPY = "business.transactions.records.empty_placeholder";
const GUIDE = "business.guide_cards.registros_intro.";
type EmptyCause = "selection" | "filters" | "search";
type CreateViewCommand = Extract<ReportViewCommand, { kind: "create" }>;
type EmptyProbe =
  | { answer: ReportAnswer; result: EmptyCause | ReportFailure }
  | { request: ReportRequest; accessFailure: ReportFailure };
export const reportPeriodFromUi = (period: Period): ReportPeriod => period.key === "all" ? { kind: "all" } : period.key === "this_month" || period.key === "last_month" || period.key === "this_year" ? { kind: period.key } : { kind: "custom", from_date: period.from, to_date: period.to ?? todayIso() };
function periodForUi(period: ReportPeriod, answer?: ReportAnswer): Period {
  if (period.kind === "all") return { key: "all", from: "", to: null };
  if (period.kind === "custom") return { key: "custom", from: period.from_date, to: period.to_date };
  if (period.kind === "latest_month") return { key: "custom", from: answer?.resolved_period.from_date ?? "", to: answer?.resolved_period.to_date ?? null };
  const fallback = periodRange(period.kind);
  return { key: period.kind, from: answer?.resolved_period.from_date ?? fallback.from, to: answer?.resolved_period.to_date ?? fallback.to };
}
export function reportFiltersForUi(filters: ReportFilters): PreviewFilters {
  const currency = recordsCurrencySchema.parse(filters.currencies[0]);
  const result = emptyPreviewFilters(currency);
  result.fiscal_data = filters.fiscal_data;
  result.review = REVIEW_FILTERS.filter((key) => filters.review_stages.includes(STAGE_OF[key]));
  result.attachment = filters.has_document === null ? "any" : filters.has_document ? "with" : "without";
  result.amount = { currency, min: filters.amount_min ?? "", max: filters.amount_max ?? "" };
  result.counterparty = filters.counterparties; result.expense_type = filters.expense_types; result.account = filters.funding_sources;
  result.document = filters.document_kinds; result.fiscal = filters.fiscal_classifications.map((value) => value.toLowerCase());
  return result;
}
export function reportFiltersFromUi(current: ReportFilters, filters: PreviewFilters, kind: RecordsFilter["kind"]): ReportFilters {
  return { ...current, record_families: [kind === "venta" ? "sale" : "purchase"], fiscal_data: filters.fiscal_data, review_stages: filters.fiscal_data ? [] : filters.review.map((key) => STAGE_OF[key]), has_document: filters.attachment === "any" ? null : filters.attachment === "with", currencies: [filters.amount.currency], amount_min: filters.amount.min || null, amount_max: filters.amount.max || null, counterparties: filters.counterparty, categories: [], expense_types: kind === "venta" ? [] : filters.expense_type, funding_sources: filters.account, document_kinds: filters.document as ReportFilters["document_kinds"], fiscal_classifications: filters.fiscal.map((value) => /^[be]\d\d$/i.test(value) ? value.toUpperCase() : value) };
}

export function RecordsWorkspaceUnavailable() {
  const { records, reload } = useBusiness();
  const { t } = useTransaccionesWords();
  return <div className={cardClass}><EmptyState kind="error" compact title={t(`${REPORTING}${records.refused ? "access_unavailable" : "unavailable"}`)} action={records.refused ? undefined : { label: t("common.retry"), run: reload }} />{records.failureReference ? <ReferenceCode reference={records.failureReference} /> : null}</div>;
}

export default function BusinessReportsPanel() {
  const { chosen, records, panel } = useBusiness();
  const focus = panel.kind === "transactions" ? panel.focus : undefined;
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
  const defaultCurrency = recordsCurrencySchema.safeParse(records.workspace?.records_default_currency);
  if ((!defaultCurrency.success || records.workspaceGrant !== getChosenGrant()) && (records.error || records.workspaceGrant === getChosenGrant() && records.workspace)) return <RecordsWorkspaceUnavailable />;
  if (!person || !chosen || records.workspaceGrant !== getChosenGrant() || !defaultCurrency.success) return <FullscreenLoading />;
  const scope = { userId: person, businessId: chosen.space_id, grantId: getChosenGrant() };
  // A focus another screen opened starts Registros on exactly that list.
  return <ConnectedBusinessReports key={`${person}:${chosen.space_id}:${scope.grantId}:${focusKey(focus)}`} scope={scope} defaultCurrency={defaultCurrency.data} initial={focus ? focusRequest(focus) : undefined} />;
}

export function ConnectedBusinessReports({ scope, transport, initial, defaultCurrency }: { defaultCurrency: RecordsCurrency; scope: ReportScope; transport?: ReportingTransport; initial?: ReportRequest }) {
  const { t } = useTransaccionesWords();
  const { panel, openPanel, revision } = useBusiness();
  const { isBelowTablet: phone, isBelowDesktop } = useResponsiveLayout();
  const { userId, businessId, grantId } = scope;
  const scopeKey = `${userId}:${businessId}`;
  const singleCurrency = useCallback((request: ReportRequest): ReportRequest => {
    if (request.filters.currencies.length === 1 && recordsCurrencySchema.safeParse(request.filters.currencies[0]).success) return request;
    return { ...request, filters: { ...request.filters, currencies: [defaultCurrency], amount_min: null, amount_max: null } };
  }, [defaultCurrency]);
  const [restored] = useState(() => {
    const params = typeof window === "undefined" ? new URLSearchParams() : new URLSearchParams(window.location.search);
    const other = params.has("report_scope") && params.get("report_scope") !== scopeKey;
    const saved = restoreReportLocation(other ? new URLSearchParams() : params);
    return { ...saved, request: singleCurrency(initial ?? (params.has("report") && !other ? saved.request : reportRequestSchema.parse({ filters: { period: { kind: "latest_month" } } }))) };
  });
  const { controller, state } = useBusinessReport(scope, restored.request, transport);
  const answer = state.load.kind === "ready" ? state.load.answer : undefined;
  const currentFormat = state.request.schema_version === 2;
  const periodKey = JSON.stringify([state.request.filters.period, state.request.filters.record_families]);
  const [scopeData, setScopeData] = useState<{ periodKey: string; answer: ReportAnswer } | null>(null);
  useEffect(() => { if (answer) setScopeData({ periodKey, answer }); }, [answer, periodKey]);
  const presentation = state.request.schema_version === 2 && state.request.presentation ? state.request.presentation : answer?.presentation ?? scopeData?.answer.presentation;
  // Until the new tab's answer lands, the last answer's columns keep the table drawn.
  const columns = answer?.columns ?? scopeData?.answer.columns;
  const preferences = useMemo(() => presentation && columns ? reportPresentationToRecords(presentation, state.request.sort, columns) : undefined, [presentation, columns, state.request.sort]);
  const accessDenied = state.load.kind === "failed" && state.load.problem.kind === "access";
  const periodAnswer = answer ?? (scopeData?.periodKey === periodKey ? scopeData.answer : undefined);
  const overview = !accessDenied ? answer?.overview : undefined;
  const catalogues = !accessDenied ? periodAnswer : undefined;
  const rows = useMemo(() => answer?.items.map(businessReportRow) ?? [], [answer]);
  const rowNodes = useRef(new Map<string, HTMLElement>());
  const focused = useRef<string | null>(null);
  const screen = useRef<HTMLElement>(null);
  const previousRevision = useRef(revision);
  const filter: RecordsFilter = { query: state.request.filters.q, kind: state.request.filters.record_families[0] === "sale" ? "venta" : "gasto" };
  const filters = reportFiltersForUi(state.request.filters);
  const selectedPeriod = periodForUi(state.request.filters.period, periodAnswer);
  const updateUrl = (request: ReportRequest, anchor = state.anchor, push = false) => writeReportLocation(request, anchor, scopeKey, push);
  const load = (request: ReportRequest, push = true) => { updateUrl(request, state.anchor, push); void controller.load(request); };
  const { toggle: toggleFiscal, clear: clearFiscal } = useFiscalStageToggle(filters, (selection) => load(reportRequestSchema.parse({ ...state.request, filters: { ...state.request.filters, fiscal_data: selection.fiscal_data, review_stages: selection.review.map((key) => STAGE_OF[key]) }, page: 1 })));
  useEffect(() => { updateUrl(state.request); }, [state.request, state.anchor]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const restore = (event: PopStateEvent) => { if (isProgrammaticPop(event)) return; const url = new URL(window.location.href); if (url.searchParams.get("report_scope") !== scopeKey) return; const next = restoreReportLocation(url.searchParams); clearFiscal(); controller.rememberAnchor(next.anchor); void controller.load(singleCurrency(next.request)); };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [controller, scopeKey, clearFiscal, singleCurrency]);
  useEffect(() => { controller.rememberAnchor(restored.anchor); }, [controller, restored.anchor]);
  useEffect(() => {
    if (previousRevision.current !== revision) { previousRevision.current = revision; void controller.refresh(); }
  }, [revision, controller]);
  useEffect(() => {
    if (state.load.kind === "ready" && state.request.schema_version === 1 && state.load.answer.overview && state.load.answer.effective_sort) {
      void controller.load(reportRequestSchema.parse({ ...state.request, schema_version: 2 }));
    }
  }, [controller, state.load, state.request]);
  // A record that left the current view says so once, in a toast; nothing above the table moves.
  useEffect(() => {
    if (state.load.kind !== "ready" || !state.missingAnchor) return;
    showToast({ kind: "info", text: t("business.search.record_unavailable") });
    controller.rememberAnchor(null);
  }, [controller, state.load.kind, state.missingAnchor, t]);
  useEffect(() => {
    if (panel.kind !== "transactions" || state.load.kind !== "ready" || !state.anchor || focused.current === state.anchor) return;
    focused.current = state.anchor;
    (rowNodes.current.get(state.anchor) ?? screen.current)?.focus();
  }, [panel.kind, state.load, state.anchor]);
  const recipe = (patch: Partial<ReportRequest>, push = true) => {
    if (patch.filters && (patch.filters.fiscal_data !== state.request.filters.fiscal_data || JSON.stringify(patch.filters.review_stages) !== JSON.stringify(state.request.filters.review_stages))) clearFiscal();
    load(singleCurrency(reportRequestSchema.parse({ ...state.request, ...patch, page: 1 })), push);
  };
  const open = (row: RecordRow) => { if (!row.opens) return; const id = recordRowKey(row); focused.current = null; controller.rememberAnchor(id); updateUrl(state.request, id); openPanel(row.opens); };
  const rowRef = (id: string, node: HTMLElement | null) => { if (node) rowNodes.current.set(id, node); else rowNodes.current.delete(id); };
  const periodLabel = useRecordsPeriodLabel();
  // The export works on the table's request as it stood when Exportar was pressed.
  const [exporting, setExporting] = useState<{ request: ReportRequest; scope: ReportScope; periodLabel: string; filterCount: number } | null>(null);
  const exportRequested = useRecordsExportRequested();
  // The DGII notice counts by tab and period only; Revisar clears the rest so the list shows exactly those records.
  const reviewDgiiPending = (currency: string) => recipe({ filters: reportFiltersSchema.parse({ period: state.request.filters.period, record_families: state.request.filters.record_families, currencies: [currency], fiscal_data: "missing" }) });
  const openExport = () => { if (presentation) setExporting({ scope: { userId, businessId, grantId }, request: reportRequestSchema.parse({ ...state.request, schema_version: 2, presentation }), periodLabel: periodLabel(selectedPeriod, state.request.filters.period), filterCount: activeFilterGroups(filters).length + (filter.query.trim() ? 1 : 0) }); };
  const views = state.views.kind === "ready" ? state.views.items : [];
  const viewProblem = state.viewOperation.kind === "failed" ? state.viewOperation.problem : state.views.kind === "failed" ? state.views.problem : null;
  const uncertain = state.viewOperation.kind === "failed" && state.viewOperation.problem.kind === "uncertain";
  const problem = (failure: ReportFailure, retry: () => void): ReactNode => <p role="alert" className="mb-3 text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{t(`${REPORTING}${failure.kind === "access" ? "access_unavailable" : failure.kind === "version" ? "view_changed" : failure.kind === "uncertain" ? "uncertain_view" : "unavailable"}`)}{failure.kind !== "access" && failure.kind !== "conflict" ? <button type="button" className={quietButtonClass} onClick={retry}>{t(`${REPORTING}${failure.kind === "uncertain" ? "retry" : "refresh"}`)}</button> : null}{failure.requestId ? <ReferenceCode reference={failure.requestId} /> : null}</p>;
  const [appliedViewId, setAppliedViewId] = useState<string | null>(null);
  // A write that resolves late applies its view only if no view was chosen since it started.
  const viewChoices = useRef(0);
  const applyView = (id: string | null) => { viewChoices.current += 1; setAppliedViewId(id); };
  const appliedView = views.find((view) => view.id === appliedViewId);
  const shownRecipe = preferences ? recipeFromRequest(state.request, recordsPresentationToReport(preferences)) : null;
  // A write the server did not confirm finishes when Reintentar gets its answer, the way a first answer would have.
  const outcome = async (write: Promise<ViewWriteResult>) => { const result = await write; return result.kind === "failed" && result.confirmed ? result.confirmed : result; };
  const updateView = async (id: string, name: string | undefined, viewRecipe: ReportRecipe | null) => {
    const view = views.find((view) => view.id === id);
    if (!view || !viewRecipe) return false;
    const result = await outcome(controller.mutateView({ kind: "update", id, key: crypto.randomUUID(), body: { name: name ?? view.name, recipe: viewRecipe, expected_version: view.version } }));
    return result.kind === "done";
  };
  // The created view is the one the server returned. It is applied only if no view was chosen since the write started, also when Reintentar confirms it later.
  const createView = async (command: CreateViewCommand, applyIfNoChoiceSince: number | null): Promise<ViewWriteResult> => {
    const apply = (result: ViewWriteResult) => { if (result.kind === "done" && result.view && applyIfNoChoiceSince === viewChoices.current) applyView(result.view.id); return result; };
    const result = await controller.mutateView(command);
    return result.kind === "failed" && result.confirmed ? { ...result, confirmed: result.confirmed.then(apply) } : apply(result);
  };
  const savedViews: RecordsViews = {
    items: views,
    applied: appliedView && shownRecipe ? { id: appliedView.id, changed: !sameRecipe(appliedView.recipe, shownRecipe) } : null,
    select: (id) => { const view = views.find((view) => view.id === id); if (view) { clearFiscal(); applyView(id); recipe({ ...view.recipe, page_size: view.recipe.schema_version === 2 ? view.recipe.page_size : state.request.page_size }); } },
    save: async (name) => shownRecipe ? (await outcome(createView({ kind: "create", key: crypto.randomUUID(), body: { name, recipe: shownRecipe } }, viewChoices.current))).kind === "done" : false,
    rename: (id, name) => updateView(id, name, views.find((view) => view.id === id)?.recipe ?? null),
    saveChanges: (id) => updateView(id, undefined, shownRecipe),
    remove: async (id) => {
      const view = views.find((view) => view.id === id);
      if (!view) return null;
      const choiceAtDelete = id === appliedViewId ? viewChoices.current : null;
      const deleted = await outcome(controller.mutateView({ kind: "delete", id, key: crypto.randomUUID(), body: { expected_version: view.version } }));
      if (deleted.kind !== "done") return null;
      // A retry after an unconfirmed restore sends the same key, so the server makes the view once.
      let restore: CreateViewCommand = { kind: "create", key: crypto.randomUUID(), body: { name: view.name, recipe: view.recipe } };
      return async (landed) => {
        const result = await createView(restore, choiceAtDelete);
        if (result.kind === "failed" && result.confirmed) void result.confirmed.then((confirmed) => { if (confirmed.kind === "done") landed(); });
        if (result.kind === "failed" && result.problem.kind !== "uncertain") restore = { ...restore, key: crypto.randomUUID() };
        return result.kind === "done";
      };
    },
    busy: state.load.kind !== "ready" || state.viewOperation.kind === "busy" || uncertain,
    notice: viewProblem ? problem(viewProblem, () => { if (uncertain) void controller.retryView(); else void controller.listViews(); }) : !currentFormat ? <p>{t(`${REPORTING}pending_contract`)}</p> : null,
  };
  const recheckAnnotationAccess = () => {
    setScopeData(null); controller.revoke();
    void controller.refresh().then(() => { if (controller.getSnapshot().load.kind === "ready") void controller.listViews(); });
  };
  const changeFilter = (next: RecordsFilter) => recipe({ filters: { ...state.request.filters, q: next.query, record_families: [next.kind === "venta" ? "sale" : "purchase"] } }, false);
  const applyFilters = (next: PreviewFilters) => recipe({ filters: reportFiltersFromUi(state.request.filters, next, filter.kind) });
  const filtersActive = activeFilterGroups(filters).length > 0;
  const searchActive = Boolean(filter.query.trim());
  const probeAnswer = state.load.kind === "ready" && state.load.answer.matching_count === 0 && (filtersActive || searchActive)
    ? state.load.answer : undefined;
  const [emptyProbe, setEmptyProbe] = useState<EmptyProbe | null>(null);
  const probeQuery = transport?.query ?? queryBusinessReport;
  useEffect(() => {
    if (!probeAnswer) return;
    const abort = new AbortController();
    const stillCurrent = () => {
      const { load } = controller.getSnapshot();
      return !abort.signal.aborted && load.kind === "ready" && load.answer === probeAnswer;
    };
    const check = async () => {
      if (!stillCurrent()) return;
      const { request } = controller.getSnapshot();
      try {
        const { from_date, to_date } = probeAnswer.resolved_period;
        const requestedPeriod = request.filters.period;
        const period = requestedPeriod.kind === "all" || requestedPeriod.kind === "custom"
          ? requestedPeriod : reportPeriodSchema.parse({ kind: "custom", from_date, to_date });
        const read = (filters: ReportFilters) => probeQuery({ userId, businessId, grantId }, { ...request, filters, page: 1, page_size: 25 }, abort.signal);
        if (filtersActive && searchActive) {
          const withoutSearch = await read({ ...request.filters, q: "", period });
          if (!stillCurrent()) return;
          if (withoutSearch.matching_count > 0) {
            setEmptyProbe({ answer: probeAnswer, result: "search" });
            return;
          }
        }
        const { record_families, currencies } = request.filters;
        const selection = await read(reportFiltersSchema.parse({ period, record_families, currencies }));
        if (!stillCurrent()) return;
        const result = selection.matching_count === 0 ? "selection" : filtersActive ? "filters" : "search";
        setEmptyProbe({ answer: probeAnswer, result });
      } catch (error) {
        if (!stillCurrent()) return;
        const failure = reportFailure(error);
        if (failure.kind === "access") {
          setScopeData(null);
          setEmptyProbe({ request: controller.getSnapshot().request, accessFailure: failure });
          controller.revoke();
        } else setEmptyProbe({ answer: probeAnswer, result: failure });
      }
    };
    void check();
    return () => abort.abort();
  }, [probeAnswer, probeQuery, controller, userId, businessId, grantId, filtersActive, searchActive]);
  const probeResult = emptyProbe && "answer" in emptyProbe && emptyProbe.answer === probeAnswer ? emptyProbe.result : undefined;
  const probeAccessFailure = emptyProbe && "request" in emptyProbe && emptyProbe.request === state.request ? emptyProbe.accessFailure : undefined;
  const probePending = Boolean(probeAnswer && !probeResult);
  const probeFailure = typeof probeResult === "object" ? probeResult : undefined;
  const emptyContent = <div className={cardClass}>{probeResult === "filters" ? (
    <EmptyState kind="filtered" mark="search" illustration="/brand/records-search.webp" compact title={t(`${EMPTY_COPY}.filters.title`)} body={t(`${EMPTY_COPY}.filters.body`)}
      action={{ label: t("business.transactions.layout.clear"), run: () => applyFilters(emptyPreviewFilters(filters.amount.currency)) }} />
  ) : probeResult === "search" ? (
    <EmptyState kind="no_results" illustration="/brand/records-search.webp" compact title={t(`${EMPTY_COPY}.search.title`)} body={t(`${EMPTY_COPY}.search.body`)}
      action={{ label: t(`${EMPTY_COPY}.search.clear`), run: () => changeFilter({ ...filter, query: "" }) }} />
  ) : (
    <EmptyState kind="no_results" mark="receipt" illustration="/brand/records-document.webp" compact testId="transacciones-records-empty"
      title={t(`${EMPTY_COPY}.${filter.kind}.title`)} body={t(`${EMPTY_COPY}.selection.body`)} />
  )}</div>;
  // Exportar registros from search lands here and opens the dialog once the table is ready.
  useEffect(() => {
    if (!exportRequested || state.load.kind !== "ready" || !presentation) return;
    clearRecordsExportRequest();
    openExport();
  }, [exportRequested, state.load.kind, presentation]); // eslint-disable-line react-hooks/exhaustive-deps
  const add = <BusinessAddMenu placement="header" />;
  // Agregar lives in the top bar; the toolbar keeps Export as its own button, same gate. A phone keeps Agregar here.
  const toolbarAction = <RecordsExportButton onExport={openExport} enabled={state.load.kind === "ready"} />;
  if (!preferences && state.load.kind !== "failed") return <FullscreenLoading />;
  return <RecordsAnnotationsPreview connected={{ scope, rows, refresh: controller.refresh, revoke: recheckAnnotationAccess }}><PullToRefresh onRefresh={async () => { await controller.refresh(); return controller.getSnapshot().load.kind === "ready" ? "updated" : "failed"; }}>
    <section ref={screen} tabIndex={-1} data-testid="transacciones" data-report-connected data-report-schema={state.request.schema_version} className="pb-6 outline-none">
      {phone || panel.kind !== "transactions" ? <div className="mb-5 flex flex-wrap items-end justify-between gap-3"><h2 className="font-display text-[26px] font-medium tracking-tight text-black dark:text-white">{t("business.transactions.title")}</h2>{add}</div> : null}
      <GuideCard cardId="registros-intro" userId={userId} title={t(`${GUIDE}title`)} points={[
        { label: t(`${GUIDE}browse.label`), body: t(`${GUIDE}browse.body`) },
        { label: t(`${GUIDE}find.label`), body: t(`${GUIDE}find.body`) },
        { label: t(`${GUIDE}pending.label`), body: t(`${GUIDE}pending.body`) },
      ]} />
      <RecordsTypeTabs value={filter.kind} onChange={(kind) => recipe({ filters: { ...state.request.filters, record_families: [kind === "venta" ? "sale" : "purchase"] } }, false)} />
      <RecordsOverviewPreview family={state.request.filters.record_families[0]} answer={answer} fiscalCount={overview?.needs_fiscal_data ?? null} selected={filters.fiscal_data === "missing" ? ["fiscal"] : []} loading={state.load.kind === "loading"} onChoose={toggleFiscal} />
      <RecordsToolbar filter={filter} onChange={changeFilter} period={selectedPeriod} setPeriod={(next) => recipe({ filters: { ...state.request.filters, period: reportPeriodFromUi(typeof next === "string" ? periodRange(next) : next) } })} preferences={preferences} appliedPeriod={selectedPeriod} onPeriodChange={(next) => recipe({ filters: { ...state.request.filters, period: reportPeriodFromUi(next) } })} appliedFilters={filters} onFiltersChange={applyFilters} options={<>{!phone ? <RecordsRefreshButton busy={state.load.kind === "loading"} onRefresh={() => void controller.refresh()} /> : null}{toolbarAction}{currentFormat && preferences && state.load.kind === "ready" ? <RecordsSettingsPreview value={preferences} onChange={(next) => controller.setPresentation(recordsPresentationToReport(next))} onRestore={() => { void controller.restorePresentation(); }} /> : !isBelowDesktop ? <button type="button" className={quietButtonClass} disabled title={t(`${REPORTING}pending_contract`)} aria-label={t("business.transactions.density.options")}><SlidersHorizontal size={18} /></button> : null}</>} connected={{ reportPeriod: state.request.filters.period, catalogues: catalogues ?? { counterparties: [], expense_types: [], funding_sources: [] }, applyFilters, views: savedViews }} />
      {state.load.kind === "failed" ? <div className={cardClass}>{problem(probeAccessFailure ?? state.load.problem, () => { void controller.refresh(); })}</div> : state.load.kind !== "ready" || !preferences || probePending ? (preferences ? <RecordsLoadingPreview preferences={preferences} density={preferences.density} /> : <FullscreenLoading />) : probeFailure ? <div className={cardClass}>{problem(probeFailure, () => { void controller.refresh(); })}</div> : <RecordGlanceContext.Provider value={open}><RecordEvidenceContext.Provider value={open}>
        <RecordsPagePreview records={rows} preferences={preferences} onSortChange={() => undefined} density={preferences.density} resetKey={scopeKey} rowRef={rowRef} emptyContent={emptyContent} connected={{ answer: state.load.answer, onPage: (page) => load({ ...state.request, page }), onPageSize: (page_size) => recipe({ page_size }), onSort: currentFormat ? (sort) => recipe({ sort: recordsSortToReport(sort) }) : undefined }} />
      </RecordEvidenceContext.Provider></RecordGlanceContext.Provider>}
    </section>
    {exporting ? <RecordsExportPanel {...exporting} transport={transport ?? liveReportingTransport} onReviewFiscal={reviewDgiiPending} onClose={() => setExporting(null)} /> : null}
  </PullToRefresh></RecordsAnnotationsPreview>;
}
