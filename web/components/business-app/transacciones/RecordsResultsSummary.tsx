"use client";

import { Info } from "lucide-react";
import { PlainAmount, Unknown } from "./transacciones-parts";
import type { RecordRow } from "./transacciones-model";
import { summarizeSettlementPreview, type SettlementCurrency } from "./records-results-preview";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-results-preview.module.css";

export default function RecordsResultsSummary({ records, businessId, enabled, kind }: { records: readonly RecordRow[]; businessId: string | null; enabled: boolean; kind: RecordRow["kind"] | "all" }) {
  const { t } = useTransaccionesWords();
  if (!enabled || kind === "all") return null;
  const summary = summarizeSettlementPreview(records, businessId, kind);
  const word = (key: string) => t(`business.transactions.layout.results.${key}`);
  const labels = (kind === "venta" ? ["invoiced", "collected", "receivable"] : ["expenses", "paid", "payable"]).map((key) => word(`metrics.${key}`));
  const values = (currency: SettlementCurrency | undefined) => (["total", "settled", "balance"] as const).map((key) => <dd key={key}>{currency?.[key] != null ? <PlainAmount money={{ currency: currency.currency, amount: currency[key] }} /> : <Unknown />}</dd>);
  const exclusions = (["unconfirmed", "personal", "unavailable"] as const).filter((reason) => summary.exclusions[reason] > 0).map((reason) => t(`business.transactions.layout.results.${reason}`, { count: summary.exclusions[reason] }));
  const parts = (currency: SettlementCurrency | undefined, explain: boolean) => <dl className={styles.parts}>{labels.map((label, index) => <div key={label} data-summary-part={index}><dt>{label}{index === 0 && explain && exclusions.length ? <details className={styles.exclusions} onKeyDown={(event) => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}><summary aria-label={word("exclusions")}><Info size={15} aria-hidden="true" /></summary><p>{word("basis")} · {exclusions.join(" · ")}</p></details> : null}</dt>{values(currency)[index]}</div>)}</dl>;
  return <section className={styles.summary} aria-label={word("title")} data-testid="records-results-summary" data-summary-kind={kind}>
    {summary.currencies.length > 1 ? <details className={styles.breakdown}>
      <summary>{t("business.transactions.layout.results.currencies", { count: summary.currencies.length })}<span>{word("breakdown")}</span></summary>
      <div className={styles.currencyList}>{summary.currencies.map((currency, index) => <div key={currency.currency} className={styles.currencyGroup}><h3>{currency.currency}</h3>{parts(currency, index === 0)}</div>)}</div>
    </details> : parts(summary.currencies[0], true)}
  </section>;
}
