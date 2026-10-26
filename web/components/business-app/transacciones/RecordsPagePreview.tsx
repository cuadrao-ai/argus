"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Check, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import type { RecordRow } from "./transacciones-model";
import type { RecordsViewPreferences } from "./records-view-preferences";
import type { Density } from "./table-density";
import { RecordsNarrowList, RecordsTable } from "./TransaccionesRecords";
import { ToolbarPicker } from "./RecordsToolbar";
import { useTransaccionesWords } from "./transacciones-words";
import { DEFAULT_RECORDS_SORT, INITIAL_PAGINATION, RECORDS_SORT_OPTIONS, pageLinks, paginateRecords, type PaginationState, type RecordsSort } from "./records-pagination";
import styles from "./records-page.module.css";

/** Local loaded rows only. A hosted query/count contract replaces this preview later. */
export default function RecordsPagePreview({ records, density, resetKey, rowRef, emptyContent, preferences, onSortChange }: { preferences: RecordsViewPreferences; onSortChange: (sort: RecordsSort) => void; emptyContent?: ReactNode; records: readonly RecordRow[]; density: Density; resetKey: string; rowRef: (id: string, node: HTMLElement | null) => void }) {
  const { t, locale } = useTransaccionesWords();
  const word = (key: string) => t(`business.transactions.pagination.${key}`);
  const chosenSort = preferences.sort ?? DEFAULT_RECORDS_SORT;
  const scope = `${resetKey}:${chosenSort.key}:${chosenSort.direction}`;
  const noticeId = useId();
  const [attemptedAmount, setAttemptedAmount] = useState(false);
  const [state, setState] = useState<PaginationState & { scope: string }>({ ...INITIAL_PAGINATION, scope });
  // Query and sort changes reset the page, preserving page size.
  if (state.scope !== scope) setState({ ...state, page: 1, scope });
  const result = paginateRecords(records, state.scope === scope ? state : { ...state, page: 1 }, chosenSort, locale);
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
  const changePage = (page: number) => setState((current) => ({ ...current, page }));
  const sort = (next: RecordsSort) => {
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
        {(close) => <>{RECORDS_SORT_OPTIONS.map(({ key, direction, label }) => <button type="button" key={`${key}-${direction}`} className={styles.option} aria-disabled={key === "monto" && !result.amountSortAvailable || undefined} onClick={() => { sort({ key, direction }); close(); }}>{word(label)}{result.effectiveSort.key === key && result.effectiveSort.direction === direction ? <Check size={16} aria-hidden="true" /> : null}</button>)}{!result.amountSortAvailable ? <p className={styles.sortHelp}>{word("amount_requires_currency")}</p> : null}</>}
      </ToolbarPicker></div> : null}
      {result.count === 0 ? emptyContent : narrow ? <RecordsNarrowList records={result.items} rowRef={rowRef} /> : <RecordsTable preferences={preferences} records={result.items} density={density} rowRef={rowRef} sort={result.effectiveSort} onSortChange={sort} amountSortAvailable={result.amountSortAvailable} sortNoticeId={showNotice ? noticeId : undefined} />}
      <footer className={styles.footer} data-testid="records-pagination" data-page={result.page}>
        <span data-testid="records-count" className={styles.count} aria-live="polite">{label}</span>
        <ToolbarPicker flip label={word("page_size")} value={t("business.transactions.pagination.per_page", { count: state.pageSize })}>
          {(close) => <>{([25, 50, 100] as const).map((size) => <button type="button" key={size} className={styles.option} onClick={() => { setState((current) => ({ ...current, pageSize: size, page: 1 })); close(); }}>{t("business.transactions.pagination.per_page", { count: size })}{state.pageSize === size ? <Check size={16} aria-hidden="true" /> : null}</button>)}</>}
        </ToolbarPicker>
        <nav className={styles.pages} aria-label={word("label")}>
          <button type="button" aria-label={word("first")} disabled={result.page === 1} onClick={() => changePage(1)}><ChevronsLeft size={16} aria-hidden="true" /></button>
          <button type="button" aria-label={word("previous")} disabled={result.page === 1} onClick={() => changePage(result.page - 1)}><ChevronLeft size={16} aria-hidden="true" /></button>
          {pageLinks(result.page, result.pages).map((page, index) => page === "gap" ? <span key={`gap-${index}`} aria-hidden="true">…</span> : <button type="button" key={page} aria-label={t("business.transactions.pagination.page", { page })} aria-current={page === result.page ? "page" : undefined} onClick={() => changePage(page)}>{page}</button>)}
          <button type="button" aria-label={word("next")} disabled={result.page === result.pages} onClick={() => changePage(result.page + 1)}><ChevronRight size={16} aria-hidden="true" /></button>
          <button type="button" aria-label={word("last")} disabled={result.page === result.pages} onClick={() => changePage(result.pages)}><ChevronsRight size={16} aria-hidden="true" /></button>
        </nav>
      </footer>
    </div>
  </div>;
}
