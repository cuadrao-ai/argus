"use client";

import { Check, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ToolbarPicker } from "./RecordsToolbar";
import { RecordsLoadingBar } from "./RecordsLoadingPreview";
import { PAGE_SIZES, pageLinks, type PaginationState } from "./records-pagination";
import loadingStyles from "./records-loading-preview.module.css";
import styles from "./records-page.module.css";

/** `loading`: the first page is pending, so the count the server owns is a placeholder bar (shown after the screen's shared delay). A control shows only when it changes something: the page size once the records outgrow the smallest page, the pages once there is more than one. */
export default function RecordsPaginationControls({ count, page, pages, pageSize, rangeLabel, onPageChange, onPageSizeChange, label, pageSizeLabel, loading = false, shown = true }: { count: number; page: number; pages: number; pageSize: PaginationState["pageSize"]; rangeLabel: string; onPageChange: (page: number) => void; onPageSizeChange: (size: PaginationState["pageSize"]) => void; label?: string; pageSizeLabel?: string; loading?: boolean; shown?: boolean }) {
  const { t } = useTranslation();
  const word = (key: string) => t(`business.transactions.pagination.${key}`);
  const sizes = !loading && count > PAGE_SIZES[0];
  const arrows = !loading && pages > 1;
  return <div className={styles.container}><footer className={styles.footer} data-testid="records-pagination" data-surface-block="pagination" data-page={page} aria-busy={loading || undefined}>
    {loading ? <span className={styles.count} aria-hidden="true" style={shown ? undefined : { visibility: "hidden" }}><RecordsLoadingBar className={loadingStyles.count} /></span> : <span data-testid="records-count" className={styles.count} aria-live="polite">{rangeLabel}</span>}
    {sizes ? <ToolbarPicker flip label={pageSizeLabel ?? word("page_size")} value={t("business.transactions.pagination.per_page", { count: pageSize })}>
      {close => <>{PAGE_SIZES.map(size => <button type="button" key={size} className={styles.option} onClick={() => { onPageSizeChange(size); close(); }}>{t("business.transactions.pagination.per_page", { count: size })}{pageSize === size ? <Check size={16} aria-hidden="true" /> : null}</button>)}</>}
    </ToolbarPicker> : null}
    {arrows ? <nav className={styles.pages} aria-label={label ?? word("label")}>
      <button type="button" aria-label={word("first")} disabled={page === 1} onClick={() => onPageChange(1)}><ChevronsLeft size={16} aria-hidden="true" /></button>
      <button type="button" aria-label={word("previous")} disabled={page === 1} onClick={() => onPageChange(page - 1)}><ChevronLeft size={16} aria-hidden="true" /></button>
      {pageLinks(page, pages).map((value, index) => value === "gap" ? <span key={`gap-${index}`} aria-hidden="true">…</span> : <button type="button" key={value} aria-label={t("business.transactions.pagination.page", { page: value })} aria-current={value === page ? "page" : undefined} onClick={() => onPageChange(value)}>{value}</button>)}
      <button type="button" aria-label={word("next")} disabled={page === pages} onClick={() => onPageChange(page + 1)}><ChevronRight size={16} aria-hidden="true" /></button>
      <button type="button" aria-label={word("last")} disabled={page === pages} onClick={() => onPageChange(pages)}><ChevronsRight size={16} aria-hidden="true" /></button>
    </nav> : null}
  </footer></div>;
}
