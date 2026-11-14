"use client";

import BusinessListTabs from "../foundation/BusinessListTabs";
import GuideCard from "../foundation/GuideCard";

import { useEffect, useEffectEvent, useMemo, useRef, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";
import { resolveLanguage } from "@/lib/language-features";
import { supportEmail } from "@/lib/support-email";
import type { ReceiptSummary } from "@/lib/business-api";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { PullToRefresh } from "@/components/ui/PullToRefresh";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { useReceivingChannels } from "../business-context";
import { useBusiness } from "../BusinessWorkspace";
import ReceiptReadingControl from "../ReceiptReadingControl";
import { loadFailure, type LoadFailure } from "../bandeja-sources";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import ReceptionApprovalFailure from "./ReceptionApprovalFailure";
import ReceptionBulkBar from "./ReceptionBulkBar";
import { useListosApproval } from "./useListosApproval";
import type { ListoTarget } from "./reception-approval";
import ReceptionAddMenu from "./ReceptionAddMenu";
import { barSearchAvailable, useLendListSearch } from "../foundation/list-search";
import ReceptionFilters, { ReceptionFilterChips } from "./ReceptionFilters";
import { emptyReceptionFilters, receptionFilterMatches, receptionArrivedInPeriod, receptionSenderIdentity, type SenderIdentity, type ReceptionFiltersValue } from "./reception-filters";
import ReceptionEmptyState from "./ReceptionEmptyState";
import { canAddRecords, quietButtonClass } from "../business-ui";
import { listoItem, receptionDocumentTitle, receptionMatches, receptionRows, receptionSearchText, receptionTarget, rowDeleteTarget, type ReceptionRow, type ReceptionView } from "./reception-model";
import { bandejaAttentionCount, bandejaListoCount } from "../inbox-count";
import ReceptionArrivalRow from "./ReceptionArrivalRow";
import ReceptionDeletedRow, { DeletedColumns } from "./ReceptionDeletedRow";
import { useDeletedNotes } from "./useDeletedNotes";
import { useDocumentDelete } from "../DocumentDeleteControls";
import { useReceiptStateWord } from "../receipt-state-word";
import ReceptionSkeleton from "./ReceptionSkeleton";
import { ReceptionSearch, ReceptionSettings, defaultReceptionPreferences, statusColumnWord, type ReceptionPreferences } from "./ReceptionControls";
import { periodRange, type Period } from "../business-format";
import RecordsDatePreview from "../transacciones/RecordsDatePreview";
import RecordsPaginationControls from "../transacciones/RecordsPaginationControls";
import { INITIAL_PAGINATION, type PaginationState } from "../transacciones/records-pagination";
import { previewAmountColumnSize } from "../transacciones/records-row-preview";
import { RECORDS_PREVIEW_COLUMNS } from "../transacciones/records-view-preferences";
import { DENSITY_ROW_PX } from "../transacciones/table-density";
import { receptionGrid } from "./reception-grid";
import styles from "./reception.module.css";

const VIEWS: ReceptionView[] = ["all", "attention", "listos", "eliminados"];
/** Each tab's word, under `business.reception_preview`. */
const VIEW_WORD: Record<ReceptionView, string> = { all: "all", attention: "attention", listos: "placeholder.listos", eliminados: "eliminados" };
type ArrivalLoad = { scope: string; source: ReturnType<typeof useBusiness>["source"]; items: ReceiptSummary[]; failure: LoadFailure | null };


type ReturnPosition = { scope: string; view: ReceptionView; filters: ReceptionFiltersValue; query: string; page: number; pageSize: PaginationState["pageSize"]; period: Period; admittedIds: string[] | null; selectedIds: string[]; preferences: ReceptionPreferences };
// Only the immediate dossier return uses this in-memory snapshot. Reload never restores it.
const dossierReturns = new WeakMap<object, ReturnPosition>();

/** One screen: the source decides whether the rows are the server's or sample data, and nothing else differs. */
export default function ReceptionPreview() {
  const { chosen } = useBusiness();
  return <ReceptionWorkspace key={`${chosen?.space_id ?? "own"}:${chosen?.grant_id ?? chosen?.role ?? "unknown"}`} />;
}

function ReceptionWorkspace() {
  const { t, i18n } = useTranslation();
  const emailAvailable = useReceivingChannels().email.available;
  const locale = resolveLanguage({ device: i18n.resolvedLanguage ?? i18n.language });
  const word = (key: string) => t(`business.reception_preview.${key}`);
  const { source, userId, records, chosen, panel, openPanel, revision, refresh, reload, retrySources } = useBusiness();
  const { isBelowTablet: phone } = useResponsiveLayout();
  const scope = `${chosen?.space_id ?? "own"}:${chosen?.grant_id ?? chosen?.role ?? "unknown"}`;
  const [returnPosition] = useState(() => { const saved = dossierReturns.get(source); return saved?.scope === scope ? saved : undefined; });
  useEffect(() => { if (panel.kind === "inbox") dossierReturns.delete(source); }, [source, panel.kind]);
  const [loaded, setLoaded] = useState<ArrivalLoad | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [view, setView] = useState<ReceptionView>(returnPosition?.view ?? (panel.kind === "inbox" ? panel.view : undefined) ?? "all");
  useEffect(() => { if (panel.kind === "inbox" && panel.view === "eliminados") setView("eliminados"); }, [panel]);
  const stateWord = useReceiptStateWord();
  const [deleting, setDeleting] = useState<ReceptionRow | null>(null);
  const deletedNotes = useDeletedNotes(view === "eliminados");
  const deletion = useDocumentDelete(deleting && deleting.kind !== "email" ? rowDeleteTarget(deleting, deleting.kind === "receipt" ? stateWord(deleting.receipt) : t("business.document_delete.previous.attention"), t("business.document_delete.unnamed")) : null, {
    onClose: () => setDeleting(null),
    onView: () => { if (deleting) { const target = receptionTarget(deleting); if (target.kind === "receipt" || target.kind === "draft") navigateFrom({ ...target, confirmDelete: true }); } setDeleting(null); },
  });
  const [filters, setFilters] = useState(() => returnPosition?.filters ?? emptyReceptionFilters());
  const [page, setPage] = useState(returnPosition?.page ?? 1);
  const [pageSize, setPageSize] = useState<PaginationState["pageSize"]>(returnPosition?.pageSize ?? INITIAL_PAGINATION.pageSize);
  const [period, setPeriod] = useState<Period>(() => returnPosition?.period ?? periodRange("all"));
  const [admittedIds, setAdmittedIds] = useState<string[] | null>(returnPosition?.admittedIds ?? null);
  useEffect(() => {
    const notes = deletedNotes.items;
    if (!notes) return;
    setAdmittedIds(current => current === null ? current : [...new Set([...current, ...notes.map(note => `note:${note.draft_id}`)])]);
  }, [deletedNotes.items]);
  const [selectedIds, setSelectedIds] = useState<string[]>(returnPosition?.selectedIds ?? []);
  const list = useRef<HTMLDivElement>(null);
  const chooseTab = (next: ReceptionView) => { setView(next); setSelectedIds([]); setPage(1); };
  const applyFilters = (next: ReceptionFiltersValue) => { setFilters(next); setSelectedIds([]); setPage(1); };
  const [query, setQuery] = useState(returnPosition?.query ?? "");
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
  const arrivalsDown = !!arrivals?.failure && !arrivals.failure.refused;
  const sourcesDown = (["notes", "emails"] as const).filter(key => { const failure = key === "notes" ? records.notesFailure : records.emailsFailure; return failure && !failure.refused; });
  const askAgain = useEffectEvent(() => { if (arrivalsDown) setAttempt(value => value + 1); if (sourcesDown.length) retrySources(sourcesDown); });
  const askArrivalsAgain = useEffectEvent(() => { if (arrivalsDown) setAttempt(value => value + 1); });
  // A healthy list re-reads only when its content changed; a failed one asks again on the next poll tick and when the connection returns.
  useEffect(() => { askArrivalsAgain(); }, [records.inbox]);
  useEffect(() => {
    window.addEventListener("online", askAgain);
    return () => window.removeEventListener("online", askAgain);
  }, []);
  const pending = !arrivals || records.notes === null || records.emails === null || (view === "eliminados" && deletedNotes.items === null);
  const failed = !!arrivals?.failure || records.error || !!records.notesFailure || !!records.emailsFailure || (view === "eliminados" && !!deletedNotes.failure);
  const refused = records.refused || arrivals?.failure?.refused;
  const reference = deletedNotes.failure?.reference ?? arrivals?.failure?.reference ?? records.notesFailure?.reference ?? records.emailsFailure?.reference ?? null;
  const retryableSources = (["notes", "emails"] as const).filter(key => {
    const failure = key === "notes" ? records.notesFailure : records.emailsFailure;
    return failure && !failure.refused && !failure.offline;
  });
  const retryableArrivals = arrivals?.failure && !arrivals.failure.refused && !arrivals.failure.offline;
  const canRetry = !refused && (retryableArrivals || records.error || retryableSources.length > 0 || !!deletedNotes.failure);
  const onlySourcesFailed = !arrivals?.failure && !records.error && !refused && (!!records.notesFailure || !!records.emailsFailure);
  const sourcesLine = records.notesFailure && records.emailsFailure ? "failed_notes_emails" : records.notesFailure ? "failed_notes" : "failed_emails";
  const refusedForGood = !canRetry && (refused || !!records.notesFailure?.refused || !!records.emailsFailure?.refused);
  const latestRows = refused ? [] : receptionRows(arrivals?.items ?? [], [...(records.notes ?? []), ...(deletedNotes.items ?? [])], records.emails ?? []);
  const latestIds = latestRows.map(row => `${row.kind}:${row.id}`);
  const admissionKey = latestIds.join("|");
  useEffect(() => {
    if (!pending && !failed && admittedIds === null) {
      setAdmittedIds(admissionKey ? admissionKey.split("|") : []);
    }
  }, [pending, failed, admittedIds, admissionKey]);
  const byId = new Map(latestRows.map(row => [`${row.kind}:${row.id}`, row]));
  const rows = (admittedIds ?? latestIds).map(id => byId.get(id)).filter((row): row is ReceptionRow => !!row);
  const newCount = admittedIds ? latestIds.filter(id => !admittedIds.includes(id)).length : 0;
  const senders = [...new Map(rows.map(receptionSenderIdentity).filter((value): value is SenderIdentity => !!value).map(sender => [sender.id, sender])).values()].sort((a, b) => (a.name || a.address).localeCompare(b.name || b.address, locale));
  const queryText = query.trim().toLocaleLowerCase(locale);
  const matched = rows.filter(row => receptionMatches(row, view) && receptionFilterMatches(row, filters) && receptionArrivedInPeriod(row, period) && (!queryText || receptionSearchText(row).toLocaleLowerCase(locale).includes(queryText)));
  const pages = Math.max(1, Math.ceil(matched.length / pageSize));
  const currentPage = Math.min(page, pages);
  const shown = matched.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const amountSize = previewAmountColumnSize(matched.flatMap(row => row.kind === "receipt" && row.receipt.amount != null && row.receipt.currency ? [{ amount: row.receipt.amount, currency: row.receipt.currency }] : []), locale);
  // The boxes live on Listos, for owners; Estado says nothing there, since every row on the tab is the same.
  const selectable = view === "listos" && chosen?.capabilities.includes("approve") === true;
  const showStatus = view !== "listos";
  const navigateFrom = (next: Parameters<typeof openPanel>[0]) => {
    dossierReturns.set(source, { scope, view, filters, query, page: currentPage, pageSize, period, admittedIds, selectedIds, preferences });
    openPanel(next.kind === "receipt" || next.kind === "draft"
      ? { ...next, receiptIds: matched.flatMap(row => row.kind === "receipt" ? [row.id] : []) }
      : next);
  };
  const rowKey = (row: ReceptionRow) => `${row.kind}:${row.id}`;
  const titleOf = (row: ReceptionRow) => receptionDocumentTitle(row, { untitled: t("business.receipt.untitled"), pending: word("intake_pending"), exception: word("intake_exception"), text: word("text_intake") });
  const target = (row: ReceptionRow): ListoTarget[] => { const item = listoItem(row); return item ? [{ ...item, rowId: rowKey(row), title: titleOf(row) }] : []; };
  // A row that stops being Listos leaves the count and comes back if it returns; a poll never touches `selectedIds`.
  const selected = selectable ? rows.filter(row => selectedIds.includes(rowKey(row))).flatMap(target) : [];
  const pageListos = selectable ? shown.flatMap(target) : [];
  const allListos = selectable ? matched.flatMap(target) : [];
  const allSelected = pageListos.length > 0 && pageListos.every(row => selectedIds.includes(row.rowId));
  const approval = useListosApproval({
    send: source.approveListos,
    reload,
    select: setSelectedIds,
    settled: () => requestAnimationFrame(() => list.current?.focus({ preventScroll: true })),
  });
  const counts = { attention: bandejaAttentionCount(records), listos: bandejaListoCount(records), eliminados: records.receiptActivity?.bandeja_eliminados_count };
  const unseenIds = new Set(rows.filter(row => row.kind === "receipt" && row.receipt.activity?.unread === true && row.receipt.bandeja?.leyendo !== true).map(rowKey));
  const reviewNext = canAddRecords(chosen) && !chosen?.capabilities.includes("approve") ? rows.find(row => row.kind === "receipt" && row.receipt.bandeja?.por_revisar === true) : undefined;
  const inPanel = phone || panel.kind !== "inbox";
  const retry = () => {
    if (deletedNotes.failure) deletedNotes.retry();
    if (retryableArrivals) setAttempt(value => value + 1);
    if (records.error && !records.refused) reload();
    if (retryableSources.length) retrySources(retryableSources);
  };
  const clear = () => { applyFilters(emptyReceptionFilters()); setQuery(""); setPeriod(periodRange("all")); };
  const narrowed = !!queryText || period.key !== "all" || filters.channels.length > 0 || filters.senders.length > 0;
  const tabEmpty = view === "all" ? null : view;
  const empty = narrowed ? { kind: "filtered" as const, title: word("empty"), body: word("empty_help"), action: { label: word("clear"), run: clear } }
    : view === "eliminados" ? { kind: "done" as const, title: t("business.document_delete.empty_title"), body: t("business.document_delete.empty_body") }
    : tabEmpty ? { kind: "done" as const, title: word(`placeholder.empty_${tabEmpty}`), body: word(`placeholder.empty_${tabEmpty}_help`), action: { label: t("business.inbox.see_all"), run: () => chooseTab("all") } }
    : { kind: "first_run" as const, title: word("empty_start"), body: word(emailAvailable ? "empty_start_help" : "placeholder.empty_start_upload_help") };
  const searchQuery = (next: string) => { setSelectedIds([]); setPage(1); setQuery(next); };
  // A wide screen keeps Agregar in the top bar; with the bar's search on, it also searches from there, scoped to
  // Bandeja, through the query this list lends. A phone keeps both.
  const barTools = !phone;
  const searchInBar = barTools && barSearchAvailable;
  const guide = (key: string) => t(`business.guide_cards.bandeja_intro.${key}`);
  useLendListSearch("inbox", searchInBar ? { query, setQuery: searchQuery } : null);
  return <PullToRefresh onRefresh={refresh}>
    <section className={styles.workspace} aria-label={t("business.inbox.title")} data-testid="reception-preview" data-selectable={selectable} data-status={showStatus} data-density={preferences.density} data-source={preferences.source || preferences.sender} data-arrival={preferences.arrival} style={{ ...receptionGrid(preferences, { select: selectable, status: showStatus }, amountSize.width, RECORDS_PREVIEW_COLUMNS.find(column => column.key === "moneda")!.width!), "--row-height": `${DENSITY_ROW_PX[preferences.density]}px` } as CSSProperties}>
      {inPanel ? <div className={styles.phoneHeading}><h2 className="font-display">{t("business.inbox.title")}</h2></div> : null}
      {source.mode === "live" && userId && chosen ? (
        <GuideCard cardId="bandeja-intro" userId={userId} title={guide("title")}
          points={[
            { label: guide("upload.label"), body: guide("upload.body") },
            { label: guide("review.label"), body: guide("review.body") },
            { label: guide("pending.label"), body: guide("pending.body") },
          ]}
        />
      ) : null}
      <div className={styles.topline}>
        <BusinessListTabs label={word("views")} idPrefix="reception-tab" controls="reception-list" value={view} onChange={chooseTab} items={VIEWS.map(value => ({ value, label: <>{word(VIEW_WORD[value])}{value !== "all" ? <span className={styles.count} data-testid={`reception-count-${value}`}>{pending || failed ? "-" : counts[value] ?? "-"}</span> : null}</> }))} />
      </div>
      <div className={styles.toolbar} data-selecting={selected.length > 0}>
        {searchInBar ? null : <ReceptionSearch value={query} onChange={searchQuery} />}
        <div role="group" aria-label={word("arrival_date")}><RecordsDatePreview period={period} value={period} title={word("arrival_date")} onChange={next => { setSelectedIds([]); setPage(1); setPeriod(next); }} /></div>
        <ReceptionFilters key={scope} senders={senders} value={filters} onChange={applyFilters} />
        <div className={styles.bulkSlot}>{selected.length ? <ReceptionBulkBar count={selected.length} approve={() => approval.ask(selected)} clear={() => setSelectedIds([])} /> : null}</div>
        {(query && !searchInBar) || period.key !== "all" ? <button className={quietButtonClass} onClick={clear}>{word("clear")}</button> : null}
        <div className={styles.tools}>{reviewNext ? <button type="button" data-testid="business-primary-review" className={`${styles.quietAction} rounded-full`} onClick={() => navigateFrom({ kind: "receipt", receiptId: reviewNext.id, list: "inbox" })}>{t("business.inbox.review_receipts")}</button> : null}{allListos.length && !selected.length ? <button type="button" data-testid="reception-approve-all" className={`${styles.quietAction} rounded-full`} onClick={() => approval.ask(allListos)}><Check size={16} aria-hidden="true" />{word("placeholder.approve_all")}</button> : null}<ReceptionAddMenu key={scope} addInBar={barTools} /><ReceptionSettings value={preferences} view={view} onChange={setPreferences} /></div>
      </div>
      {newCount > 0 ? <div className={styles.updateNotice} role="status"><span>{t("business.reception_preview.new_arrivals", { count: newCount })}</span><button type="button" className={quietButtonClass} onClick={() => { setAdmittedIds(latestIds); setPage(1); }}>{word("update_list")}</button></div> : null}
      <ReceptionFilterChips value={filters} senders={senders} onChange={applyFilters} />
      {view === "eliminados" ? <p className="text-[14px] text-[#56635e] dark:text-white/70">{t("business.document_delete.list_help")}</p> : <ReceiptReadingControl />}
      {approval.failed.length ? <ReceptionApprovalFailure failed={approval.failed} attempted={approval.attempted} onRetry={approval.retry} onDismiss={approval.dismiss} /> : null}
      {failed ? <div className={styles.error} role="alert"><p>{refused ? t("auth.business_unavailable.title") : onlySourcesFailed ? t(`business.inbox.${sourcesLine}`) : word("error")}{refusedForGood ? <> {t("auth.business_unavailable.body", { supportEmail })}</> : null}{reference ? <span className="ml-2 inline-flex align-middle"><ReferenceCode reference={reference} /></span> : null}</p>{canRetry ? <button className={quietButtonClass} onClick={retry}>{t("common.retry")}</button> : null}</div> : null}
      <div ref={list} id="reception-list" role="tabpanel" aria-labelledby={`reception-tab-${view}`} tabIndex={0} className={styles.list}>
        {view === "eliminados" ? <DeletedColumns /> : <div className={styles.columns}>{!selectable ? null : pageListos.length ? <label className={styles.checkbox}><input type="checkbox" checked={allSelected} aria-label={word("select_page")} ref={node => { if (node) node.indeterminate = selected.length > 0 && !allSelected; }} onChange={() => setSelectedIds(allSelected ? [] : pageListos.map(row => row.rowId))} /></label> : <span className={styles.checkbox} />}<span className={styles.contentHeading}>{word("document")}</span><span>{word("file")}</span>{preferences.source ? <span className={styles.channelHeading}>{word("source")}</span> : null}{preferences.sender ? <span className={styles.senderHeading}>{word("sender")}</span> : null}{preferences.source || preferences.sender ? <span className={styles.combinedHeading}>{word(preferences.source && preferences.sender ? "sender_source" : preferences.source ? "source" : "sender")}</span> : null}{preferences.amount ? <span className={styles.amountHeading}>{word("amount")}</span> : null}{preferences.currency ? <span className={styles.currencyHeading}>{t("business.transactions.columns.moneda")}</span> : null}{showStatus ? <span>{word(statusColumnWord(view))}</span> : null}{preferences.arrival ? <span>{word("arrival")}</span> : null}<span className="sr-only">{word("next_action")}</span></div>}
        {pending && !failed ? <ReceptionSkeleton preferences={preferences} selectable={selectable} status={showStatus} /> : <ul aria-label={word("list_label")}>
          {shown.map(row => view === "eliminados" ? <ReceptionDeletedRow key={`${row.kind}-${row.id}`} row={row} title={titleOf(row)} openPanel={navigateFrom} /> : <ReceptionArrivalRow key={`${row.kind}-${row.id}`} row={row} view={view} onDelete={(row.kind === "receipt" ? row.receipt.bandeja_group?.group === "attention" && row.receipt.delete_available : row.kind === "note" && row.note.bandeja_group?.group === "attention" && row.note.delete_available) && chosen?.capabilities.includes("approve") && source.deleteDocument ? () => { setDeleting(row); deletion.ask(); } : undefined} panel={panel} openPanel={navigateFrom} preferences={preferences} selectable={selectable} checkable={selectable && listoItem(row) !== null} checked={selectedIds.includes(rowKey(row))} unseen={unseenIds.has(rowKey(row))} onCheck={() => setSelectedIds(current => current.includes(rowKey(row)) ? current.filter(id => id !== rowKey(row)) : [...current, rowKey(row)])} />)}
        </ul>}
        {!pending && !failed && !shown.length ? <ReceptionEmptyState {...empty} /> : null}
      </div>
      {!pending && !failed ? <RecordsPaginationControls page={currentPage} pages={pages} pageSize={pageSize} rangeLabel={t("business.reception_preview.document_range", { from: matched.length ? (currentPage - 1) * pageSize + 1 : 0, to: Math.min(currentPage * pageSize, matched.length), count: matched.length })} label={word("pagination")} pageSizeLabel={word("page_size")} onPageChange={next => { setSelectedIds([]); setPage(next); }} onPageSizeChange={size => { setSelectedIds([]); setPageSize(size); setPage(1); }} /> : null}
      {(view !== "eliminados" && records.notesTruncated) ? <p className={styles.historyNote}>{t("business.inbox.notes_latest")}</p> : null}
      {deletion.dialog}
      <ConfirmDialog isOpen={approval.asking !== null} tone="primary" isBusy={approval.busy} title={t("business.reception_preview.placeholder.approve_confirm", { count: approval.asking?.length ?? 0 })} description={t("business.reception_preview.placeholder.approve_confirm_help", { count: approval.asking?.length ?? 0 })} confirmLabel={t("business.dossier.approve_action")} cancelLabel={t("common.cancel")} onCancel={approval.cancel} onConfirm={approval.confirm} />
    </section>
  </PullToRefresh>;
}

