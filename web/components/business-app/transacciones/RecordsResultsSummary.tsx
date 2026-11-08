"use client";

import { Check, Clock3, FileText, Info } from "lucide-react";
import { currencySymbol } from "@/lib/money-entry";
import { formatAmount } from "../business-format";
import { Unknown } from "./transacciones-parts";
import { reportSummary } from "@/lib/business-reporting-wire";
import type { ReportAnswer } from "@/lib/business-reports-api";
import type { RecordRow } from "./transacciones-model";
import type { SettlementCurrency, SettlementSummary } from "./records-results-preview";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-results-preview.module.css";

export const RECORDS_TOTAL_ID = "records-total";

export default function RecordsResultsSummary({ answer, kind }: { answer?: ReportAnswer; kind: RecordRow["kind"] }) {
  return <RecordsSummaryCards summary={reportSummary(answer, kind)} kind={kind} />;
}

const METRICS = [
  { key: "total", icon: FileText, sale: "invoiced", expense: "expenses" },
  { key: "settled", icon: Check, sale: "collected", expense: "paid" },
  { key: "balance", icon: Clock3, sale: "receivable", expense: "payable" },
] as const;
const PILOT_METRICS = METRICS.filter((metric) => metric.key === "total");

export function RecordsSummaryCards({ summary, kind }: { summary: SettlementSummary; kind: RecordRow["kind"] }) {
  const { t, locale } = useTransaccionesWords();
  const word = (key: string, options?: Record<string, string>) => t(`business.transactions.layout.results.${key}`, options);
  const label = (metric: typeof METRICS[number]) => word(`metrics.${kind === "venta" ? metric.sale : metric.expense}`);
  const partial = (currency: SettlementCurrency) => {
    const amount = `${currencySymbol(currency.currency)}${formatAmount(currency.known!, currency.currency, locale)}`;
    const [before, after] = word("partial", { amount }).split(amount);
    return <><Unknown meaning={word("partial_meaning")} /><span className={styles.partial} data-partial-known>{before}<span className="cuadrao-amount tabular-nums">{amount}</span>{after}</span></>;
  };
  const code = (currency: SettlementCurrency) => currency.currency || word("no_currency");
  const currency = summary.currencies[0];
  const exclusions = (["unconfirmed", "personal", "unavailable"] as const).filter((reason) => summary.exclusions[reason] > 0).map((reason) => t(`business.transactions.layout.results.${reason}`, { count: summary.exclusions[reason] }));
  return <section id={RECORDS_TOTAL_ID} className={styles.summary} aria-label={word("title")} data-testid="records-results-summary" data-summary-kind={kind}>
    <dl className={styles.cards}>{PILOT_METRICS.map((metric, index) => <div key={metric.key} className={styles.metric} data-summary-part={index} data-tone={metric.key}>
      <dt className={styles.heading}><metric.icon size={19} strokeWidth={1.6} aria-hidden="true" /><span>{label(metric)}</span>
        {index === 0 && exclusions.length ? <details className={styles.exclusions} onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}>
          <summary aria-label={word("exclusions")}><Info size={15} aria-hidden="true" /></summary><p>{word("basis")} · {exclusions.join(" · ")}</p>
        </details> : null}
      </dt>
      <dd className={styles.values}><div className={styles.currencyRow} data-currency={currency?.currency}>
        {currency?.[metric.key] != null ? <span className="cuadrao-amount"><span className={styles.symbol}>{currencySymbol(currency.currency)}</span>{formatAmount(currency[metric.key], currency.currency, locale)}</span> : <><span className={styles.symbol}>{currency ? code(currency) : null}</span>{currency?.known != null && metric.key === "total" ? partial(currency) : <Unknown />}</>}
      </div></dd>
    </div>)}</dl>
  </section>;
}
