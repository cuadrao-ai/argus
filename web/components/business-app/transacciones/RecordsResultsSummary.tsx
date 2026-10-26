"use client";

import { ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { PlainAmount } from "./transacciones-parts";
import type { RecordRow } from "./transacciones-model";
import { summarizePreviewRecords, type SummaryMetric } from "./records-results-preview";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-results-preview.module.css";

export default function RecordsResultsSummary({ records, businessId, selected }: { records: readonly RecordRow[]; businessId: string | null; selected: readonly SummaryMetric[] }) {
  const { t } = useTransaccionesWords();
  const summary = summarizePreviewRecords(records, businessId);
  const word = (key: string) => t(`business.transactions.layout.results.${key}`);
  if (!selected.length) return null;
  return <section className={styles.summary} aria-label={word("title")} data-testid="records-results-summary">
    <div className={styles.cards}>{selected.map((metric) => {
      const Icon = metric === "sales" ? ArrowDownLeft : ArrowUpRight;
      const money = summary[metric];
      const exclusions = (["unconfirmed", "personal", "unavailable"] as const).filter((reason) => summary.excludedByKind[metric][reason] > 0).map((reason) => t(`business.transactions.layout.results.${reason}`, { count: summary.excludedByKind[metric][reason] }));
      return <article key={metric} data-summary-metric={metric} className={`${styles.card} ${styles[metric]}`} aria-label={word(`metrics.${metric}`)}>
        <h3 className={styles.heading}><Icon size={19} strokeWidth={1.7} aria-hidden="true" /><span>{word(`metrics.${metric}`)}</span></h3>
        <div className={styles.values}>{money.length ? money.slice(0, 2).map((value) => <strong key={value.currency}><PlainAmount money={value} /></strong>) : <p className={styles.noAmount}>{word("none")}</p>}</div>
        {money.length > 2 ? <details className={styles.currencies}><summary>{t("business.transactions.layout.results.more_currencies", { count: money.length - 2 })}</summary><div className={`${styles.values} ${styles.currencyList}`}>{money.slice(2).map((value) => <strong key={value.currency}><PlainAmount money={value} /></strong>)}</div></details> : null}
        {money.length ? <p className={styles.qualification}>{word("basis")}</p> : null}
        {exclusions.length ? <p className={styles.qualification}>{exclusions.join(" · ")}</p> : null}
      </article>;
    })}</div>
  </section>;
}
