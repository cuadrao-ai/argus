"use client";

import { useDelayedPending } from "../business-skeletons";
import skeleton from "../business-skeletons.module.css";
import { CELL, PIN_CLASS, RECORDS_TITLE } from "./TransaccionesTable";
import { recordsMinimumWidth, visibleRecordsColumns, type RecordsViewPreferences } from "./records-view-preferences";
import { DEFAULT_DENSITY, DENSITY_ROW_PX, type Density } from "./table-density";
import { useTransaccionesWords } from "./transacciones-words";
import page from "./records-page.module.css";
import styles from "./records-loading-preview.module.css";

const ROWS = Array.from({ length: 8 }, (_, index) => index);
/** Unnamed slots stand in for the columns until the server's saved view names them. */
const SLOTS = Array.from({ length: 7 }, (_, index) => index);

export function RecordsLoadingBar({ className = "", overview = false }: { className?: string; overview?: boolean }) {
  return <span className={`${skeleton.block} ${skeleton.shimmer} ${styles.bar} ${overview ? styles.overview : ""} ${className}`} />;
}

/** Pending slots follow the same column owner and narrow container as the loaded ledger. `shown` lets the screen carry one wait across its parts. */
export default function RecordsLoadingPreview({ density = DEFAULT_DENSITY, preferences, shown }: { density?: Density; preferences?: RecordsViewPreferences; shown?: boolean }) {
  const { t } = useTransaccionesWords();
  const delayed = useDelayedPending(true);
  const visible = shown ?? delayed;
  const columns = preferences ? visibleRecordsColumns(preferences) : null;
  return <div className={page.container} role="status" aria-label={t("common.loading")} data-testid="transacciones-loading" data-surface-block="table">
    <div aria-hidden="true" className={visible ? undefined : styles.waiting}>
      <div className={styles.table}>
        <div className="argus-thin-scrollbar relative max-h-[calc(100dvh-15rem)] min-h-[16rem] overflow-auto rounded-surface border border-[#DCE0DA] bg-white dark:border-white/10 dark:bg-[#1f2225]">
          <table data-density={density} style={columns ? { minWidth: recordsMinimumWidth(columns, { units: 0, width: "104px" }) } : undefined} className="w-full table-fixed border-separate border-spacing-0 text-[14px]">
            {columns ? <colgroup>{columns.map((column) => <col key={column.key} style={{ width: column.width ?? undefined }} />)}</colgroup> : null}
            <thead><tr>{columns ? columns.map((column) => <th key={column.key} scope="col" data-col={column.key} data-pinned={column.pin ? `top ${column.pin}` : "top"} className={`${RECORDS_TITLE} z-20 ${column.align === "right" ? "text-right" : "text-left"} ${column.pin ? `${PIN_CLASS[column.pin]} z-30` : ""}`}>{t(column.label_key, { currency: "" }).trim()}</th>) : SLOTS.map((slot) => <th key={slot} scope="col" data-pinned="top" className={`${RECORDS_TITLE} z-20 text-left`}><RecordsLoadingBar className={styles.heading} /></th>)}</tr></thead>
            <tbody>{ROWS.map((row) => <tr key={row} style={{ height: DENSITY_ROW_PX[density] }}>{columns ? columns.map((column) => <td key={column.key} data-col={column.key} data-pinned={column.pin} className={`${CELL} ${column.pin ? PIN_CLASS[column.pin] : ""}`}><RecordsLoadingBar className={`${styles[column.key]} ${column.align === "right" ? styles.right : ""}`} /></td>) : SLOTS.map((slot) => <td key={slot} className={CELL}><RecordsLoadingBar className={styles.slot} /></td>)}</tr>)}</tbody>
          </table>
        </div>
      </div>
      <div className={styles.narrow}>
        {preferences ? <div className={page.sort}><RecordsLoadingBar className={styles.sort} /></div> : null}
        <ul className={page.list}>{ROWS.map((row) => <li key={row} className={page.narrowRecord}><div className={page.row}>
          <span className={page.top}><RecordsLoadingBar className={styles.counterparty} /><RecordsLoadingBar className={`${styles.gross_amount} ${styles.right}`} /></span>
          <span className={page.meta}><span className={page.marks}><RecordsLoadingBar className={styles.detail} /><RecordsLoadingBar className={styles.stage} /></span><RecordsLoadingBar className={`${styles.date} ${styles.right}`} /></span>
        </div><span className={styles.actions}><RecordsLoadingBar className={styles.action} /><RecordsLoadingBar className={styles.action} /></span></li>)}</ul>
      </div>
      {preferences ? <footer className={page.footer} data-testid="records-loading-pagination"><RecordsLoadingBar className={styles.count} /><RecordsLoadingBar className={styles.pageSize} /><span className={page.pages}>{Array.from({ length: 5 }, (_, index) => <span key={index} className={styles.pageSlot}><RecordsLoadingBar className={styles.action} /></span>)}</span></footer> : null}
    </div>
  </div>;
}
