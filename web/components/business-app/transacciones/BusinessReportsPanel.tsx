"use client";

import { useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { SlidersHorizontal } from "lucide-react";
import { getChosenGrant } from "@/lib/business-grant";
import { usePanelShell } from "@/components/chat/ChatWorkspace";
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
import { activeFilterGroups, emptyPreviewFilters, type PreviewFilters } from "./records-filter-preview-model";
import { showToast } from "../foundation/toasts";
import { RecordsToolbar, RecordsToolbarPending, type RecordsFilter } from "./RecordsToolbar";
import { sameRecipe, type RecordsViews } from "./RecordsViewsPreview";
import RecordsTypeTabs from "./RecordsTypeTabs";
import RecordsSettingsPreview from "./RecordsSettingsPreview";
import RecordsPagePreview from "./RecordsPagePreview";
import RecordsLoadingPreview, { RecordsLoadingBar } from "./RecordsLoadingPreview";
import loading from "./records-loading-preview.module.css";
import RecordsOverviewPreview from "./RecordsOverviewPreview";
import { RecordArrivalsContext, RecordGlanceContext, type OpenRecordGlance } from "./RecordGlanceContext";
import { useListArrivals } from "../foundation/list-arrivals";
import { focusKey, focusRequest } from "./records-focus";
import { recordRowKey } from "./records-row-preview";
import { useFiscalStageToggle } from "./useFiscalStageToggle";
import { useBusinessReport } from "./useBusinessReport";
import { useTransaccionesWords } from "./transacciones-words";
import { useDelayedPending } from "../business-skeletons";

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
  result.ready = filters.ready;
  result.fiscal_data = filters.fiscal_data;
  result.attachment = filters.has_document === null ? "any" : filters.has_document ? "with" : "without";
  result.amount = { currency, min: filters.amount_min ?? "", max: filters.amount_max ?? "" };
  result.counterparty = filters.counterparties; result.expense_type = filters.expense_types; result.account = filters.funding_sources;
  result.document = filters.document_kinds; result.fiscal = filters.fiscal_classifications.map((value) => value.toLowerCase());
  return result;
}
export function reportFiltersFromUi(current: ReportFilters, filters: PreviewFilters, kind: RecordsFilter["kind"]): ReportFilters {
  return { ...current, record_families: [kind === "venta" ? "sale" : "purchase"], ready: filters.ready, fiscal_data: filters.fiscal_data, review_stages: [], has_document: filters.attachment === "any" ? null : filters.attachment === "with", currencies: [filters.amount.currency], amount_min: filters.amount.min || null, amount_max: filters.amount.max || null, counterparties: filters.counterparty, categories: [], expense_types: kind === "venta" ? [] : filters.expense_type, funding_sources: filters.account, document_kinds: filters.document as ReportFilters["document_kinds"], fiscal_classifications: filters.fiscal.map((value) => /^[be]\d\d$/i.test(value) ? value.toUpperCase() : value) };
}

/** The list Registros opens on: a focus another screen opened, else this scope's saved address, else the latest month. A scope not known yet reads the address as it stands. */
function startingReport(scopeKey: string | null, initial?: ReportRequest) {
  const params = typeof window === "undefined" ? new URLSearchParams() : new URLSearchParams(window.location.search);
  const other = scopeKey !== null && params.has("report_scope") && params.get("report_scope") !== scopeKey;
  const saved = restoreReportLocation(other ? new URLSearchParams() : params);
  return { ...saved, request: initial ?? (params.has("report") && !other ? saved.request : reportRequestSchema.parse({ filters: { period: { kind: "latest_month" } } })) };
}

/** A phone's heading and Agregar; from the tablet stop up the top bar holds both, also beside an open record. */
function RecordsHeading() {
  const { isBelowTablet: phone } = useResponsiveLayout();
  const { t } = useTransaccionesWords();
  return phone ? <div data-surface-block="heading" className="mb-5 flex flex-wrap items-end justify-between gap-3"><h2 className="font-display text-[26px] font-medium tracking-tight text-black dark:text-white">{t("business.transactions.title")}</h2><BusinessAddMenu placement="header" /></div> : null;
}

