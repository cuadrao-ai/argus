"use client";

import { useDelayedPending } from "../business-skeletons";
import skeleton from "../business-skeletons.module.css";
import { COLUMNS, CELL, PIN_CLASS } from "./TransaccionesTable";
import { recordsColumnLabelKey, recordsMinimumWidth, visibleRecordsColumns, type RecordsViewPreferences } from "./records-view-preferences";
import { DENSITY_ROW_PX, type Density } from "./table-density";
import { useTransaccionesWords } from "./transacciones-words";
import page from "./records-page.module.css";
import styles from "./records-loading-preview.module.css";

const ROWS = Array.from({ length: 8 }, (_, index) => index);

export function RecordsLoadingBar({ className = "", overview = false }: { className?: string; overview?: boolean }) {
  return <span className={`${skeleton.block} ${skeleton.shimmer} ${styles.bar} ${overview ? styles.overview : ""} ${className}`} />;
}

/** Pending slots follow the same column owner and narrow container as the loaded ledger. */
export default function RecordsLoadingPreview({ density, preferences }: { density: Density; preferences?: RecordsViewPreferences }) {
  const { t } = useTransaccionesWords();
  const visible = useDelayedPending(true);
  const columns = preferences ? visibleRecordsColumns(preferences) : COLUMNS;
  return <div className={page.container} role="status" aria-label={t("common.loading")} data-testid="transacciones-loading">
    <div aria-hidden="true" className={visible ? undefined : styles.waiting}>
      <div className={styles.table}>
        <div className="argus-thin-scrollbar relative max-h-[calc(100dvh-15rem)] min-h-[16rem] overflow-auto rounded-surface border border-[#DCE0DA] bg-white dark:border-white/10 dark:bg-[#1f2225]">
          <table data-density={density} style={{ minWidth: recordsMinimumWidth(columns, { units: 0, width: "104px" }) }} className="w-full table-fixed border-separate border-spacing-0 text-[14px]">
            <colgroup>{columns.map((column) => <col key={column.key} style={{ width: column.width ?? undefined }} />)}</colgroup>
            <thead><tr>{columns.map((column) => <th key={column.key} scope="col" data-col={column.key} data-pinned={column.pin ? `top ${column.pin}` : "top"} className={`sticky top-0 z-20 h-11 border-b border-[#DCE0DA] bg-white px-3 text-[13px] font-normal text-[#56635e] dark:border-white/10 dark:bg-[#1f2225] dark:text-white/65 ${column.align === "right" ? "text-right" : "text-left"} ${column.pin ? `${PIN_CLASS[column.pin]} z-30` : ""}`}>{t(recordsColumnLabelKey(column.key), { currency: "" }).trim()}</th>)}</tr></thead>
            <tbody>{ROWS.map((row) => <tr key={row} style={{ height: DENSITY_ROW_PX[density] }}>{columns.map((column) => <td key={column.key} data-col={column.key} data-pinned={column.pin} className={`${CELL} ${column.pin ? PIN_CLASS[column.pin] : ""}`}><RecordsLoadingBar className={`${styles[column.key]} ${column.align === "right" ? styles.right : ""}`} /></td>)}</tr>)}</tbody>
          </table>
        </div>
      </div>
      <div className={styles.narrow}>
        {preferences ? <div className={page.sort}><RecordsLoadingBar className={styles.sort} /></div> : null}
        <ul className={page.list}>{ROWS.map((row) => <li key={row} className={page.narrowRecord}><div className={page.row}>
          <span className={page.top}><RecordsLoadingBar className={styles.contraparte} /><RecordsLoadingBar className={`${styles.monto} ${styles.right}`} /></span>
          <span className={page.meta}><span className={page.marks}><RecordsLoadingBar className={styles.detalle} /><RecordsLoadingBar className={styles.estado} /></span><RecordsLoadingBar className={`${styles.fecha} ${styles.right}`} /></span>
        </div><span className={styles.actions}><RecordsLoadingBar className={styles.action} /><RecordsLoadingBar className={styles.action} /></span></li>)}</ul>
      </div>
      {preferences ? <footer className={page.footer} data-testid="records-loading-pagination"><RecordsLoadingBar className={styles.count} /><RecordsLoadingBar className={styles.pageSize} /><span className={page.pages}>{Array.from({ length: 5 }, (_, index) => <span key={index} className={styles.pageSlot}><RecordsLoadingBar className={styles.action} /></span>)}</span></footer> : null}
    </div>
  </div>;
}
