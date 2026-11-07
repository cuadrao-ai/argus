"use client";

import { useRef, useState, type ReactNode } from "react";
import { ArrowUpRight, Boxes, ChevronRight, FileSearch, Hash, Receipt, Wallet, Wrench, type LucideIcon } from "lucide-react";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import type { ReportAnswer, ReportFiscalTotal, ReportTotal } from "@/lib/business-reports-api";
import { formatAmount } from "../business-format";
import { PURCHASE_TOTAL_ID } from "./RecordsResultsSummary";
import type { CardFilter, ReviewFilter } from "./records-filter-preview-model";
import { useTransaccionesWords } from "./transacciones-words";
import { useDelayedPending } from "../business-skeletons";
import { RecordsLoadingBar } from "./RecordsLoadingPreview";
import { Unknown } from "./transacciones-parts";
import styles from "./records-overview-preview.module.css";

type ShelfAnswer = Pick<ReportAnswer, "matching_count" | "totals" | "fiscal_totals">;
type MoneyMetric = "total" | "itbis" | "goods" | "services";
type AmountLine = ReportTotal | ReportFiscalTotal;
const METRICS = [
  { key: "total", icon: Wallet }, { key: "itbis", icon: Receipt },
  { key: "goods", icon: Boxes }, { key: "services", icon: Wrench },
] as const;
const PREFIX = "business.transactions.layout.overview.";

function Heading({ icon: Icon, title }: { icon: LucideIcon; title: string }) {
  return <span className={styles.heading}><Icon size={19} strokeWidth={1.7} aria-hidden="true" /><span>{title}</span></span>;
}

function ExactAmount({ amount, currency }: { amount: string; currency: string }) {
  const { locale } = useTransaccionesWords();
  const full = formatAmount(amount, currency, locale);
  const separator = new Intl.NumberFormat(locale).formatToParts(1.1).find((part) => part.type === "decimal")?.value ?? ".";
  const index = full.lastIndexOf(separator);
  return <span className={`cuadrao-amount ${styles.amount}`} aria-label={`${currency} ${full}`}><span aria-hidden="true">{index < 0 ? full : <>{full.slice(0, index)}<sup>{full.slice(index)}</sup></>}</span><span className="sr-only">{currency} {full}</span></span>;
}

function AmountValue({ line }: { line: AmountLine | undefined }) {
  const { t } = useTransaccionesWords();
  if (!line || !line.currency) return <Unknown />;
  return <>
    {line.complete && line.amount !== null ? <ExactAmount currency={line.currency} amount={line.amount} /> : <>
      <Unknown />
      {line.known_amount !== null && ("matching_count" in line ? line.matching_count > line.unknown_count + line.unsupported_count : line.applicable_count > line.unknown_count + line.unsupported_count) ? <span className={styles.partial}>{t(`${PREFIX}partial_placeholder`)} <ExactAmount currency={line.currency} amount={line.known_amount} /></span> : null}
    </>}
  </>;
}