/** Until the first wait has lasted the shared delay, the screen paints nothing, then all of its placeholders at once. */
const unseen = (shown: boolean) => shown ? undefined : { visibility: "hidden" as const };

/** The guide's place is known before the page draws: the person's account says whether it was dismissed. */
function RecordsGuide({ pending }: { pending: boolean }) {
  const { t } = useTransaccionesWords();
  return <GuideCard cardId="registros-intro" pending={pending} title={t(`${GUIDE}title`)} points={[
    { label: t(`${GUIDE}browse.label`), body: t(`${GUIDE}browse.body`) },
    { label: t(`${GUIDE}find.label`), body: t(`${GUIDE}find.body`) },
    { label: t(`${GUIDE}pending.label`), body: t(`${GUIDE}pending.body`) },
  ]} />;
}

/** Before the report can be asked, Registros is its own layout with pending values: the guide's place, the tabs, the overview cards, the toolbar, then the table. */
function RecordsPendingLayout({ family, shown }: { family: ReportFilters["record_families"][0]; shown: boolean }) {
  const { isBelowDesktop } = useResponsiveLayout();
  return <section className="pb-6" style={unseen(shown)}>
    <RecordsHeading />
    <RecordsGuide pending />
    <RecordsTypeTabs value={family === "sale" ? "venta" : "gasto"} />
    <RecordsOverviewPreview family={family} notReadyCount={null} selected={false} loading shown={shown} onChoose={() => undefined} />
    <RecordsToolbarPending options={<><RecordsExportButton pending />{isBelowDesktop ? null : <RecordsLoadingBar className={`${loading.control} ${loading.iconControl} !rounded-full`} />}</>} />
    <RecordsLoadingPreview shown={shown} />
  </section>;
}

export function RecordsWorkspaceUnavailable() {
  const { records, reload } = useBusiness();
  const { t } = useTransaccionesWords();
  return <div className={cardClass}><EmptyState kind="error" compact title={t(`${REPORTING}${records.refused ? "access_unavailable" : "unavailable"}`)} action={records.refused ? undefined : { label: t("common.retry"), run: reload }} />{records.failureReference ? <ReferenceCode reference={records.failureReference} /> : null}</div>;
}

export default function BusinessReportsPanel() {
  const { chosen, records, panel } = useBusiness();
  const focus = panel.kind === "transactions" ? panel.focus : undefined;
  // The shell renders its screens only after its account answers, so the person is known on the first render.
  const person = usePanelShell()?.memberId ?? null;
  const { t } = useTransaccionesWords();
  const defaultCurrency = recordsCurrencySchema.safeParse(records.workspace?.records_default_currency);
  const connectedKey = person && chosen && records.workspaceGrant === getChosenGrant() && defaultCurrency.success ? `${person}:${chosen.space_id}:${getChosenGrant()}:${focusKey(focus)}` : null;
  // One wait from the first paint to the first answer, so the placeholders never restart when the report is asked.
  const [answered, setAnswered] = useState<string | null>(null);
  const firstLoadShown = useDelayedPending(connectedKey === null || answered !== connectedKey);
  const onFirstLoad = useCallback(() => setAnswered(connectedKey), [connectedKey]);
  if (!person) return <div className={cardClass}><EmptyState kind="error" compact title={t(`${REPORTING}access_unavailable`)} /></div>;
  if ((!defaultCurrency.success || records.workspaceGrant !== getChosenGrant()) && (records.error || records.workspaceGrant === getChosenGrant() && records.workspace)) return <RecordsWorkspaceUnavailable />;
  // A focus another screen opened starts Registros on exactly that list.
  const initial = focus ? focusRequest(focus) : undefined;
  if (!chosen || connectedKey === null || !defaultCurrency.success) return <RecordsPendingLayout family={startingReport(chosen ? `${person}:${chosen.space_id}` : null, initial).request.filters.record_families[0]} shown={firstLoadShown} />;
  const scope = { userId: person, businessId: chosen.space_id, grantId: getChosenGrant() };
  return <ConnectedBusinessReports key={connectedKey} scope={scope} defaultCurrency={defaultCurrency.data} initial={initial} firstLoadShown={firstLoadShown} onFirstLoad={onFirstLoad} />;
}

