"use client";

import { FileSearch, ListChecks, Files } from "lucide-react";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-overview-preview.module.css";

const CARDS = [
  { key: "review", count: 6, icon: FileSearch },
  { key: "approval", count: 2, icon: ListChecks },
  { key: "export", count: 12, icon: Files },
] as const;

export default function RecordsOverviewPreview() {
  const { t } = useTransaccionesWords();
  return (
    <dl data-testid="records-overview-preview" className={styles.cards}>
      {CARDS.map(({ key, count, icon: Icon }) => (
        <div key={key} className={`${styles.card} ${styles[key]}`}>
          <dt className={styles.heading}>
            <Icon size={21} strokeWidth={1.7} aria-hidden="true" />
            <span>{t(`business.transactions.layout.overview.${key}.title`)}</span>
          </dt>
          <dd className={`${styles.count} font-display`}>{count}</dd>
          <dd className={styles.description}>{t(`business.transactions.layout.overview.${key}.description`)}</dd>
        </div>
      ))}
    </dl>
  );
}
