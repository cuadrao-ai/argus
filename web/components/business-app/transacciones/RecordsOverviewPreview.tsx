"use client";

import type { ReactNode } from "react";
import { Banknote, ClipboardList, FileSearch, Filter, Hash, Package, Wallet, type LucideIcon } from "lucide-react";
import type { ReportAnswer, ReportFiscalTotal, ReportTotal } from "@/lib/business-reports-api";
import { formatAmount } from "../business-format";
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

/** A pending value fills its slot with one line of the slot's own text, so the card keeps its loaded size; the bar sits over that line. */
function Pending({ shown }: { shown: boolean }) {
  return <span aria-hidden="true" className={styles.pending} style={{ visibility: shown ? "visible" : "hidden" }}>{"\u00a0"}<RecordsLoadingBar overview /></span>;
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

function MoneyCard({ metric, icon, answer, loading, showSkeleton, family }: { family: "sale" | "purchase"; metric: MoneyMetric; icon: LucideIcon; answer: ShelfAnswer | undefined; loading: boolean; showSkeleton: boolean }) {
  const { t } = useTransaccionesWords();
  const title = t(metric === "total" ? `business.terms.net_card_${family === "purchase" ? "purchases" : "sales"}` : `${PREFIX}${metric}.title`);
  const lines = metric === "total" ? answer?.totals.filter((line) => line.basis === "document_net_family_amount") ?? [] : answer?.fiscal_totals?.filter((line) => line.basis === metric) ?? [];
  const line = lines.find((line) => line.kind === (family === "sale" ? "income" : "expense"));
  const familyMetric = metric === "total" || metric === "itbis";
  const helpers = (line: AmountLine | undefined) => {
    if (!line) return null;
    const showPartial = !line.complete && usableKnownAmount(line) !== null;
    const showCoverage = !familyMetric && showPartial && "populated_count" in line && line.populated_count < line.applicable_count;
    if (!familyMetric && !showPartial && line.unsupported_count === 0) return null;
    return <div className={styles.lineHelpers}>
      {familyMetric ? <span className={styles.helper}>{t(family === "purchase" ? `${PREFIX}purchases` : `${PREFIX}sales`)}{showPartial ? <> <span aria-hidden="true">·</span> <span data-overview-partial>{t(`${PREFIX}partial_placeholder`)}</span></> : null}</span> : showPartial ? <div className={styles.partialSummary}>
        <span className={styles.helper} data-overview-partial>{t(`${PREFIX}partial_placeholder`)}</span>
        {showCoverage && "populated_count" in line ? <span className={`${styles.helper} ${styles.coverage}`} data-overview-coverage>{t(`${PREFIX}coverage_placeholder`, { populated: line.populated_count, applicable: line.applicable_count })}</span> : null}
      </div> : null}
      {line.unsupported_count > 0 ? <span className={styles.helper} data-overview-unsupported>{t(`${PREFIX}unsupported_placeholder`, { count: line.unsupported_count })}</span> : null}
    </div>;
  };
  return <div className={`${styles.card} ${styles[metric]}`} data-overview-card={metric}>
    <Heading icon={icon} title={title} />
    <div className={styles.values}><div className={styles.currencyGroup} data-currency={line?.currency ?? undefined}>
      <span className={styles.currency} data-overview-slot="currency">{loading ? <Pending shown={showSkeleton} /> : line ? line.currency ?? t("business.transactions.layout.results.no_currency") : "\u00a0"}</span>
      <div className={styles.family} data-family={family}><div className={styles.moneyValue} data-overview-slot="amount">{loading ? <Pending shown={showSkeleton} /> : <AmountValue line={line} />}</div></div>
    </div></div>
    <div className={styles.footer}>
      <div className={styles.helpers}>{helpers(line)}</div>
      {familyMetric && !line ? <span className={styles.helper}>{t(family === "purchase" ? `${PREFIX}purchases` : `${PREFIX}sales`)}</span> : null}
    </div>
  </div>;
}

function CountCard({ icon, title, value, helper, loading, showSkeleton, children }: { icon: LucideIcon; title: string; value: number | null; helper: string; loading: boolean; showSkeleton: boolean; children?: ReactNode }) {
  const { locale } = useTransaccionesWords();
  return <><Heading icon={icon} title={title} /><span className={`${styles.count} font-display`} data-overview-slot="count">{value !== null ? new Intl.NumberFormat(locale).format(value) : loading ? <Pending shown={showSkeleton} /> : <Unknown />}</span><span className={styles.footer}><span className={styles.helper}>{helper}</span>{children}</span></>;
}

/** `shown` lets the screen carry one wait across its parts; without it the cards wait on their own. */
export default function RecordsOverviewPreview({ family, answer, notReadyCount, selected, onChoose, loading = false, shown }: { family: "sale" | "purchase"; answer?: ShelfAnswer; notReadyCount: number | null; loading?: boolean; shown?: boolean; selected: boolean; onChoose: () => void }) {
  const { t } = useTransaccionesWords();
  const delayed = useDelayedPending(loading);
  const showSkeleton = loading && (shown ?? delayed);
  const current = loading ? undefined : answer;
  const fiscalActive = selected;
  return <div data-testid="records-overview-preview" data-surface-block="overview" className={styles.overview} aria-busy={loading}>
    <div className={styles.cards}>
      {METRICS.slice(0, 2).map((metric) => <MoneyCard key={metric.key} metric={metric.key} family={family} icon={metric.icon} answer={current} loading={loading} showSkeleton={showSkeleton} />)}
      <div className={`${styles.card} ${styles.quantity}`} data-overview-card="quantity"><CountCard icon={Hash} title={t(`${PREFIX}quantity.title`)} value={current?.matching_count ?? null} loading={loading} showSkeleton={showSkeleton} helper={t(`${PREFIX}quantity_helper_placeholder`)} /></div>
      {METRICS.slice(2).map((metric) => <MoneyCard key={metric.key} metric={metric.key} family={family} icon={metric.icon} answer={current} loading={loading} showSkeleton={showSkeleton} />)}
      <button type="button" data-overview-card="fiscal" data-overview-filter="fiscal" aria-pressed={fiscalActive} disabled={notReadyCount === null || loading || notReadyCount === 0 && !fiscalActive} onClick={onChoose} className={`${styles.card} ${styles.fiscal} ${styles.action}`}><CountCard icon={FileSearch} title={t("business.transactions.layout.workflow.not_ready")} value={loading ? null : notReadyCount} loading={loading} showSkeleton={showSkeleton} helper={t(`${PREFIX}fiscal.description`)}><Filter size={19} fill={fiscalActive ? "currentColor" : "none"} aria-hidden="true" /></CountCard></button>
    </div>
  </div>;
}
