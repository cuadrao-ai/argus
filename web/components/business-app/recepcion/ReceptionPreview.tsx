"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { resolveLanguage } from "@/lib/language-features";
import type { ReceiptSummary } from "@/lib/business-api";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { PullToRefresh } from "@/components/ui/PullToRefresh";
import { useBusiness } from "../BusinessWorkspace";
import ReceiptReadingControl from "../ReceiptReadingControl";
import { loadFailure, type LoadFailure } from "../bandeja-sources";
import ReceptionBulkBar from "./ReceptionBulkBar";
import { applyOrganizationPreview, emptyOrganizationPreview, undoOrganizationPreview, type OrganizationAction, type OrganizationPreview } from "./reception-organization-preview";
import ReceptionAddMenu from "./ReceptionAddMenu";
import ReceptionFilters, { ReceptionFilterChips } from "./ReceptionFilters";
import { emptyReceptionFilters, receptionFilterMatches, receptionArrivedInPeriod, receptionSenderIdentity, type SenderIdentity, type ReceptionFiltersValue } from "./reception-filters";
import ReceptionEmptyState from "./ReceptionEmptyState";
import { showToast, dismissToast } from "../foundation/toasts";
import { primaryButtonClass, quietButtonClass } from "../business-ui";
import { receptionNoteExample, receptionRows, receptionMatches, receptionSearchText, type ReceptionRow, type ReceptionView } from "./reception-model";
import { inboxCount, problemCount, readingCount } from "../inbox-count";
import ReceptionArrivalRow from "./ReceptionArrivalRow";
import ReceptionDossier from "./ReceptionDossier";
import ReceptionSkeleton from "./ReceptionSkeleton";
import { ReceptionSearch, ReceptionSettings, defaultReceptionPreferences, type ReceptionPreferences } from "./ReceptionControls";
import { periodRange, type Period } from "../business-format";
import RecordsDatePreview from "../transacciones/RecordsDatePreview";
import RecordsPaginationControls from "../transacciones/RecordsPaginationControls";
import { INITIAL_PAGINATION, type PaginationState } from "../transacciones/records-pagination";
import { previewAmountColumnSize } from "../transacciones/records-row-preview";
import { RECORDS_PREVIEW_COLUMNS } from "../transacciones/records-view-preferences";
import { DENSITY_ROW_PX } from "../transacciones/table-density";
import styles from "./reception.module.css";

type ReceptionTab = ReceptionView | "archived" | "combined";
const BASE_VIEWS: ReceptionTab[] = ["all", "review", "processing", "attention"];
const BASE_COLUMN_PX = 44;
type ArrivalLoad = { scope: string; source: ReturnType<typeof useBusiness>["source"]; items: ReceiptSummary[]; failure: LoadFailure | null };


type ReturnPosition = { scope: string; filters: ReceptionFiltersValue; query: string; page: number; pageSize: PaginationState["pageSize"]; period: Period; archived: boolean; admittedIds: string[] | null; organization: OrganizationPreview; preferences: ReceptionPreferences };
// Only the immediate dossier return uses this in-memory snapshot. Reload never restores it.
const dossierReturns = new WeakMap<object, ReturnPosition>();

/**
 * `live` renders the server's arrivals and nothing else. Archive, restore,
 * seen and unseen have no durable backend, so live hides them and the dev
 * preview keeps its local, labeled stand-ins.
 */
export default function ReceptionPreview({ live = false }: { live?: boolean }) {
  const { chosen } = useBusiness();
  return <ReceptionWorkspace live={live} key={`${chosen?.space_id ?? "own"}:${chosen?.grant_id ?? chosen?.role ?? "unknown"}`} />;
}

