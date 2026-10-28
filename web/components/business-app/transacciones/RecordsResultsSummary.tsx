"use client";

import { useRef, useState } from "react";
import { Check, ChevronRight, Clock3, FileText, Info } from "lucide-react";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { currencySymbol } from "@/lib/money-entry";
import { formatAmount } from "../business-format";
import { PlainAmount, Unknown } from "./transacciones-parts";
import type { RecordRow } from "./transacciones-model";
import { summarizeSettlementPreview, type SettlementCurrency, type SettlementSummary } from "./records-results-preview";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-results-preview.module.css";

export default function RecordsResultsSummary({ records, businessId, kind }: { records: readonly RecordRow[]; businessId: string | null; kind: RecordRow["kind"] | "all" }) {
  if (kind === "all") return null;
  const summary = summarizeSettlementPreview(records, businessId, kind);
  return <RecordsSummaryCards key={`${businessId}:${kind}:${summary.currencies.map(({ currency }) => currency).join(",")}`} summary={summary} kind={kind} />;
}

const METRICS = [
  { key: "total", icon: FileText, sale: "invoiced", expense: "expenses" },
  { key: "settled", icon: Check, sale: "collected", expense: "paid" },
  { key: "balance", icon: Clock3, sale: "receivable", expense: "payable" },
] as const;

export function RecordsSummaryCards({ summary, kind, qualifier }: { summary: SettlementSummary; kind: RecordRow["kind"]; qualifier?: string }) {
  const { t, locale } = useTransaccionesWords();
  const [expanded, setExpanded] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const word = (key: string, options?: Record<string, string>) => t(`business.transactions.layout.results.${key}`, options);
  const label = (metric: typeof METRICS[number]) => word(`metrics.${kind === "venta" ? metric.sale : metric.expense}`);
  const partial = (currency: SettlementCurrency) => <><Unknown meaning={word("partial_meaning")} /><span className={styles.partial} data-partial-known>{word("partial", { amount: `${currencySymbol(currency.currency)}${formatAmount(currency.known!, currency.currency, locale)}` })}</span></>;
  const code = (currency: SettlementCurrency) => currency.currency || word("no_currency");
  const visible: (SettlementCurrency | undefined)[] = summary.currencies.length ? summary.currencies.slice(0, 2) : [undefined];
  const exclusions = (["unconfirmed", "personal", "unavailable"] as const).filter((reason) => summary.exclusions[reason] > 0).map((reason) => t(`business.transactions.layout.results.${reason}`, { count: summary.exclusions[reason] }));
  const close = () => { setExpanded(false); trigger.current?.focus(); };
  return <section className={styles.summary} aria-label={word("title")} data-testid="records-results-summary" data-summary-kind={kind}>
    <dl className={styles.cards}>{METRICS.map((metric, index) => <div key={metric.key} className={styles.metric} data-summary-part={index} data-tone={metric.key}>
      <dt className={styles.heading}><metric.icon size={19} strokeWidth={1.6} aria-hidden="true" /><span>{label(metric)}</span>
        {index === 0 && exclusions.length ? <details className={styles.exclusions} onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}>
          <summary aria-label={word("exclusions")}><Info size={15} aria-hidden="true" /></summary><p>{word("basis")} · {exclusions.join(" · ")}</p>
        </details> : null}
      </dt>
      <dd className={styles.values}>{visible.map((currency) => <div className={styles.currencyRow} key={currency?.currency ?? "unknown"} data-currency={currency?.currency}>
        {currency?.[metric.key] != null ? <span className="cuadrao-amount"><span className={styles.symbol}>{currencySymbol(currency.currency)}</span>{formatAmount(currency[metric.key], currency.currency, locale)}</span> : <><span className={styles.symbol}>{currency ? code(currency) : null}</span>{currency?.known != null && metric.key === "total" ? partial(currency) : <Unknown />}</>}
      </div>)}{index === 0 && qualifier ? <p className={styles.qualifier} data-summary-qualifier>{qualifier}</p> : null}</dd>
    </div>)}</dl>
    {summary.currencies.length > 2 ? <button ref={trigger} type="button" className={styles.breakdown} aria-expanded={expanded} onClick={() => setExpanded(true)}>
      {t("business.transactions.layout.results.view_currencies", { count: summary.currencies.length })}<ChevronRight size={16} aria-hidden="true" />
    </button> : null}
    {expanded && summary.currencies.length > 2 ? <AdaptivePanel modal={false} width="md" snaps={["half", "full"]} initialSnap="full" title={word("breakdown_title")} summary={t("business.transactions.layout.results.currencies", { count: summary.currencies.length })} closeLabel={t("common.close")} onClose={close} returnFocusRef={trigger}>
      <div className={styles.currencyList} data-testid="records-currency-breakdown">
        {summary.currencies.map((currency) => <section className={styles.currencyGroup} key={currency.currency} data-currency={currency.currency} aria-label={code(currency)}>
          <h3>{code(currency)}</h3><dl>{METRICS.map((metric) => <div key={metric.key}><dt>{label(metric)}</dt><dd>{currency[metric.key] != null ? <PlainAmount money={{ currency: currency.currency, amount: currency[metric.key]! }} /> : currency.known != null && metric.key === "total" ? partial(currency) : <Unknown />}</dd></div>)}</dl>
        </section>)}
        {exclusions.length ? <p className={styles.basis}>{word("basis")} · {exclusions.join(" · ")}</p> : null}
      </div>
    </AdaptivePanel> : null}
  </section>;
}
