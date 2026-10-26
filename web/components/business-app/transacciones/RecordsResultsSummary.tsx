"use client";

import { useState } from "react";
import { PlainAmount, Unknown } from "./transacciones-parts";
import type { RecordRow } from "./transacciones-model";
import { DEFAULT_SUMMARY_METRICS, summarizePreviewRecords, type SummaryMetric } from "./records-results-preview";
import RecordsSummaryCustomizer from "./RecordsSummaryCustomizer";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-results-preview.module.css";

export default function RecordsResultsSummary({ records, businessId }: { records: readonly RecordRow[]; businessId: string | null }) {
  const { t } = useTransaccionesWords();
  const [selected, setSelected] = useState<SummaryMetric[]>(() => [...DEFAULT_SUMMARY_METRICS]);
  const summary = summarizePreviewRecords(records, businessId);
  const word = (key: string) => t(`business.transactions.layout.results.${key}`);
  const excluded = Object.values(summary.excluded).reduce((sum, count) => sum + count, 0);
  return <section className={styles.summary} aria-label={word("title")} data-testid="records-results-summary">
    <div className={styles.summaryHeader}><h3>{word("title")}</h3><RecordsSummaryCustomizer selected={selected} onChange={setSelected} /></div>
    {selected.length ? <div className={styles.cards}>{selected.map((metric) => {
      const monetary = metric === "sales" || metric === "expenses";
      const withoutDocumentUnknown = metric === "without_document" && summary.count > 0 && summary.documents.unknown === summary.count;
      return <article key={metric} data-summary-metric={metric} className={styles.card} aria-label={word(`metrics.${metric}`)}>
        <h4>{word(`metrics.${metric}`)}</h4>
        {monetary ? <>
          <div className={styles.values}>{summary[metric].length ? summary[metric].map((money) => <strong key={money.currency}><PlainAmount money={money} /></strong>) : <p className={styles.noAmount}>{word("none")}</p>}</div>
          <p className={styles.qualification}>{word("basis")}</p>
          {Object.values(summary.excludedByKind[metric]).some(Boolean) ? <p className={styles.qualification}>{(["unconfirmed", "personal", "unavailable"] as const).filter((reason) => summary.excludedByKind[metric][reason] > 0).map((reason) => t(`business.transactions.layout.results.${reason}`, { count: summary.excludedByKind[metric][reason] })).join(" · ")}</p> : null}
        </> : <>
          <div className={styles.values}><strong>{metric === "count" ? summary.count : withoutDocumentUnknown ? <Unknown meaning={word("document_unknown")} /> : summary.documents.missing}</strong></div>
          <p className={styles.qualification}>{word(metric === "count" ? "count_basis" : "document_basis")}</p>
          {metric === "without_document" && summary.documents.unknown > 0 ? <p className={styles.qualification}>{t("business.transactions.layout.results.document_unknown_count", { count: summary.documents.unknown })}</p> : null}
        </>}
      </article>;
    })}</div> : <p className={styles.empty}>{word("empty_metrics")}</p>}
    <div className={styles.supporting}><span>{t("business.transactions.layout.count", { count: summary.count })}</span>{summary.count === 0 || summary.unknownWorkflow < summary.count ? <span>{t(`business.transactions.layout.results.${summary.unknownWorkflow ? "known_review" : "review"}`, { count: summary.review })}</span> : null}{summary.unknownWorkflow ? <span>{t("business.transactions.layout.results.unknown_state", { count: summary.unknownWorkflow })}</span> : null}{excluded ? <span>{t("business.transactions.layout.results.excluded", { count: excluded })}</span> : null}</div>
  </section>;
}