function ReceptionWorkspace({ live }: { live: boolean }) {
  const { t, i18n } = useTranslation();
  const locale = resolveLanguage({ device: i18n.resolvedLanguage ?? i18n.language });
  const word = (key: string) => t(`business.reception_preview.${key}`);
  const { source, records, chosen, panel, openPanel, revision, refresh, reload, retrySources } = useBusiness();
  const { isBelowTablet: phone } = useResponsiveLayout();
  const scope = `${chosen?.space_id ?? "own"}:${chosen?.grant_id ?? chosen?.role ?? "unknown"}`;
  const [returnPosition] = useState(() => { const saved = dossierReturns.get(source); return saved?.scope === scope ? saved : undefined; });
  useEffect(() => { if (panel.kind === "inbox") dossierReturns.delete(source); }, [source, panel.kind]);
  const [noteArrivedAt] = useState(() => new Date().toISOString());
  const [loaded, setLoaded] = useState<ArrivalLoad | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [filters, setFilters] = useState(() => returnPosition?.filters ?? emptyReceptionFilters());
  const [page, setPage] = useState(returnPosition?.page ?? 1);
  const [pageSize, setPageSize] = useState<PaginationState["pageSize"]>(returnPosition?.pageSize ?? INITIAL_PAGINATION.pageSize);
  const [period, setPeriod] = useState<Period>(() => returnPosition?.period ?? periodRange("all"));
  const [admittedIds, setAdmittedIds] = useState<string[] | null>(returnPosition?.admittedIds ?? null);
  const [archived, setArchived] = useState(returnPosition?.archived ?? false);
  const activeTab: ReceptionTab = archived ? "archived" : filters.states.length > 1 ? "combined" : filters.states[0] ?? "all";
  const views: ReceptionTab[] = [...BASE_VIEWS, ...(filters.states.length > 1 ? ["combined" as const] : []), ...(live ? [] : ["archived" as const])];
  const [organization, setOrganization] = useState(() => returnPosition?.organization ?? emptyOrganizationPreview());
  const [openedId, setOpenedId] = useState<string | null>(null);
  const detailTrigger = useRef<HTMLElement | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const organizationToast = useRef<number | null>(null);
  useEffect(() => () => { if (organizationToast.current !== null) dismissToast(organizationToast.current); }, []);
  const list = useRef<HTMLDivElement>(null);
  const chooseTab = (next: ReceptionTab) => {
    setArchived(next === "archived");
    if (next !== "combined") setFilters(current => ({ ...current, states: next === "all" || next === "archived" ? [] : [next] }));
    setSelectedIds([]); setPage(1);
  };
  const applyFilters = (next: ReceptionFiltersValue) => { setFilters(next); setSelectedIds([]); setPage(1); };
  const [query, setQuery] = useState(returnPosition?.query ?? "");
  const tabs = useRef<HTMLDivElement>(null);
  const [preferences, setPreferences] = useState(() => returnPosition?.preferences ?? defaultReceptionPreferences());
  // The poll hands over a new array every tick; re-read the full list only when what it carries changed.
  const inboxContent = useMemo(() => JSON.stringify(records.inbox), [records.inbox]);
  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    const request = source.receiptPage ? source.receiptPage("all", controller.signal).then(page => page.items) : source.receipts("all");
    void request.then(items => { if (current) setLoaded({ scope, source, items, failure: null }); }, error => {
      if (current) setLoaded(previous => ({ scope, source, items: previous?.scope === scope && previous.source === source ? previous.items : [], failure: loadFailure(error) }));
    });
    return () => { current = false; controller.abort(); };
  }, [source, scope, revision, attempt, inboxContent]);
  const arrivals = loaded?.scope === scope && loaded.source === source ? loaded : null;
  const pending = !arrivals || records.notes === null || records.emails === null;
  const failed = !!arrivals?.failure || records.error || !!records.notesFailure || !!records.emailsFailure;
  const refused = records.refused || arrivals?.failure?.refused;
  const retryableSources = (["notes", "emails"] as const).filter(key => {
    const failure = key === "notes" ? records.notesFailure : records.emailsFailure;
    return failure && !failure.refused && !failure.offline;
  });
  const retryableArrivals = arrivals?.failure && !arrivals.failure.refused && !arrivals.failure.offline;
  const canRetry = !refused && (retryableArrivals || records.error || retryableSources.length > 0);
  const latestRows = refused ? [] : [...(live ? [] : [receptionNoteExample(word("note_example"), noteArrivedAt)]), ...receptionRows(arrivals?.items ?? [], records.notes ?? [], records.emails ?? [])];
  const latestIds = latestRows.map(row => `${row.kind}:${row.id}`);
  const admissionKey = latestIds.join("|");
  useEffect(() => {
    if (!pending && !failed && admittedIds === null) {
      const initialIds = admissionKey ? admissionKey.split("|") : [];
      setAdmittedIds(initialIds);
      // Seed mixed attention only on the first load of this development preview.
      if (!live) setOrganization(current => applyOrganizationPreview(current, initialIds.filter((_, index) => index % 3 === 0), "unseen"));
    }
  }, [pending, failed, admittedIds, admissionKey, live]);
  const byId = new Map(latestRows.map(row => [`${row.kind}:${row.id}`, row]));
  const openedRow = openedId ? byId.get(openedId) : undefined;
  const rows = (admittedIds ?? latestIds).map(id => byId.get(id)).filter((row): row is ReceptionRow => !!row);
  const newCount = admittedIds ? latestIds.filter(id => !admittedIds.includes(id)).length : 0;
  const senders = [...new Map(rows.map(receptionSenderIdentity).filter((value): value is SenderIdentity => !!value).map(sender => [sender.id, sender])).values()].sort((a, b) => (a.name || a.address).localeCompare(b.name || b.address, locale));
  const queryText = query.trim().toLocaleLowerCase(locale);
  const matched = rows.filter(row => organization.archived.includes(`${row.kind}:${row.id}`) === archived && receptionFilterMatches(row, filters) && receptionArrivedInPeriod(row, period) && (!queryText || receptionSearchText(row).toLocaleLowerCase(locale).includes(queryText)));
  const pages = Math.max(1, Math.ceil(matched.length / pageSize));
  const currentPage = Math.min(page, pages);
  const shown = matched.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const amountSize = previewAmountColumnSize(matched.flatMap(row => row.kind === "receipt" && row.receipt.amount != null && row.receipt.currency ? [{ amount: row.receipt.amount, currency: row.receipt.currency }] : []), locale);
  const recordsWidth = (key: "contraparte" | "moneda" | "fecha") => RECORDS_PREVIEW_COLUMNS.find(column => column.key === key)!.width!;
  const documentWidth = recordsWidth("contraparte");
  const attachmentWidth = 104;
  const senderWidth = 180;
  const statusWidth = 240;
  const currencyWidth = preferences.currency ? recordsWidth("moneda") : 0;
  const arrivalWidth = preferences.arrival ? recordsWidth("fecha") : 0;
  const moneyColumns = `${preferences.amount ? amountSize.width : ""} ${currencyWidth ? `${currencyWidth}px` : ""}`;
  const selectWidth = live ? 0 : BASE_COLUMN_PX;
  const commonWidth = selectWidth + documentWidth + attachmentWidth + currencyWidth + statusWidth + arrivalWidth + 136;
  const minimum = (sourceWidth: number) => `calc(${commonWidth + sourceWidth}px + ${preferences.amount ? amountSize.width : "0px"})`;
  const selectColumn = live ? "" : `${BASE_COLUMN_PX}px`;
  const columns = `${selectColumn} minmax(${documentWidth}px, 1.2fr) ${attachmentWidth}px ${preferences.source ? "150px" : ""} ${preferences.sender ? `minmax(${senderWidth}px, 240px)` : ""} ${moneyColumns} minmax(${statusWidth}px, 0.8fr) ${arrivalWidth ? `${arrivalWidth}px` : ""} 136px`;
  const compactColumns = `${selectColumn} minmax(${documentWidth}px, 1.2fr) ${attachmentWidth}px ${preferences.source || preferences.sender ? `minmax(${senderWidth}px,240px)` : ""} ${moneyColumns} minmax(${statusWidth}px, 0.8fr) ${arrivalWidth ? `${arrivalWidth}px` : ""} 136px`;
  const closeDetail = () => {
    setOpenedId(null);
    requestAnimationFrame(() => {
      (detailTrigger.current?.isConnected ? detailTrigger.current : list.current)?.focus({ preventScroll: true });
    });
  };
  const navigateFrom = (row: ReceptionRow, next: Parameters<typeof openPanel>[0]) => {
    dossierReturns.set(source, { scope, filters, query, page: currentPage, pageSize, period, archived, admittedIds, organization: live ? organization : applyOrganizationPreview(organization, [`${row.kind}:${row.id}`], "seen"), preferences });
    setOpenedId(null);
    openPanel(next);
  };
  const pageIds = shown.map(row => `${row.kind}:${row.id}`);
  const selected = selectedIds.filter(id => pageIds.includes(id));
  const allSelected = pageIds.length > 0 && selected.length === pageIds.length;
  const apply = (action: OrganizationAction) => {
    if ((action === "archive" || action === "restore") && !chosen?.capabilities.includes("prepare")) return;
    if (!selected.length) return;
    const before = organization;
    const ids = [...selected];
    setOrganization(current => applyOrganizationPreview(current, ids, action));
    organizationToast.current = showToast({ kind: "success", text: t(`business.reception_preview.toast_${action}`, { count: ids.length }), action: {
      label: t("business.marks.undo"),
      run: () => {
        setOrganization(current => undoOrganizationPreview(current, before, ids, action));
        organizationToast.current = showToast({ kind: "success", text: word("toast_undone") });
        requestAnimationFrame(() => list.current?.focus({ preventScroll: true }));
      },
    } });
    setSelectedIds([]);
    requestAnimationFrame(() => list.current?.focus({ preventScroll: true }));
  };
  const activeRows = rows.filter(row => !organization.archived.includes(`${row.kind}:${row.id}`));
  const counts = live
    ? { all: undefined, review: inboxCount(records), processing: readingCount(records), attention: problemCount(records), archived: undefined, combined: undefined }
    : { all: undefined, review: activeRows.filter(row => receptionMatches(row, "review")).length, processing: activeRows.filter(row => receptionMatches(row, "processing")).length, attention: activeRows.filter(row => receptionMatches(row, "attention")).length, archived: rows.length - activeRows.length, combined: undefined };
  const unseenIds = new Set(live ? rows.filter(row => row.kind === "receipt" && row.receipt.activity?.unread === true).map(row => `${row.kind}:${row.id}`) : organization.unseen);
  const markSeenLocally = (row: ReceptionRow) => { if (!live) setOrganization(current => applyOrganizationPreview(current, [`${row.kind}:${row.id}`], "seen")); };
  const reviewNext = live && chosen?.role === "accountant" ? rows.find(row => row.kind === "receipt" && row.receipt.bandeja?.por_revisar === true) : undefined;
  const inPanel = phone || panel.kind !== "inbox";
  const retry = () => {
    if (retryableArrivals) setAttempt(value => value + 1);
    if (records.error && !records.refused) reload();
    if (retryableSources.length) retrySources(retryableSources);
  };
  const clear = () => { applyFilters(emptyReceptionFilters()); setQuery(""); setPeriod(periodRange("all")); };
  return <PullToRefresh onRefresh={refresh}>
    <section className={styles.workspace} aria-label={t("business.inbox.title")} data-testid="reception-preview" data-mode={live ? "live" : "preview"} data-selectable={!live} data-density={preferences.density} data-source={preferences.source || preferences.sender} data-arrival={preferences.arrival} style={{ "--columns": columns, "--compact-columns": compactColumns, "--table-min-width": minimum((preferences.source ? 150 : 0) + (preferences.sender ? senderWidth : 0)), "--compact-min-width": minimum(preferences.source || preferences.sender ? senderWidth : 0), "--row-height": `${DENSITY_ROW_PX[preferences.density]}px` } as CSSProperties}>
      {inPanel ? <div className={styles.phoneHeading}><h2 className="font-display">{t("business.inbox.title")}</h2></div> : null}
      <div className={styles.topline}>
        <div ref={tabs} className={styles.tabs} role="tablist" aria-label={word("views")} onKeyDown={event => {
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          const index = views.indexOf(activeTab);
          const next = event.key === "Home" ? 0 : event.key === "End" ? views.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + views.length) % views.length;
          chooseTab(views[next]);
          tabs.current?.querySelectorAll<HTMLButtonElement>("button")[next]?.focus();
        }}>
          {views.map(value => <button key={value} id={`reception-tab-${value}`} type="button" role="tab" aria-selected={activeTab === value} aria-controls="reception-list" tabIndex={activeTab === value ? 0 : -1} onClick={() => chooseTab(value)}>
            {word(value)}{value !== "all" && value !== "combined" ? <span className={styles.count}>{pending || failed ? "-" : counts[value] ?? "-"}</span> : null}
          </button>)}
        </div>
      </div>
      <div className={styles.toolbar} data-selecting={selected.length > 0}>
        <ReceptionSearch value={query} onChange={next => { setSelectedIds([]); setPage(1); setQuery(next); }} />
        <div role="group" aria-label={word("arrival_date")}><RecordsDatePreview period={period} value={period} title={word("arrival_date")} allDatesLabel={word("all_dates")} onChange={next => { setSelectedIds([]); setPage(1); setPeriod(next); }} /></div>
        <ReceptionFilters key={scope} senders={senders} value={filters} onChange={applyFilters} />
        {live ? null : <div className={styles.bulkSlot}>{selected.length ? <ReceptionBulkBar count={selected.length} archived={archived} canOrganize={chosen?.capabilities.includes("prepare") === true} apply={apply} clear={() => setSelectedIds([])} /> : null}</div>}
        {query || period.key !== "all" ? <button className={quietButtonClass} onClick={clear}>{word("clear")}</button> : null}
        <div className={styles.tools}>{reviewNext ? <button type="button" data-testid="business-primary-review" className={primaryButtonClass} onClick={() => navigateFrom(reviewNext, { kind: "receipt", receiptId: reviewNext.id, list: "inbox" })}>{t("business.inbox.review_receipts")}</button> : null}<ReceptionAddMenu key={scope} /><ReceptionSettings value={preferences} onChange={setPreferences} /></div>
      </div>
      {newCount > 0 ? <div className={styles.updateNotice} role="status"><span>{t("business.reception_preview.new_arrivals", { count: newCount })}</span><button type="button" className={quietButtonClass} onClick={() => { setAdmittedIds(latestIds); setSelectedIds([]); setPage(1); }}>{word("update_list")}</button></div> : null}
      <ReceptionFilterChips value={filters} senders={senders} onChange={applyFilters} />
      <ReceiptReadingControl />
      {failed ? <div className={styles.error} role="alert"><p>{refused ? t("auth.business_unavailable.title") : word("error")}</p>{canRetry ? <button className={quietButtonClass} onClick={retry}>{t("common.retry")}</button> : null}</div> : null}
      <div ref={list} id="reception-list" role="tabpanel" aria-labelledby={`reception-tab-${activeTab}`} tabIndex={0} className={styles.list}>
        <div className={styles.columns}>{live ? null : <label className={styles.checkbox}><input type="checkbox" checked={allSelected} disabled={pending || failed || !pageIds.length} aria-label={word("select_page")} ref={node => { if (node) node.indeterminate = selected.length > 0 && !allSelected; }} onChange={() => setSelectedIds(allSelected ? [] : pageIds)} /></label>}<span>{word("document")}</span><span>{word("file")}</span>{preferences.source ? <span className={styles.channelHeading}>{word("source")}</span> : null}{preferences.sender ? <span className={styles.senderHeading}>{word("sender")}</span> : null}{preferences.source || preferences.sender ? <span className={styles.combinedHeading}>{word(preferences.source && preferences.sender ? "sender_source" : preferences.source ? "source" : "sender")}</span> : null}{preferences.amount ? <span className={styles.amountHeading}>{word("amount")}</span> : null}{preferences.currency ? <span className={styles.currencyHeading}>{t("business.transactions.columns.moneda")}</span> : null}<span>{word("status")}</span>{preferences.arrival ? <span>{word("arrival")}</span> : null}<span className="sr-only">{word("next_action")}</span></div>
        {pending && !failed ? <ReceptionSkeleton preferences={preferences} selectable={!live} /> : <ul aria-label={word("list_label")}>
          {shown.map(row => <ReceptionArrivalRow key={`${row.kind}-${row.id}`} row={row} panel={panel} openPanel={next => navigateFrom(row, next)} inspecting={openedId === `${row.kind}:${row.id}`} onInspect={() => { detailTrigger.current = document.activeElement as HTMLElement; markSeenLocally(row); setOpenedId(`${row.kind}:${row.id}`); }} preferences={preferences} selectable={!live} checked={selected.includes(`${row.kind}:${row.id}`)} unseen={unseenIds.has(`${row.kind}:${row.id}`)} onCheck={() => { const id = `${row.kind}:${row.id}`; setSelectedIds(selected.includes(id) ? selected.filter(value => value !== id) : [...selected, id]); }} onSeen={() => markSeenLocally(row)} />)}
        </ul>}
        {!pending && !failed && !shown.length ? <ReceptionEmptyState filtered={rows.length > 0} title={word(rows.length ? "empty" : "empty_start")} body={word(rows.length ? "empty_help" : "empty_start_help")} action={rows.length ? { label: word("clear"), run: clear } : undefined} /> : null}
      </div>
      {!pending && !failed ? <RecordsPaginationControls page={currentPage} pages={pages} pageSize={pageSize} rangeLabel={t("business.reception_preview.document_range", { from: matched.length ? (currentPage - 1) * pageSize + 1 : 0, to: Math.min(currentPage * pageSize, matched.length), count: matched.length })} label={word("pagination")} pageSizeLabel={word("page_size")} onPageChange={next => { setSelectedIds([]); setPage(next); }} onPageSizeChange={size => { setSelectedIds([]); setPageSize(size); setPage(1); }} /> : null}
      {records.notesTruncated ? <p className={styles.historyNote}>{t("business.inbox.notes_latest")}</p> : null}
      {openedRow ? <ReceptionDossier key={openedId} live={live} row={openedRow} returnFocusRef={detailTrigger} onClose={closeDetail} onNavigate={next => navigateFrom(openedRow, next)} /> : null}
    </section>
  </PullToRefresh>;
}

