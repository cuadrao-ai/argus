"use client";

// Inicio's right card: one month's figures in one currency, then what they include. Every number is the server's;
// the card only rounds it to whole units through the one shared formatter and says what each term means.

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/Tooltip";
import type { MonthCloseFigures, MonthCloseFiscalRow, MonthCloseNetDisplay } from "@/lib/business-month-close";
import { belowOneUnit, formatMoney, UNKNOWN_VALUE } from "../business-format";
import { FOCUS_RING } from "../foundation/presentation";
import { HomeCard, HOME_MUTED, HOME_SKELETON, HOME_TYPE } from "./HomeCard";

const TERM = `cursor-help rounded-mark underline decoration-[#7d8a84] decoration-dotted underline-offset-4 ${FOCUS_RING}`;
const LINK = `rounded-mark font-medium text-[var(--cuadrao-green)] underline-offset-4 hover:underline ${FOCUS_RING}`;

/** A label whose meaning shows on hover and on keyboard focus. */
function Term({ label, definition, testId }: { label: string; definition: string; testId?: string }) {
  return (
    <Tooltip content={definition} side="top">
      <span tabIndex={0} data-testid={testId} className={TERM}>{label}</span>
    </Tooltip>
  );
}

/**
 * One overview total: whole units, full digits, never cut or wrapped, the currency symbol in the number's own ink.
 * Hover or focus shows the exact amount with cents. A non-zero amount that rounds to 0 says "menos de RD$ 1".
 */
function Amount({ value, currency, locale, muted, testId, className }: { value: string | null; currency: string | null; locale: string; muted: boolean; testId: string; className: string }) {
  const { t } = useTranslation();
  const ink = muted ? "text-[#7d8a84] dark:text-white/45" : "text-[#172b26] dark:text-white";
  if (value === null || currency === null) {
    return <span data-testid={testId} data-state="unknown" className={`${className} ${ink}`}><span aria-hidden="true">{UNKNOWN_VALUE}</span><span className="sr-only">{t("business.dossier.unknown_amount")}</span></span>;
  }
  const whole = belowOneUnit(value)
    ? t("business.inicio.month.under_one", { amount: formatMoney("1", currency, locale, { decimals: 0 }) })
    : formatMoney(value, currency, locale, { decimals: 0 });
  return (
    <Tooltip content={formatMoney(value, currency, locale)} side="top">
      <span tabIndex={0} data-testid={testId} data-amount={value} className={`cuadrao-amount whitespace-nowrap rounded-mark tabular-nums ${FOCUS_RING} ${className} ${ink}`}>{whole}</span>
    </Tooltip>
  );
}

export type HomeMonthCardProps = {
  /** "‹ Mes Año ›": the month switcher. */
  switcher: ReactNode;
  /** The currency pill, only when the month holds more than one currency. */
  currencyMenu: ReactNode;
  state: "loading" | "error" | "ready";
  error?: ReactNode;
  /** The shown currency's block; null when the month has none in it. */
  block: MonthCloseFigures | null;
  /** The shown currency, or the Business's own for a month with no block; null while unknown. */
  currency: string | null;
  net: MonthCloseNetDisplay;
  /** No approved document ever: the figures read RD$ 0, muted, and the footer says when they fill. */
  firstDay: boolean;
  /** The server's "Faltan datos fiscales" rows in the shown currency, one per Registros tab. */
  fiscalRows: readonly MonthCloseFiscalRow[];
  /** Opens the Bandeja; absent for someone who may not prepare. */
  openBandeja?: () => void;
  /** What a fiscal row's Ver opens: Registros on that tab with "Faltan datos fiscales"; null offers no Ver. */
  openFiscal?: (row: MonthCloseFiscalRow) => (() => void) | null;
  label?: string;
  locale: string;
};

