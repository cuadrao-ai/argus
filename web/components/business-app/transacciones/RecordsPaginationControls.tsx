"use client";

import { Check, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ToolbarPicker } from "./RecordsToolbar";
import { pageLinks, type PaginationState } from "./records-pagination";
import styles from "./records-page.module.css";

export default function RecordsPaginationControls({ page, pages, pageSize, rangeLabel, onPageChange, onPageSizeChange, hideSinglePage = false, label, pageSizeLabel }: { page: number; pages: number; pageSize: PaginationState["pageSize"]; rangeLabel: string; onPageChange: (page: number) => void; onPageSizeChange: (size: PaginationState["pageSize"]) => void; hideSinglePage?: boolean; label?: string; pageSizeLabel?: string }) {
  const { t } = useTranslation();
  const word = (key: string) => t(`business.transactions.pagination.${key}`);
  return <div className={styles.container}><footer className={styles.footer} data-testid="records-pagination" data-page={page}>
    <span data-testid="records-count" className={styles.count} aria-live="polite">{rangeLabel}</span>
    <ToolbarPicker flip label={pageSizeLabel ?? word("page_size")} value={t("business.transactions.pagination.per_page", { count: pageSize })}>
      {close => <>{([25, 50, 100] as const).map(size => <button type="button" key={size} className={styles.option} onClick={() => { onPageSizeChange(size); close(); }}>{t("business.transactions.pagination.per_page", { count: size })}{pageSize === size ? <Check size={16} aria-hidden="true" /> : null}</button>)}</>}
    </ToolbarPicker>
    {!hideSinglePage || pages > 1 ? <nav className={styles.pages} aria-label={label ?? word("label")}>
      <button type="button" aria-label={word("first")} disabled={page === 1} onClick={() => onPageChange(1)}><ChevronsLeft size={16} aria-hidden="true" /></button>
      <button type="button" aria-label={word("previous")} disabled={page === 1} onClick={() => onPageChange(page - 1)}><ChevronLeft size={16} aria-hidden="true" /></button>
      {pageLinks(page, pages).map((value, index) => value === "gap" ? <span key={`gap-${index}`} aria-hidden="true">…</span> : <button type="button" key={value} aria-label={t("business.transactions.pagination.page", { page: value })} aria-current={value === page ? "page" : undefined} onClick={() => onPageChange(value)}>{value}</button>)}
      <button type="button" aria-label={word("next")} disabled={page === pages} onClick={() => onPageChange(page + 1)}><ChevronRight size={16} aria-hidden="true" /></button>
      <button type="button" aria-label={word("last")} disabled={page === pages} onClick={() => onPageChange(pages)}><ChevronsRight size={16} aria-hidden="true" /></button>
    </nav> : null}
  </footer></div>;
}
