"use client";

import { FileSearch, ListChecks, Files } from "lucide-react";
import type { ReviewFilter } from "./records-filter-preview-model";
import { useTransaccionesWords } from "./transacciones-words";
import { Unknown } from "./transacciones-parts";
import styles from "./records-overview-preview.module.css";

const CARDS = [{ key: "review", icon: FileSearch }, { key: "approval", icon: ListChecks }, { key: "export", icon: Files }] as const;

export default function RecordsOverviewPreview({ counts, selected, onChoose }: { counts: Record<ReviewFilter, number | null>; selected: readonly ReviewFilter[]; onChoose: (value: ReviewFilter) => void }) {
  const { t } = useTransaccionesWords();
  return <div data-testid="records-overview-preview" className={styles.cards}>
    {CARDS.map(({ key, icon: Icon }) => <button type="button" key={key} data-overview-filter={key} aria-pressed={selected.includes(key)} disabled={counts[key] === null} onClick={() => onChoose(key)} className={`${styles.card} ${styles[key]}`}>
      <span className={styles.heading}><Icon size={21} strokeWidth={1.7} aria-hidden="true" /><span>{t(`business.transactions.layout.overview.${key}.title`)}</span></span>
      <span className={`${styles.count} font-display`}>{counts[key] ?? <Unknown />}</span>
      <span className={styles.description}>{t(`business.transactions.layout.overview.${key}.description`)}</span>
    </button>)}
  </div>;
}
