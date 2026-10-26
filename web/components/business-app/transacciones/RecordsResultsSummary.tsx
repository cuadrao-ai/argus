"use client";

import { Fragment } from "react";
import { PlainAmount } from "./transacciones-parts";
import type { RecordRow } from "./transacciones-model";
import { summarizePreviewRecords } from "./records-results-preview";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-results-preview.module.css";

export default function RecordsResultsSummary({ records, businessId }: { records: readonly RecordRow[]; businessId: string | null }) {
  const { t } = useTransaccionesWords();
  const summary = summarizePreviewRecords(records, businessId);
  const word = (key: string) => t(`business.transactions.layout.results.${key}`);
  const excluded = Object.values(summary.excluded).reduce((sum, count) => sum + count, 0);
  return <section className={styles.summary} aria-label={word("title")} data-testid="records-results-summary">
    <div className={styles.heading}><span>{word("title")}</span><span>{t("business.transactions.layout.count", { count: summary.count })}</span>{summary.count === 0 || summary.unknownWorkflow < summary.count ? <span>{t(`business.transactions.layout.results.${summary.unknownWorkflow ? "known_review" : "review"}`, { count: summary.review })}</span> : null}{summary.unknownWorkflow ? <span>{t("business.transactions.layout.results.unknown_state", { count: summary.unknownWorkflow })}</span> : null}</div>
    <div className={styles.amounts}><span className={styles.basis}>{word("basis")}</span>{(["sales", "expenses"] as const).map((kind) => <div key={kind} className={styles.total}><span>{word(kind)}</span><strong>{summary[kind].length ? summary[kind].map((money, index) => <Fragment key={money.currency}>{index ? " · " : null}<PlainAmount money={money} /></Fragment>) : word("none")}</strong></div>)}</div>
    {excluded ? <p className={styles.exclusions}>{t("business.transactions.layout.results.excluded", { count: excluded })}{" · "}{(["unconfirmed", "personal", "unavailable"] as const).filter((reason) => summary.excluded[reason] > 0).map((reason) => t(`business.transactions.layout.results.${reason}`, { count: summary.excluded[reason] })).join(" · ")}</p> : null}
  </section>;
}