function MoneyCard({ metric, icon, answer, loading, totalAction }: { metric: MoneyMetric; icon: LucideIcon; answer: ShelfAnswer | undefined; loading: boolean; totalAction?: { expanded: boolean; toggle: () => void } }) {
  const { t } = useTransaccionesWords();
  const [expanded, setExpanded] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const title = t(`${PREFIX}${metric}.title`);
  const lines = metric === "total" ? answer?.totals.filter((line) => line.basis === "document_family_amount") ?? [] : answer?.fiscal_totals?.filter((line) => line.basis === metric) ?? [];
  const applicable = lines.filter((line) => line.kind === "expense");
  const currencies = [...new Set(applicable.map((line) => line.currency))];
  const visible = currencies.length ? currencies.slice(0, 2) : [null];
  const showSkeleton = useDelayedPending(loading);
  const helpers = (line: AmountLine | undefined, currency: string | null, labelCurrency: boolean) => line && (line.unsupported_count > 0 || metric === "goods" || metric === "services") ? <div key={`${currency}:${line.kind}`} className={styles.lineHelpers}>
    {labelCurrency ? <span className={styles.currency}>{currency ?? t("business.transactions.layout.results.no_currency")}</span> : null}
    {"populated_count" in line && (metric === "goods" || metric === "services") ? <span className={styles.helper} data-overview-coverage>{t(`${PREFIX}coverage_placeholder`, { populated: line.populated_count, applicable: line.applicable_count })}</span> : null}
    {line.unsupported_count > 0 ? <span className={styles.helper} data-overview-unsupported>{t(`${PREFIX}unsupported_placeholder`, { count: line.unsupported_count })}</span> : null}
  </div> : null;
  const values = (currency: string | null, showHelpers: boolean) => <div className={styles.currencyGroup} key={currency ?? "unknown"} data-currency={currency ?? undefined}>
    {currencies.length ? <span className={styles.currency}>{currency ?? t("business.transactions.layout.results.no_currency")}</span> : null}
    <div className={styles.family} data-family="purchase">
      {(metric === "total" || metric === "itbis") ? <span className={styles.familyLabel}>{t(`${PREFIX}purchases`)}</span> : null}
      <div className={styles.moneyValue}>{loading ? <span aria-hidden="true" style={{ visibility: showSkeleton ? "visible" : "hidden" }}><RecordsLoadingBar overview /></span> : <AmountValue line={applicable.find((line) => line.currency === currency)} />}</div>
      {showHelpers ? helpers(applicable.find((line) => line.currency === currency), currency, false) : null}
    </div>
  </div>;
  const close = () => { setExpanded(false); trigger.current?.focus(); };
  return <div className={`${styles.card} ${styles[metric]}`} data-overview-card={metric}>
    <Heading icon={icon} title={title} />
    {totalAction ? <button type="button" className={styles.totalAction} aria-label={title} aria-expanded={totalAction.expanded} aria-controls={PURCHASE_TOTAL_ID} onClick={totalAction.toggle}><ArrowUpRight size={19} aria-hidden="true" /></button> : null}
    <div className={styles.values}>{visible.map((currency) => values(currency, false))}</div>
    <div className={styles.footer}>
      <div className={styles.helpers}>{applicable.filter((line) => visible.includes(line.currency)).map((line) => helpers(line, line.currency, visible.length > 1))}</div>
      {applicable.length > 0 && (metric === "total" || metric === "itbis") ? <span className={styles.helper}>{t(`${PREFIX}${metric}_helper_placeholder`)}</span> : null}
      {!applicable.length ? <span className={styles.helper}>{t(`${PREFIX}unavailable_placeholder`)}</span> : null}
      {currencies.length > 2 ? <button ref={trigger} type="button" className={styles.breakdown} aria-expanded={expanded} onClick={() => setExpanded(true)}>{t("business.transactions.layout.results.view_currencies", { count: currencies.length })}<ChevronRight size={14} aria-hidden="true" /></button> : null}
    </div>
    {expanded && currencies.length > 2 ? <AdaptivePanel modal={false} width="md" snaps={["half", "full"]} initialSnap="full" title={`${title} · ${t("business.transactions.layout.results.breakdown_title")}`} closeLabel={t("common.close")} onClose={close} returnFocusRef={trigger}><div className={styles.breakdownList} data-testid="records-overview-breakdown">{currencies.map((currency) => values(currency, true))}</div></AdaptivePanel> : null}
  </div>;
}

function CountCard({ icon, title, value, helper, loading, children }: { icon: LucideIcon; title: string; value: number | null; helper: string; loading: boolean; children?: ReactNode }) {
  const { locale } = useTransaccionesWords();
  const showSkeleton = useDelayedPending(loading);
  return <><Heading icon={icon} title={title} /><span className={`${styles.count} font-display`}>{value !== null ? new Intl.NumberFormat(locale).format(value) : loading ? <span aria-hidden="true" style={{ visibility: showSkeleton ? "visible" : "hidden" }}><RecordsLoadingBar overview /></span> : <Unknown />}</span><span className={styles.footer}><span className={styles.helper}>{helper}</span>{children}</span></>;
}

export default function RecordsOverviewPreview({ answer, fiscalCount, totalExpanded, onToggleTotal, selected, onChoose, loading = false, waiting, onOpenBandeja }: { answer?: ShelfAnswer; fiscalCount: number | null; totalExpanded: boolean; onToggleTotal: () => void; loading?: boolean; selected: readonly ReviewFilter[]; onChoose: (value: CardFilter) => void; waiting: number | null; onOpenBandeja: () => void }) {
  const { t } = useTransaccionesWords();
  const current = loading ? undefined : answer;
  return <div data-testid="records-overview-preview" className={styles.overview} aria-busy={loading}>
    <div className={styles.cards}>
      {METRICS.slice(0, 2).map((metric) => <MoneyCard key={metric.key} metric={metric.key} icon={metric.icon} answer={current} loading={loading} totalAction={metric.key === "total" ? { expanded: totalExpanded, toggle: onToggleTotal } : undefined} />)}
      <div className={`${styles.card} ${styles.quantity}`} data-overview-card="quantity"><CountCard icon={Hash} title={t(`${PREFIX}quantity.title`)} value={current?.matching_count ?? null} loading={loading} helper={t(`${PREFIX}quantity_helper_placeholder`)} /></div>
      {METRICS.slice(2).map((metric) => <MoneyCard key={metric.key} metric={metric.key} icon={metric.icon} answer={current} loading={loading} />)}
      <button type="button" data-overview-card="fiscal" data-overview-filter="fiscal" aria-pressed={selected.includes("fiscal")} disabled={fiscalCount === null || loading} onClick={() => onChoose("fiscal")} className={`${styles.card} ${styles.fiscal} ${styles.action}`}><CountCard icon={FileSearch} title={t(`${PREFIX}fiscal.title`)} value={fiscalCount} loading={loading} helper={t(`${PREFIX}fiscal.description`)}><ArrowUpRight size={19} aria-hidden="true" /></CountCard></button>
    </div>
    {waiting ? <p className={styles.waiting} data-testid="records-bandeja-waiting"><button type="button" className={styles.waitingLink} onClick={onOpenBandeja}>{t(`${PREFIX}bandeja_waiting`, { count: waiting })}</button></p> : null}
  </div>;
}