export function HomeMonthCard({ switcher, currencyMenu, state, error, block, currency, net, firstDay, fiscalRows, openBandeja, openFiscal, label, locale }: HomeMonthCardProps) {
  const { t } = useTranslation();
  const loading = state === "loading";
  // A month with no document in this currency is a real zero; only the first day reads muted.
  const zero = (value: string | null | undefined) => (block ? value ?? null : "0");
  const figure = (testId: string, value: string | null, className: string) => loading
    ? <span aria-hidden="true" className={`inline-block rounded-mark ${HOME_SKELETON} ${className.includes(HOME_TYPE.net) ? "h-10 w-56" : "h-5 w-32"}`} />
    : <Amount testId={testId} value={value} currency={currency} locale={locale} muted={firstDay} className={className} />;
  const row = (testId: string, term: ReactNode, value: string | null, small = false) => (
    <div className={`flex items-baseline justify-between gap-4 ${HOME_TYPE.label} ${small ? "py-1.5" : "py-2"}`}>
      <span className={`shrink-0 ${HOME_MUTED}`}>{term}</span>
      {figure(testId, value, `text-right ${small ? HOME_TYPE.itbisFigure : HOME_TYPE.figure} font-medium leading-tight`)}
    </div>
  );
  const netValue = net.state === "final" ? net.net_before_itbis : block ? null : "0";
  const counted = block?.documents_counted ?? null;
  const total = block?.documents_total ?? null;
  const inBandeja = block?.documents_in_bandeja ?? null;
  const footer = loading ? (
    <div aria-hidden="true" className="space-y-2">
      <span className={`block h-3.5 w-48 rounded-mark ${HOME_SKELETON}`} />
      <span className={`block h-3.5 w-36 rounded-mark ${HOME_SKELETON}`} />
    </div>
  ) : (
    <>
      {firstDay ? <p data-testid="home-month-first-day" className={HOME_TYPE.included}>{t("business.inicio.month.first_day")}</p>
        : counted !== null && total !== null && total > 0 ? <p data-testid="home-month-included" className={HOME_TYPE.included}>{t("business.inicio.month.included", { counted, total })}</p> : null}
      {inBandeja !== null && inBandeja > 0 ? (
        <p data-testid="home-month-bandeja">
          {t("business.inicio.month.in_bandeja", { count: inBandeja })}
          {openBandeja ? <>{" · "}<button type="button" data-testid="home-month-bandeja-open" className={LINK} onClick={openBandeja}>{t("business.inicio.month.review")}</button></> : null}
        </p>
      ) : null}
      {fiscalRows.map((fiscal) => {
        const open = openFiscal?.(fiscal) ?? null;
        return (
          <p key={fiscal.family} data-testid="home-month-fiscal" data-family={fiscal.family}>
            {/* With both tabs held, each line names its tab, so two lines never read alike. */}
            <Term label={t(fiscalRows.length > 1 ? `business.inicio.month.fiscal_${fiscal.family === "purchase" ? "purchases" : "sales"}` : "business.inicio.month.fiscal", { count: fiscal.count })} definition={t("business.inicio.month.terms.fiscal")} />
            {open ? <>{" · "}<button type="button" data-testid="home-month-fiscal-open" className={LINK} onClick={open}>{t("business.inicio.month.see")}</button></> : null}
          </p>
        );
      })}
    </>
  );
  const term = (key: string) => <Term label={t(`business.inicio.month.${key}`)} definition={t(`business.inicio.month.terms.${key}`)} />;
  return (
    <HomeCard testId="home-month" label={label} heading={<div className="flex min-w-0 flex-1 items-center">{switcher}</div>} action={currencyMenu}>
      <div data-testid="home-month-body" data-state={state} data-currency={currency ?? undefined} aria-busy={loading || undefined} className="px-5 pb-4 pt-2">
        {loading ? <p role="status" className="sr-only">{t("business.month_close.loading")}</p> : null}
        {state === "error" ? error : (
          <>
            {row("home-month-income", term("income"), zero(block?.income_before_itbis))}
            {row("home-month-expenses", term("expenses"), zero(block?.expense_before_itbis))}
            <div className="mt-1 border-t border-black/20 pt-3 dark:border-white/25">
              <p className={`${HOME_TYPE.label} ${HOME_MUTED}`}>{term("net")}</p>
              <p className="mt-1 text-right">{figure("home-month-net", netValue, `font-display ${HOME_TYPE.net} font-medium leading-tight tracking-tight`)}</p>
            </div>
            <div className="mt-3 border-t border-[color:var(--surface-divider)] pt-1.5">
              {row("home-month-itbis-sales", term("itbis_sales"), zero(block?.itbis_charged), true)}
              {row("home-month-itbis-purchases", term("itbis_purchases"), zero(block?.itbis_paid), true)}
            </div>
            <div data-testid="home-month-footer" className={`mt-3 space-y-1 border-t border-[color:var(--surface-divider)] pt-3 ${HOME_TYPE.footer} empty:hidden ${HOME_MUTED}`}>{footer}</div>
          </>
        )}
      </div>
    </HomeCard>
  );
}
