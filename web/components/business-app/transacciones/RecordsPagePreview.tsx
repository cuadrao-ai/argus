"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Check } from "lucide-react";
import { reportSortToRecords } from "@/lib/business-reporting-wire";
import type { ReportAnswer, ReportRequest } from "@/lib/business-reports-api";
import type { RecordRow } from "./transacciones-model";
import type { RecordsViewPreferences } from "./records-view-preferences";
import type { Density } from "./table-density";
import { RecordsNarrowList, RecordsTable } from "./TransaccionesRecords";
import { ToolbarPicker } from "./RecordsToolbar";
import { useTransaccionesWords } from "./transacciones-words";
import { DEFAULT_RECORDS_SORT, INITIAL_PAGINATION, RECORDS_SORT_OPTIONS, paginateRecords, type PaginationState, type RecordsSort } from "./records-pagination";
import RecordsPaginationControls from "./RecordsPaginationControls";
import styles from "./records-page.module.css";

/** Preview and server pages share the same table and footer. */
export default function RecordsPagePreview({ records, density, resetKey, rowRef, emptyContent, preferences, onSortChange, connected }: { connected?: { answer: ReportAnswer; onPage: (page: number) => void; onPageSize: (size: ReportRequest["page_size"]) => void; onSort?: (sort: RecordsSort) => void }; preferences: RecordsViewPreferences; onSortChange: (sort: RecordsSort) => void; emptyContent?: ReactNode; records: readonly RecordRow[]; density: Density; resetKey: string; rowRef: (id: string, node: HTMLElement | null) => void }) {
  const { t, locale } = useTransaccionesWords();
  const word = (key: string) => t(`business.transactions.pagination.${key}`);
  const chosenSort = preferences.sort ?? DEFAULT_RECORDS_SORT;
  const scope = `${resetKey}:${chosenSort.key}:${chosenSort.direction}`;
  const noticeId = useId();
  const [attemptedAmount, setAttemptedAmount] = useState(false);
  const [state, setState] = useState<PaginationState & { scope: string }>({ ...INITIAL_PAGINATION, scope });
  // Query and sort changes reset the page, preserving page size.
  if (state.scope !== scope) setState({ ...state, page: 1, scope });
  const result = connected ? { count: connected.answer.matching_count, pages: Math.max(1, connected.answer.page_count), page: connected.answer.page, effectiveSort: reportSortToRecords(connected.answer.effective_sort ?? "date_desc"), amountSortAvailable: Boolean(connected.onSort), amountSortBlocked: connected.answer.sort_unavailable_reason === "amount_sort_requires_single_known_currency", from: connected.answer.matching_count ? (connected.answer.page - 1) * connected.answer.page_size + 1 : 0, to: Math.min(connected.answer.page * connected.answer.page_size, connected.answer.matching_count), items: records } : paginateRecords(records, state.scope === scope ? state : { ...state, page: 1 }, chosenSort, locale);
  const container = useRef<HTMLDivElement>(null);
  const surface = useRef<HTMLDivElement>(null);
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const node = container.current;
    const read = () => { if (surface.current) setNarrow(getComputedStyle(surface.current).getPropertyValue("--records-narrow").trim() === "1"); };
    read();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(read);
    if (node) observer?.observe(node);
    window.addEventListener("resize", read);
    return () => { observer?.disconnect(); window.removeEventListener("resize", read); };
  }, []);
  useEffect(() => { if (state.page !== result.page) setState((current) => ({ ...current, page: result.page })); }, [state.page, result.page]);
  const changePage = (page: number) => { if (connected) connected.onPage(page); else setState((current) => ({ ...current, page })); };
  const sort = (next: RecordsSort) => {
    if (connected) { connected.onSort?.(next); return; }
    if (next.key === "monto" && !result.amountSortAvailable) { setAttemptedAmount(true); return; }
    setAttemptedAmount(false);
    onSortChange(next);
  };
  const selected = RECORDS_SORT_OPTIONS.find(({ key, direction }) => key === result.effectiveSort.key && direction === result.effectiveSort.direction)!;
  const showNotice = result.amountSortBlocked || attemptedAmount && !result.amountSortAvailable;
  const label = t("business.transactions.pagination.range", { from: result.from, to: result.to, count: result.count });
  return <div ref={container} className={styles.container} data-testid="records-page-preview">
    <div ref={surface} className={styles.surface}>
      {showNotice ? <p id={noticeId} className={styles.sortNotice} role="status">{word(result.amountSortBlocked ? "amount_fallback" : "amount_requires_currency")}</p> : null}
      {narrow ? <div className={styles.sort}><ToolbarPicker label={word("sort")} value={word(selected.label)}>
        {(close) => <>{RECORDS_SORT_OPTIONS.map(({ key, direction, label }) => <button type="button" key={`${key}-${direction}`} className={styles.option} disabled={connected !== undefined && !connected.onSort && (key !== "fecha" || direction !== "desc")} aria-disabled={key === "monto" && !result.amountSortAvailable || undefined} onClick={() => { sort({ key, direction }); close(); }}>{word(label)}{result.effectiveSort.key === key && result.effectiveSort.direction === direction ? <Check size={16} aria-hidden="true" /> : null}</button>)}{!result.amountSortAvailable ? <p className={styles.sortHelp}>{word("amount_requires_currency")}</p> : null}</>}
      </ToolbarPicker></div> : null}
      {result.count === 0 ? emptyContent : narrow ? <RecordsNarrowList records={result.items} rowRef={rowRef} /> : <RecordsTable preferences={preferences} records={result.items} density={density} rowRef={rowRef} sort={result.effectiveSort} onSortChange={sort} amountSortAvailable={result.amountSortAvailable} sortNoticeId={showNotice ? noticeId : undefined} serverSorted={connected !== undefined && !connected.onSort} />}
      <RecordsPaginationControls page={result.page} pages={result.pages} pageSize={connected?.answer.page_size ?? state.pageSize} rangeLabel={label} onPageChange={changePage} onPageSizeChange={(pageSize) => { if (connected) connected.onPageSize(pageSize); else setState((current) => ({ ...current, pageSize, page: 1 })); }} />
    </div>
  </div>;
}
