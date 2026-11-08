"use client";

import type { ReactNode } from "react";
import { Banknote, ChevronDown, ChevronUp, ClipboardList, FileSearch, Filter, Hash, Package, Wallet, type LucideIcon } from "lucide-react";
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
  { key: "total", icon: Wallet }, { key: "itbis", icon: Banknote },
  { key: "goods", icon: Package }, { key: "services", icon: ClipboardList },
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

function usableKnownAmount(line: AmountLine): string | null {
  if (!line.currency) return null;
  const count = "matching_count" in line ? line.matching_count : line.applicable_count;
  return count > line.unknown_count + line.unsupported_count ? line.known_amount : null;
}

function AmountValue({ line }: { line: AmountLine | undefined }) {
  if (!line || !line.currency) return <Unknown />;
  const amount = line.complete ? line.amount : usableKnownAmount(line);
  return amount !== null ? <ExactAmount currency={line.currency} amount={amount} /> : <Unknown />;
}

function MoneyCard({ metric, icon, answer, loading, totalAction }: { metric: MoneyMetric; icon: LucideIcon; answer: ShelfAnswer | undefined; loading: boolean; totalAction?: { expanded: boolean; toggle: () => void } }) {
  const { t } = useTransaccionesWords();
  const title = t(`${PREFIX}${metric}.title`);
  const lines = metric === "total" ? answer?.totals.filter((line) => line.basis === "document_family_amount") ?? [] : answer?.fiscal_totals?.filter((line) => line.basis === metric) ?? [];
  const line = lines.find((line) => line.kind === "expense");
  const showSkeleton = useDelayedPending(loading);
  const purchaseMetric = metric === "total" || metric === "itbis";
  const helpers = (line: AmountLine | undefined) => {
    if (!line) return null;
    const showPartial = !line.complete && usableKnownAmount(line) !== null;
    const showCoverage = !purchaseMetric && showPartial && "populated_count" in line && line.populated_count < line.applicable_count;
    if (!purchaseMetric && !showPartial && line.unsupported_count === 0) return null;
    return <div className={styles.lineHelpers}>
      {purchaseMetric ? <span className={styles.helper}>{t(`${PREFIX}purchases`)}{showPartial ? <> <span aria-hidden="true">·</span> <span data-overview-partial>{t(`${PREFIX}partial_placeholder`)}</span></> : null}</span> : showPartial ? <div className={styles.partialSummary}>
        <span className={styles.helper} data-overview-partial>{t(`${PREFIX}partial_placeholder`)}</span>
        {showCoverage && "populated_count" in line ? <span className={`${styles.helper} ${styles.coverage}`} data-overview-coverage>{t(`${PREFIX}coverage_placeholder`, { populated: line.populated_count, applicable: line.applicable_count })}</span> : null}
      </div> : null}
      {line.unsupported_count > 0 ? <span className={styles.helper} data-overview-unsupported>{t(`${PREFIX}unsupported_placeholder`, { count: line.unsupported_count })}</span> : null}
    </div>;
  };
  return <div className={`${styles.card} ${styles[metric]}`} data-overview-card={metric}>
    <Heading icon={icon} title={title} />
    {totalAction ? <button type="button" className={styles.totalAction} aria-label={title} aria-expanded={totalAction.expanded} aria-controls={PURCHASE_TOTAL_ID} onClick={totalAction.toggle}>{totalAction.expanded ? <ChevronUp size={19} aria-hidden="true" /> : <ChevronDown size={19} aria-hidden="true" />}</button> : null}
    <div className={styles.values}><div className={styles.currencyGroup} data-currency={line?.currency ?? undefined}>
      {line ? <span className={styles.currency}>{line.currency ?? t("business.transactions.layout.results.no_currency")}</span> : null}
      <div className={styles.family} data-family="purchase"><div className={styles.moneyValue}>{loading ? <span aria-hidden="true" style={{ visibility: showSkeleton ? "visible" : "hidden" }}><RecordsLoadingBar overview /></span> : <AmountValue line={line} />}</div></div>
    </div></div>
    <div className={styles.footer}>
      <div className={styles.helpers}>{helpers(line)}</div>
      {purchaseMetric && !line ? <span className={styles.helper}>{t(`${PREFIX}purchases`)}</span> : null}
    </div>
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
  const fiscalActive = selected.length === 1 && selected[0] === "fiscal";
  return <div data-testid="records-overview-preview" className={styles.overview} aria-busy={loading}>
    <div className={styles.cards}>
      {METRICS.slice(0, 2).map((metric) => <MoneyCard key={metric.key} metric={metric.key} icon={metric.icon} answer={current} loading={loading} totalAction={metric.key === "total" ? { expanded: totalExpanded, toggle: onToggleTotal } : undefined} />)}
      <div className={`${styles.card} ${styles.quantity}`} data-overview-card="quantity"><CountCard icon={Hash} title={t(`${PREFIX}quantity.title`)} value={current?.matching_count ?? null} loading={loading} helper={t(`${PREFIX}quantity_helper_placeholder`)} /></div>
      {METRICS.slice(2).map((metric) => <MoneyCard key={metric.key} metric={metric.key} icon={metric.icon} answer={current} loading={loading} />)}
      <button type="button" data-overview-card="fiscal" data-overview-filter="fiscal" aria-pressed={fiscalActive} disabled={fiscalCount === null || loading || fiscalCount === 0 && !fiscalActive} onClick={() => onChoose("fiscal")} className={`${styles.card} ${styles.fiscal} ${styles.action}`}><CountCard icon={FileSearch} title={t(`${PREFIX}fiscal.title`)} value={loading ? null : fiscalCount} loading={loading} helper={t(`${PREFIX}fiscal.description`)}><Filter size={19} fill={fiscalActive ? "currentColor" : "none"} aria-hidden="true" /></CountCard></button>
    </div>
    {waiting ? <p className={styles.waiting} data-testid="records-bandeja-waiting"><button type="button" className={styles.waitingLink} onClick={onOpenBandeja}>{t(`${PREFIX}bandeja_waiting`, { count: waiting })}</button></p> : null}
  </div>;
}
