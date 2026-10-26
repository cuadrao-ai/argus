"use client";

import { useRef, useState } from "react";
import { Check, ChevronRight, Clock3, FileText } from "lucide-react";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { currencySymbol } from "@/lib/money-entry";
import { InvoiceMoney, useInvoiceWords } from "./InvoiceDocument";
import styles from "../transacciones/records-results-preview.module.css";

type InvoiceCurrencySummary = { currency: string; total: number; settled: number; balance: number };

const METRICS = [
  { key: "total", icon: FileText, label: "adjusted_total" },
  { key: "settled", icon: Check, label: "collected" },
  { key: "balance", icon: Clock3, label: "balance" },
] as const;

export default function InvoiceResultsSummary({ currencies }: { currencies: readonly InvoiceCurrencySummary[] }) {
  const { word, t } = useInvoiceWords();
  const [expanded, setExpanded] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const close = () => { setExpanded(false); trigger.current?.focus(); };

  if (!currencies.length) return null;

  return <section className={styles.summary} aria-label={word("issued_summary")} data-testid="invoice-results-summary">
    <dl className={styles.cards}>{METRICS.map((metric, index) => <div key={metric.key} className={styles.metric} data-summary-part={index} data-tone={metric.key}>
      <dt className={styles.heading}><metric.icon size={19} strokeWidth={1.6} aria-hidden="true" /><span>{word(metric.label)}</span></dt>
      <dd className={styles.values}>{currencies.slice(0, 2).map(group => <div className={styles.currencyRow} key={group.currency} data-currency={group.currency}>
        <span className="cuadrao-amount"><span className={styles.symbol}>{currencySymbol(group.currency)}</span><InvoiceMoney numberOnly amount={group[metric.key]} currency={group.currency} /></span>
      </div>)}</dd>
    </div>)}</dl>
    {currencies.length > 2 ? <button ref={trigger} type="button" className={styles.breakdown} aria-expanded={expanded} onClick={() => setExpanded(true)}>
      {t("business.transactions.layout.results.view_currencies", { count: currencies.length })}<ChevronRight size={16} aria-hidden="true" />
    </button> : null}
    {expanded && currencies.length > 2 ? <AdaptivePanel modal={false} width="md" snaps={["half", "full"]} initialSnap="full" title={t("business.transactions.layout.results.breakdown_title")} summary={t("business.transactions.layout.results.currencies", { count: currencies.length })} closeLabel={t("common.close")} onClose={close} returnFocusRef={trigger}>
      <div className={styles.currencyList} data-testid="invoice-currency-breakdown">
        {currencies.map(group => <section className={styles.currencyGroup} key={group.currency} data-currency={group.currency} aria-label={group.currency}>
          <h3>{group.currency}</h3><dl>{METRICS.map(metric => <div key={metric.key}><dt>{word(metric.label)}</dt><dd><InvoiceMoney amount={group[metric.key]} currency={group.currency} /></dd></div>)}</dl>
        </section>)}
      </div>
    </AdaptivePanel> : null}
  </section>;
}
