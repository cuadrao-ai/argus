"use client";

import { FileCheck, FileSearch, Files } from "lucide-react";
import { CARD_FILTERS, type CardFilter, type ReviewFilter } from "./records-filter-preview-model";
import { useTransaccionesWords } from "./transacciones-words";
import { useDelayedPending } from "../business-skeletons";
import { RecordsLoadingBar } from "./RecordsLoadingPreview";
import { Unknown } from "./transacciones-parts";
import styles from "./records-overview-preview.module.css";

const ICONS: Record<CardFilter, typeof Files> = { fiscal: FileSearch, export: Files, exported: FileCheck };

/**
 * The three cards (Faltan datos fiscales, Listos para exportar, Ya exportados), each a count the
 * server answered and a line saying what it counts, and under them one quiet line to the Bandeja
 * when receipts wait there. `waiting` is the receipt activity count the sidebar shows; null is unknown.
 */
export default function RecordsOverviewPreview({ counts, selected, onChoose, loading = false, waiting, onOpenBandeja }: { loading?: boolean; counts: Record<CardFilter, number | null>; selected: readonly ReviewFilter[]; onChoose: (value: CardFilter) => void; waiting: number | null; onOpenBandeja: () => void }) {
  const { t } = useTransaccionesWords();
  const showSkeleton = useDelayedPending(loading);
  return <div data-testid="records-overview-preview" className={styles.overview}>
    <div className={styles.cards}>
      {CARD_FILTERS.map((key) => { const Icon = ICONS[key]; return <button type="button" key={key} data-overview-filter={key} aria-pressed={selected.includes(key)} disabled={counts[key] === null} onClick={() => onChoose(key)} className={`${styles.card} ${styles[key]}`}>
        <span className={styles.heading}><Icon size={21} strokeWidth={1.7} aria-hidden="true" /><span>{t(`business.transactions.layout.overview.${key}.title`)}</span></span>
        <span className={`${styles.count} font-display`}>{counts[key] ?? (loading ? <span aria-hidden="true" style={{ visibility: showSkeleton ? "visible" : "hidden" }}><RecordsLoadingBar overview /></span> : <Unknown />)}</span>
        <span className={styles.description} data-overview-description>{t(`business.transactions.layout.overview.${key}.description`)}</span>
      </button>; })}
    </div>
    {waiting ? <p className={styles.waiting} data-testid="records-bandeja-waiting"><button type="button" className={styles.waitingLink} onClick={onOpenBandeja}>{t("business.transactions.layout.overview.bandeja_waiting", { count: waiting })}</button></p> : null}
  </div>;
}