export function ConnectedBusinessReports({ scope, transport, initial, defaultCurrency, firstLoadShown, onFirstLoad }: { defaultCurrency: RecordsCurrency; scope: ReportScope; transport?: ReportingTransport; initial?: ReportRequest; firstLoadShown?: boolean; onFirstLoad?: () => void }) {
  const openSelectedRow = useContext(RecordGlanceContext);
  const { t } = useTransaccionesWords();
  const { panel, openPanel, revision, records } = useBusiness();
  const { isBelowDesktop } = useResponsiveLayout();
  const { userId, businessId, grantId } = scope;
  const scopeKey = `${userId}:${businessId}`;
  const singleCurrency = useCallback((request: ReportRequest): ReportRequest => {
    request = { ...request, filters: { ...request.filters, review_stages: [] } };
    if (request.filters.currencies.length === 1 && recordsCurrencySchema.safeParse(request.filters.currencies[0]).success) return request;
    return { ...request, filters: { ...request.filters, currencies: [defaultCurrency], amount_min: null, amount_max: null } };
  }, [defaultCurrency]);
  const [restored] = useState(() => {
    const start = startingReport(scopeKey, initial);
    return { ...start, request: singleCurrency(start.request) };
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
  const { toggle: toggleFiscal, clear: clearFiscal } = useFiscalStageToggle(filters, (selection) => load(reportRequestSchema.parse({ ...state.request, filters: { ...state.request.filters, ready: selection.ready, review_stages: [] }, page: 1 })));
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
  // The Business's one change check says when something changed; the table reads itself again without leaving the screen.
  const arrivals = useListArrivals(screen, "data-record-key");
  const { hold, arrived } = arrivals;
  // The table owes a read until one lands for the latest change. A read that did not land is asked again on the next answered check.
  const listChanges = records.listChanges ?? 0;
  const delivered = useRef(listChanges);
  const asked = useRef<number | null>(null);
  useEffect(() => { const stop = controller.subscribe(() => { if (asked.current !== null) hold(); }); return () => { stop(); }; }, [controller, hold]);
  useEffect(() => {
    if (delivered.current === listChanges || asked.current === listChanges) return;
    asked.current = listChanges;
    void controller.refreshQuietly().then((landed) => {
      if (!landed) return;
      delivered.current = listChanges;
      arrived(landed);
    }).finally(() => { if (asked.current === listChanges) asked.current = null; });
  }, [listChanges, records.listChecks, controller, arrived]);
  // A first-version answer from a server that has the current format is asked again in it, so it is not the answer yet.
  const upgrading = state.load.kind === "ready" && state.request.schema_version === 1 && Boolean(state.load.answer.overview && state.load.answer.effective_sort);
  useEffect(() => {
    if (upgrading) void controller.load(reportRequestSchema.parse({ ...state.request, schema_version: 2 }));
  }, [controller, upgrading, state.request]);
  // A record that left the current view says so once, in a toast; nothing above the table moves.
  useEffect(() => {
    if (state.load.kind !== "ready" || !state.missingAnchor) return;
    showToast({ kind: "info", text: t("business.search.record_unavailable") });
    controller.rememberAnchor(null);
  }, [controller, state.load.kind, state.missingAnchor, t]);
  const recipe = (patch: Partial<ReportRequest>, push = true) => {
    if (patch.filters && patch.filters.ready !== state.request.filters.ready) clearFiscal();
    load(singleCurrency(reportRequestSchema.parse({ ...state.request, ...patch, page: 1 })), push);
  };
  const open: OpenRecordGlance = (row, options) => {
    if (!row.opens) return;
    const id = recordRowKey(row);
    focused.current = null; controller.rememberAnchor(id); updateUrl(state.request, id);
    if (openSelectedRow) {
      openSelectedRow(row, {
        detailsCard: options?.detailsCard,
        refresh: async (signal) => {
          const answer = await (transport ?? liveReportingTransport).query(scope, state.request, signal);
          const next = answer.items.find((item) => item.row_id === row.report?.row_id);
          return next ? businessReportRow(next) : null;
        },
      });
    } else {
      openPanel(options?.detailsCard ? { ...row.opens, detailsCard: options.detailsCard } : row.opens);
    }
  };
  const rowRef = (id: string, node: HTMLElement | null) => { if (node) rowNodes.current.set(id, node); else rowNodes.current.delete(id); };
  const periodLabel = useRecordsPeriodLabel();
  // The export works on the table's request as it stood when Exportar was pressed.
  const [exporting, setExporting] = useState<{ request: ReportRequest; scope: ReportScope; periodLabel: string; filterCount: number } | null>(null);
  const exportRequested = useRecordsExportRequested();
  // Revisar restores the DGII fiscal scope and clears the other table filters.
  const reviewDgiiPending = (currency: string) => recipe({ filters: reportFiltersSchema.parse({ period: state.request.filters.period, record_families: state.request.filters.record_families, currencies: [currency], fiscal_data: "missing" }) });
  const openExport = () => { if (presentation) setExporting({ scope: { userId, businessId, grantId }, request: reportRequestSchema.parse({ ...state.request, schema_version: 2, presentation }), periodLabel: periodLabel(selectedPeriod, state.request.filters.period), filterCount: activeFilterGroups(filters).length + (filter.query.trim() ? 1 : 0) }); };
  const views = state.views.kind === "ready" ? state.views.items : [];
  const viewProblem = state.viewOperation.kind === "failed" ? state.viewOperation.problem : state.views.kind === "failed" ? state.views.problem : null;
  const uncertain = state.viewOperation.kind === "failed" && state.viewOperation.problem.kind === "uncertain";
  const problem = (failure: ReportFailure, retry: () => void): ReactNode => <p role="alert" className="mb-3 text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{t(`${REPORTING}${failure.kind === "access" ? "access_unavailable" : failure.kind === "version" ? "view_changed" : failure.kind === "uncertain" ? "uncertain_view" : "unavailable"}`)}{failure.kind !== "access" && failure.kind !== "conflict" ? <button type="button" className={quietButtonClass} onClick={retry}>{t(`${REPORTING}${failure.kind === "version" ? "refresh" : "retry"}`)}</button> : null}{failure.requestId ? <ReferenceCode reference={failure.requestId} /> : null}</p>;
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
  const answerPending = state.load.kind === "idle" || state.load.kind === "loading" || upgrading;
  // The table draws once the answer, its columns and any empty-list check are all in.
  const table = state.load.kind === "ready" && !upgrading && preferences && !probePending ? { answer: state.load.answer, preferences } : null;
  const tablePending = state.load.kind !== "failed" && !table;
  const [drawn, setDrawn] = useState(false);
  if (!tablePending && !drawn) setDrawn(true);
  const firstWait = tablePending && !drawn;
  const skeletonPending = tablePending || firstWait;
  const tableWaited = useDelayedPending(skeletonPending);
  const skeletonShown = skeletonPending && (tableWaited || firstLoadShown === true);
  useEffect(() => { if (!firstWait) onFirstLoad?.(); }, [firstWait, onFirstLoad]);
  useEffect(() => {
    if (panel.kind !== "transactions" || state.load.kind !== "ready" || firstWait || !state.anchor || focused.current === state.anchor) return;
    focused.current = state.anchor;
    (rowNodes.current.get(state.anchor) ?? screen.current)?.focus();
  }, [panel.kind, state.load, state.anchor, firstWait]);
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
  // Agregar lives in the top bar; the toolbar keeps Export as its own button, same gate. A phone keeps Agregar in the heading.
  const toolbarAction = <RecordsExportButton onExport={openExport} enabled={state.load.kind === "ready"} />;
  return <PullToRefresh onRefresh={async () => { await controller.refresh(); return controller.getSnapshot().load.kind === "ready" ? "updated" : "failed"; }}>
    <section ref={screen} tabIndex={-1} data-testid="transacciones" data-report-connected data-report-schema={state.request.schema_version} className="pb-6 outline-none" style={unseen(!firstWait || skeletonShown)}>
      <RecordsHeading />
      <RecordsGuide pending={firstWait} />
      <RecordsTypeTabs value={filter.kind} onChange={(kind) => recipe({ filters: { ...state.request.filters, record_families: [kind === "venta" ? "sale" : "purchase"] } }, false)} />
      <RecordsOverviewPreview family={state.request.filters.record_families[0]} answer={answer} notReadyCount={overview?.not_ready ?? null} selected={filters.ready === false} loading={answerPending || firstWait} shown={skeletonShown} onChoose={toggleFiscal} />
      <RecordsToolbar filter={filter} onChange={changeFilter} period={selectedPeriod} setPeriod={(next) => recipe({ filters: { ...state.request.filters, period: reportPeriodFromUi(typeof next === "string" ? periodRange(next) : next) } })} preferences={preferences} appliedPeriod={selectedPeriod} onPeriodChange={(next) => recipe({ filters: { ...state.request.filters, period: reportPeriodFromUi(next) } })} appliedFilters={filters} onFiltersChange={applyFilters} options={<>{toolbarAction}{currentFormat && preferences && state.load.kind === "ready" ? <RecordsSettingsPreview value={preferences} onChange={(next) => controller.setPresentation(recordsPresentationToReport(next))} onRestore={() => { void controller.restorePresentation(); }} /> : !isBelowDesktop ? <button type="button" className={quietButtonClass} disabled title={t(`${REPORTING}pending_contract`)} aria-label={t("business.transactions.density.options")}><SlidersHorizontal size={18} /></button> : null}</>} connected={{ reportPeriod: state.request.filters.period, catalogues: catalogues ?? { counterparties: [], expense_types: [], funding_sources: [] }, applyFilters, views: savedViews }} />
      {firstWait ? <RecordsLoadingPreview preferences={preferences} density={preferences?.density} shown={skeletonShown} /> : state.load.kind === "failed" ? <div className={cardClass}>{problem(probeAccessFailure ?? state.load.problem, () => { void controller.refresh(); })}</div> : !table ? <RecordsLoadingPreview preferences={preferences} density={preferences?.density} shown={skeletonShown} /> : probeFailure ? <div className={cardClass}>{problem(probeFailure, () => { void controller.refresh(); })}</div> : <RecordArrivalsContext.Provider value={arrivals.fresh}><RecordGlanceContext.Provider value={open}>
        <RecordsPagePreview records={rows} preferences={table.preferences} onSortChange={() => undefined} density={table.preferences.density} resetKey={scopeKey} rowRef={rowRef} emptyContent={emptyContent} connected={{ answer: table.answer, onPage: (page) => load({ ...state.request, page }), onPageSize: (page_size) => recipe({ page_size }), onSort: currentFormat ? (sort) => recipe({ sort: recordsSortToReport(sort) }) : undefined }} />
      </RecordGlanceContext.Provider></RecordArrivalsContext.Provider>}
    </section>
    {exporting ? <RecordsExportPanel {...exporting} transport={transport ?? liveReportingTransport} onReviewFiscal={reviewDgiiPending} onClose={() => setExporting(null)} /> : null}
  </PullToRefresh>;
}
