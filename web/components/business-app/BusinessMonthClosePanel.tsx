"use client";

import { LOCAL_BUSINESS_PREFIX } from "@/lib/business-grant";

import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import {
  canStepMonth,
  createMockMonthCloseClient,
  currenciesInOrder,
  currencyShown,
  currentMonthKey,
  documentOverdue,
  formatMonthLabel,
  loadCurrentMonth,
  monthCloseClient,
  MonthCloseError,
  monthCloseNetDisplay,
  monthPickerMonths,
  openItemsHeaderCurrency,
  openItemsInDueOrder,
  openItemsTotalsInOrder,
  overdueTotalsInOrder,
  shiftMonthKey,
  type MonthCloseClient,
  type MonthCloseDocument,
  type MonthCloseSnapshot,
  type OpenItems,
  type OpenItemsList,
} from "@/lib/business-month-close";
import { formatAmount, formatLateness, formatMoney, formatRelativeDay, formatShortDay, UNKNOWN_VALUE, type Lateness } from "./business-format";
import type { RecordsFocus } from "./transacciones/records-focus";
import { cardClass, quietButtonClass } from "./business-ui";
import { useBusiness } from "./BusinessWorkspace";
import { businessSettlementAvailable, businessWorkspaceCurrency } from "@/lib/business-api";
import { recordsCurrencySchema } from "@/lib/business-reports-api";
import { EmptyState } from "./foundation/EmptyState";
import { resolveLanguage } from "@/lib/language-features";
import { referenceCode, refusedForGood } from "@/lib/failure-screen";
import { supportEmail } from "@/lib/support-email";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { setCurrencyView, useCurrencyView } from "@/lib/business-currency-view";
import { currencySymbol } from "@/lib/money-entry";
import { MonthCurrencyMenu } from "./MonthCurrencyMenu";
import moneyCard from "./month-close-money.module.css";
import { previewOpenItems } from "./inicio/money-preview";
import { HomeMonthCard } from "./inicio/HomeMonthCard";

const monthArrowClass =
  "inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-black/70 transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent dark:text-white/70 dark:hover:bg-white/5";

/** The reference a failed read shows: the API error's request id when the client wrapped it, else a generated one. */
const readReference = (error: unknown) => referenceCode(error instanceof MonthCloseError && error.cause ? error.cause : error);

/** Home's cards preview a short list; the reveal opens the rest in place. */
const HOME_MONEY_ROWS = 3;

const LATENESS_TONE: Record<Lateness["tone"], string> = {
  overdue: "bg-[#d66d75]/15 text-[#9e2f39] dark:text-[#ec9aa0]",
  today: "bg-[#f4ead2] text-[#3f3414] dark:bg-[#4a3d1c] dark:text-[#f6e7c1]",
  upcoming: "bg-black/[0.05] text-[#56635e] dark:bg-white/[0.08] dark:text-white/75",
};
type PreviewHold = "loading" | "empty" | "error";

function previewHold(): PreviewHold | null {
  if (typeof window === "undefined") return null;
  if (process.env.NODE_ENV !== "development" || process.env.NEXT_PUBLIC_MOCK_AUTH !== "true") return null;
  const value = new URLSearchParams(window.location.search).get("monthClose");
  if (value === "loading" || value === "empty" || value === "error") return value;
  return null;
}

export function MonthSwitcher({
  month,
  current,
  earliest,
  onMonth,
  heading = false,
}: {
  month: string;
  current: string;
  earliest: string | null;
  onMonth: (month: string) => void;
  /** In Inicio's month card band, the label takes the card-title type. */
  heading?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const options = useMemo(() => monthPickerMonths(current, earliest), [current, earliest]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [position, setPosition] = useState({ left: 8, top: 48 });
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();
  const label = formatMonthLabel(month, locale);

  function close() {
    setOpen(false);
    buttonRef.current?.focus();
  }

  function choose(next: string) {
    const option = options.find((item) => item.month === next);
    if (!option?.selectable) return;
    onMonth(next);
    close();
  }

  useOverlayLayer({
    isOpen: open,
    overlayId: listId,
    containerRef: listRef,
    onKeyDown: (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActive((index) => Math.min(options.length - 1, index + 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActive((index) => Math.max(0, index - 1));
      } else if (event.key === "Home") {
        event.preventDefault();
        setActive(0);
      } else if (event.key === "End") {
        event.preventDefault();
        setActive(Math.max(0, options.length - 1));
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        const option = options[active];
        if (option) choose(option.month);
      }
    },
    onOutsidePointerDown: (event) => {
      if (buttonRef.current?.contains(event.target as Node)) return;
      setOpen(false);
    },
  });

  useEffect(() => {
    if (!open) return;
    const rect = buttonRef.current?.getBoundingClientRect();
    if (rect) {
      const width = 256;
      setPosition({
        left: Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)),
        top: rect.bottom + 4,
      });
    }
    listRef.current?.focus();
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }, [open]);

  return (
    // A control, not a title. The arrows give back their inset so the chevrons sit on the row's edges.
    <div className="-mx-3 flex items-center" data-testid="month-close-switcher">
      <button
        type="button"
        data-testid="month-close-month-prev"
        className={monthArrowClass}
        aria-label={t("business.month_close.previous_month", "Mes anterior")}
        disabled={!canStepMonth(month, -1, current, earliest)}
        onClick={() => onMonth(shiftMonthKey(month, -1))}
      >
        <ChevronLeft className="h-5 w-5" aria-hidden="true" />
      </button>
      <button
        ref={buttonRef}
        type="button"
        data-testid="month-close-month"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        className={`inline-flex min-h-11 min-w-0 items-center rounded-full px-2 font-medium tabular-nums hover:bg-black/5 ${heading ? "font-display text-[18px] text-[#172b26]" : "text-[16px] text-black"} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40 dark:text-white dark:hover:bg-white/5`}
        onClick={() => {
          if (open) {
            close();
            return;
          }
          setActive(Math.max(0, options.findIndex((option) => option.month === month)));
          setOpen(true);
        }}
      >
        {label}
      </button>
      <button
        type="button"
        data-testid="month-close-month-next"
        className={monthArrowClass}
        aria-label={t("business.month_close.next_month", "Mes siguiente")}
        disabled={!canStepMonth(month, 1, current, earliest)}
        onClick={() => onMonth(shiftMonthKey(month, 1))}
      >
        <ChevronRight className="h-5 w-5" aria-hidden="true" />
      </button>
      {open ? createPortal(
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          tabIndex={-1}
          data-testid="month-close-month-picker"
          aria-label={t("business.month_close.choose_month", "Elegir mes")}
          aria-activedescendant={options[active] ? `${listId}-${options[active].month}` : undefined}
          style={{ left: position.left, top: position.top }}
          className="fixed z-[100] max-h-80 w-64 overflow-y-auto rounded-surface border border-black/10 bg-white p-1.5 shadow-lg focus-visible:outline-none dark:border-white/10 dark:bg-[var(--cuadrao-menu-surface)]"
        >
          {options.map((option, index) => {
            const selected = option.month === month;
            return (
              <li
                key={option.month}
                id={`${listId}-${option.month}`}
                role="option"
                aria-selected={selected}
                aria-disabled={option.selectable ? undefined : true}
                data-month={option.month}
                data-active={index === active ? "true" : undefined}
                onMouseEnter={() => setActive(index)}
                onClick={() => choose(option.month)}
                className={`flex min-h-11 items-center justify-between gap-2 rounded-item px-3 font-display text-[16px] font-medium ${option.selectable ? "cursor-pointer text-black dark:text-white" : "cursor-not-allowed text-black/35 dark:text-white/30"} ${index === active ? "bg-black/5 dark:bg-white/5" : ""}`}
              >
                <span>{formatMonthLabel(option.month, locale)}</span>
                {selected ? <Check className="h-4 w-4 shrink-0 text-[var(--cuadrao-green)]" aria-hidden="true" /> : null}
              </li>
            );
          })}
        </ul>,
        document.body,
      ) : null}
    </div>
  );
}

type Text = (key: string, fallback: string, options?: Record<string, unknown>) => string;

/** The counterparty, or the document's kind from the catalog when the record names none. */
function nameOf(document: MonthCloseDocument, text: Text): string {
  return document.counterparty ?? (document.kind === "invoice" ? text("business.month_close.kind_invoice", "Invoice") : text("business.month_close.kind_receipt", "Expense"));
}

export type MonthCloseReview =
  // The Bandeja's counts are known; `reading` is how many receipts are still being read.
  | { count: number; reading?: number }
  | { state: "loading" | "unknown" }
  | { state: "refused"; reference?: string | null }
  | { state: "failed"; retry: () => void; reference?: string | null };

/** Inicio's parts. `firstDay` is the server's "no approved document ever" (no earliest month), null while unknown. */
export type MonthCloseParts = { month: ReactNode; money: ReactNode; receiptStatus: ReactNode; firstDay: boolean | null };

type BusinessMonthCloseViewProps = {
  client: MonthCloseClient;
  /** Selected Business grant. A change reloads this snapshot and keeps the mock's books apart; null holds the load until the Business is known. */
  scopeKey?: string | null;
  /** Only picks the first month asked for; the server's `today` decides the current month. Tests pin it. */
  now?: Date;
  /** Told each time the owner moves to another month. */
  onMonthChange?: (month: string) => void;
  /** The server receipt count, or why it is unavailable; null keeps older callers unknown. */
  review?: MonthCloseReview | null;
  headingAction?: ReactNode;
  /** What a Por cobrar or Por pagar row opens; null leaves the row plain. */
  openDocument?: (document: MonthCloseDocument) => (() => void) | null;
  /** Opens Registros on exactly the list a "Faltan datos fiscales" row counts. */
  openRecords?: (focus: RecordsFocus) => void;
  /** Opens the Bandeja in its normal view. */
  openBandeja?: () => void;
  arrange?: (parts: MonthCloseParts) => ReactNode;
  receiptStatusPlacement?: "lead" | "default";
  /**
   * The server's `settlement_available`. Off, there is no Por cobrar, Por pagar, mark, settle step or "left to mark"
   * line, and the open items are never read; the net says it is approved income minus approved expenses, and ITBIS en
   * ventas stands where ITBIS cobrado was.
   */
  settlement: boolean;
  /** Inicio uses the finance layout. */
  layout?: "finance";
  /** The Business's own currency: the figures' default and the first in its menu. Null while unknown. */
  businessCurrency?: string | null;
  /** Whose currency choice the figures follow: the selected Business. Defaults to `scopeKey`. */
  businessId?: string | null;
};

/** Local month and document state belongs to one selected Business. */
export function BusinessMonthCloseView(props: BusinessMonthCloseViewProps) {
  return <BusinessMonthCloseContent key={props.scopeKey === null ? "pending" : `selected:${props.scopeKey ?? "default"}`} {...props} />;
}

function BusinessMonthCloseContent({
  client,
  scopeKey = "default",
  now,
  onMonthChange,
  review,
  headingAction,
  openDocument,
  openRecords,
  openBandeja,
  arrange,
  receiptStatusPlacement = "default",
  businessCurrency = null,
  businessId,
  settlement,
}: BusinessMonthCloseViewProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const [seed] = useState(() => currentMonthKey(now ?? new Date()));
  const preview = previewHold();
  // Null follows the server's current month; a month the person chose stays chosen.
  const [month, setMonth] = useState<string | null>(null);
  // The server's current month, known once the first month arrives.
  const [currentMonth, setCurrentMonth] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<MonthCloseSnapshot | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  // With an error: the server refused on purpose, so the error offers no Reintentar.
  const [refused, setRefused] = useState(false);
  const [reference, setReference] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set());
  const [openItems, setOpenItems] = useState<OpenItems | null>(null);
  const [openPhase, setOpenPhase] = useState<"loading" | "ready" | "error">("loading");
  const [openRefused, setOpenRefused] = useState(false);
  const [openReference, setOpenReference] = useState<string | null>(null);
  const [openAttempt, setOpenAttempt] = useState(0);
  const generation = useRef(0);
  const openGeneration = useRef(0);
  // Por cobrar and Por pagar are every month's pending documents, so a month change does not reread them.
  async function readOpenItems(): Promise<void> {
    if (scopeKey === null) return;
    const request = ++openGeneration.current;
    try {
      const next = await client.openItems(scopeKey);
      if (openGeneration.current !== request) return;
      setOpenItems(previewOpenItems(next));
      setOpenPhase("ready");
    } catch (error) {
      if (openGeneration.current !== request) return;
      setOpenRefused(refusedForGood(error));
      setOpenReference(readReference(error));
      setOpenPhase("error");
    }
  }

  useEffect(() => {
    if (!settlement || preview === "loading" || preview === "error") return;
    if (preview === "empty") {
      const none: OpenItemsList = { count: 0, totals: [], overdue: { count: 0, totals: [] }, items: [] };
      setOpenItems({ today: null, cuentas_por_cobrar: none, cuentas_por_pagar: none });
      setOpenPhase("ready");
      return;
    }
    setOpenPhase("loading");
    void readOpenItems();
    // readOpenItems reads the same client and scope listed here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, openAttempt, preview, scopeKey, settlement]);

  useEffect(() => {
    const request = ++generation.current;
    const held = preview === "loading" || preview === "error";
    setPhase(preview === "error" ? "error" : "loading");
    if (held) {
      setSnapshot(null);
      return;
    }
    if (scopeKey === null) return;
    (month === null ? loadCurrentMonth(client, scopeKey, seed) : client.load(month, scopeKey)).then(
      (next) => {
        if (generation.current !== request) return;
        setCurrentMonth(next.today?.slice(0, 7) ?? seed);
        setSnapshot(preview === "empty" ? { ...next, documents: [], figures: [], fiscal_rows: [], not_ready_rows: [] } : next);
        setPhase("ready");
      },
      (error: unknown) => {
        if (generation.current !== request) return;
        setRefused(refusedForGood(error));
        setReference(readReference(error));
        setPhase("error");
      },
    );
  }, [attempt, client, month, preview, scopeKey, seed]);

  // The cards show one currency's block at a time; the others stay one choice away, never added in.
  // Settlement off: no document is left to mark, so a block the server does not call final waits on a rate.
  const blocks = (snapshot?.figures ?? []).map((block) => (settlement ? block : { ...block, pending_count: 0 }));
  const currencies = currenciesInOrder(blocks.map((block) => block.currency), businessCurrency);
  // One choice per Business, kept while the person moves between its months.
  const currencyKey = businessId ?? scopeKey;
  const chosenCurrency = useCurrencyView(currencyKey);
  const shownCurrency = currencyShown(currencies, businessCurrency, chosenCurrency);
  const shown = blocks.find((block) => block.currency === shownCurrency) ?? null;
  const net = shown ? monthCloseNetDisplay(shown) : { state: "pending" as const, pending_count: 0, reason: "unknown" as const };
  // Each list is judged by the day its own response carries. An older server sends none: lateness is unknown.
  const openToday = openItems?.today ?? null;
  const knownReview = review && "count" in review ? review : null;
  const overdueOn = (document: MonthCloseDocument, today: string | null) => today !== null && documentOverdue(document, today);
  /** A day against the server's day, or the plain date when the server sent none. */
  const dayText = (day: string, today: string | null) => (today === null ? formatShortDay(day, locale) : formatRelativeDay(day, today, locale));
  const shownMonth = month ?? currentMonth;
  const reviewProblem = review && "state" in review ? review : { state: "unknown" as const };
  const receiptStatus = knownReview ? null : (
    <div data-testid="month-close-receipts-status">
      <div role={reviewProblem.state === "failed" || reviewProblem.state === "refused" ? "alert" : undefined} data-testid={reviewProblem.state === "failed" || reviewProblem.state === "refused" ? "inicio-error" : undefined} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[14px] text-[#56635e] dark:text-white/70">
        <div className="min-w-0 flex-1 basis-full tablet:basis-auto">
          <p>{reviewProblem.state === "refused" ? t("auth.business_unavailable.title") : t(`business.month_close.receipts_${reviewProblem.state}`)}</p>
          {reviewProblem.state === "refused" ? <p>{t("auth.business_unavailable.body", { supportEmail })}{reviewProblem.reference ? <span className="ml-2 inline-flex align-middle"><ReferenceCode reference={reviewProblem.reference} /></span> : null}</p> : null}
        </div>
        {reviewProblem.state === "failed" ? <button type="button" className={`${quietButtonClass} shrink-0 px-3`} onClick={reviewProblem.retry}>{t("common.retry")}</button> : null}
        {reviewProblem.state === "failed" && reviewProblem.reference ? <ReferenceCode reference={reviewProblem.reference} /> : null}
      </div>
    </div>
  );
  const receiptStatusInLead = Boolean(arrange) && receiptStatusPlacement === "lead";
  function moneyColumn(testId: string, title: string, list: OpenItemsList, empty: { title: string; body: string }) {
    const open = expanded.has(testId);
    const rows = openItemsInDueOrder(list.items);
    const shown = open ? rows : rows.slice(0, HOME_MONEY_ROWS);
    const header = openItemsHeaderCurrency(list, businessCurrency);
    const totals = openItemsTotalsInOrder(list, businessCurrency);
    if (totals.length === 0 && list.count === 0 && businessCurrency) totals.push({ currency: businessCurrency, total: "0.00" });
    const beyond = list.count - list.items.length;
    // The total names the currency; a row in it is the number alone, any other keeps its own symbol, and one with no currency is unknown.
    const amount = (value: string | null, currency: string | null) => (value === null || currency === null ? UNKNOWN_VALUE : currency === header ? formatAmount(value, currency, locale) : formatMoney(value, currency, locale));
    const listPart = (
      <>
        {rows.length === 0 ? (
          <div data-testid={`${testId}-empty`}>
            <EmptyState kind="done" settled compact title={empty.title} body={empty.body} />
          </div>
        ) : (
          <>
            <ul className="mt-1">
              {shown.map((document) => {
                const late = document.due_on && openToday ? formatLateness(document.due_on, openToday, t) : null;
                const opens = openDocument?.(document) ?? null;
                const body = (
                  <>
                    {/* The chip always sits under the name, so every row keeps one shape. */}
                    <span className="flex min-w-0 flex-1 flex-col items-start gap-1">
                      <span className="min-w-0 break-words text-[16px] font-medium text-black dark:text-white">{nameOf(document, t)}</span>
                      {late ? (
                        <span data-testid="month-close-lateness" data-tone={late.tone} className={`inline-flex shrink-0 items-center rounded-mark px-2 py-0.5 text-[14px] font-medium tabular-nums ${LATENESS_TONE[late.tone]}`}>{late.text}</span>
                      ) : (
                        // No due day: the day it was issued, so the row still says how old it is.
                        <time data-testid="month-close-issued" dateTime={document.occurred_on} className="shrink-0 text-[14px] tabular-nums text-[#56635e] dark:text-white/70">{dayText(document.occurred_on, openToday)}</time>
                      )}
                    </span>
                    <span className="cuadrao-amount shrink-0 text-right text-[16px] font-medium tabular-nums text-black dark:text-white">{amount(document.amount, document.currency)}</span>
                  </>
                );
                // The row's body gives back its inset on the right, so its hover stays inside the card's padding and the amount ends on the content edge.
                // Home has no mark circle, so the body gives back its left inset too and names align with the header.
                const bodyClass = "-mr-2 -ml-2 flex min-h-11 min-w-0 flex-1 items-center gap-3 rounded-item px-2 py-1 text-left";
                return (
                  <li
                    key={document.id}
                    id={`month-close-row-${document.id}`}
                    tabIndex={-1}
                    data-testid="month-close-row"
                    data-document-id={document.id}
                    data-kind={document.kind}
                    data-status={document.status}
                    data-overdue={overdueOn(document, openToday) ? "true" : "false"}
                    className="rounded-item py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/50"
                  >
                    <div className={moneyCard.row}>
                      {/* Home never settles in one tap. */}
                      {opens ? (
                        <button type="button" data-testid="month-close-row-open" onClick={opens} className={`${bodyClass} transition-colors hover:bg-black/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--cuadrao-green)]/50 dark:hover:bg-white/[0.05]`}>
                          {body}
                        </button>
                      ) : (
                        <div className={bodyClass}>{body}</div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        )}
        {rows.length > HOME_MONEY_ROWS ? (
          <button
            type="button"
            aria-expanded={open}
            data-testid={`${testId}-reveal`}
            className={`${quietButtonClass} mt-1 self-start`}
            onClick={() => setExpanded((current) => {
              const next = new Set(current);
              if (next.has(testId)) next.delete(testId);
              else next.add(testId);
              return next;
            })}
          >
            {open ? t("business.month_close.show_less", "Show less") : t("business.month_close.show_all", { count: rows.length, defaultValue: "See all {{count}}" })}
          </button>
        ) : null}
        {beyond > 0 ? (
          <p data-testid={`${testId}-beyond`} className="mt-1 text-[14px] text-[#56635e] dark:text-white/70">
            {t("business.month_close.open_items_beyond", { count: beyond, defaultValue: "And {{count}} more not shown here." })}
          </p>
        ) : null}
      </>
    );
    // Home: the label sits top right of a tinted header, the total leads on the left with the overdue share under it,
    // one divider, then the short list. A narrow card stacks the label above the total.
    const overdueTotals = overdueTotalsInOrder(list, businessCurrency);
    return (
      <section aria-labelledby={`${testId}-title`} data-testid={testId} className={`${cardClass.replace(/\bp-5\b/, "")} ${moneyCard.card} flex min-w-0 flex-col overflow-hidden`}>
        <div className={`${moneyCard.head} border-b border-[color:var(--surface-divider)] bg-[color:var(--surface-header)] px-5 py-4`}>
          <h4 id={`${testId}-title`} className={`${moneyCard.label} text-[13px] font-semibold uppercase tracking-[0.07em] text-[#56635e] dark:text-white/70`}>{title}</h4>
          <div className="min-w-0">
            {totals.length > 0 ? totals.map((total, index) => (
              <p key={total.currency} data-testid={`${testId}-total`} data-currency={total.currency} className={`cuadrao-amount font-display font-medium leading-tight tracking-tight tabular-nums text-black [overflow-wrap:anywhere] dark:text-white ${index === 0 ? moneyCard.total : "text-[20px]"}`}>
                {formatMoney(total.total, total.currency, locale)}
              </p>
            )) : <p data-testid={`${testId}-total`} className={`cuadrao-amount font-display font-medium leading-tight text-black dark:text-white ${moneyCard.total}`}><span aria-hidden="true">{UNKNOWN_VALUE}</span><span className="sr-only">{t("business.dossier.unknown_amount", "Amount unknown")}</span></p>}
            {list.overdue && list.overdue.count > 0 ? (
              <p data-testid={`${testId}-overdue`} className="mt-1 text-[14px] font-medium tabular-nums text-[#9e2f39] dark:text-[#ec9aa0]">
                {t("business.month_close.overdue_included", { count: list.overdue.count, defaultValue: "Includes {{count}} overdue" })}
                {overdueTotals.map((total) => (
                  <span key={total.currency}>{" · "}<span className="cuadrao-amount whitespace-nowrap" data-currency={total.currency}>{formatMoney(total.total, total.currency, locale)}</span></span>
                ))}
              </p>
            ) : null}
          </div>
        </div>
        <div className="flex flex-col px-5 py-3">{listPart}</div>
      </section>
    );
  }

  /** Pendiente hoy: what every month left open, so it sits apart from the month above it. */
  function moneySection() {
    if (!settlement) return null;
    return (
      <section id="month-close-money" aria-labelledby="month-close-money-title" data-testid="month-close-money" className="scroll-mt-6">
        <div className="flex flex-wrap items-center justify-between gap-3 min-h-11">
          <h3 id="month-close-money-title" className="font-display text-[17px] font-medium text-[#172b26] dark:text-white">{t("business.month_close.collections_title", "Collections and payments")}</h3>
          {headingAction}
        </div>
        {/* Home's section rhythm: a 44px title row, then 16px to its cards, as "Resumen del negocio" has. */}
        <div className="mt-4">
          {moneyBody()}
        </div>
      </section>
    );
  }

  function moneyBody() {
    if (!openItems && openPhase !== "error") {
      // Home's Por cobrar and Por pagar as they will stand: total and label in the tinted header, then three rows.
      return (
        <div role="status" aria-busy="true" data-testid="month-close-money-loading" className="grid grid-cols-1 items-start gap-4 tablet:grid-cols-2 tablet:gap-6">
          <span className="sr-only">{t("business.month_close.loading", "Loading the month")}</span>
          {[0, 1].map((index) => (
            <div key={index} aria-hidden="true" className={`${cardClass.replace(/\bp-5\b/, "")} animate-pulse overflow-hidden motion-reduce:animate-none`}>
              <div className="flex items-start justify-between gap-4 border-b border-[color:var(--surface-divider)] bg-[color:var(--surface-header)] px-5 py-4">
                <div className={`${loadingBar} h-8 w-44 max-w-[60%]`} />
                <div className={`${loadingBar} mt-2 h-[13px] w-20`} />
              </div>
              <div className="space-y-1 px-5 py-3">
                {[0, 1, 2].map((row) => (
                  <div key={row} className="flex min-h-[60px] items-center gap-3">
                    <div className="min-w-0 flex-1 space-y-2"><div className={`${loadingBar} h-4 w-2/5`} /><div className={`${loadingBar} h-5 w-24`} /></div>
                    <div className={`${loadingBar} h-4 w-20`} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      );
    }
    if (!openItems || openPhase === "error") return moneyError();
    const { cuentas_por_cobrar: receivable, cuentas_por_pagar: payable } = openItems;
    if (receivable.count === 0 && payable.count === 0) {
      return (
        <div data-testid="month-close-nothing-open" className={`${cardClass} flex-1`}>
          <EmptyState kind="done" settled compact title={t("business.month_close.nothing_open", "All settled")} />
        </div>
      );
    }
    return (
      <div className="grid flex-1 grid-cols-1 gap-4 tablet:grid-cols-2 tablet:gap-6 items-start">
        {moneyColumn("month-close-receivable", t("business.month_close.receivable_title", "To collect"), receivable, { title: t("business.month_close.receivable_empty", "All collected"), body: t("business.month_close.receivable_empty_body", "No one owes you right now.") })}
        {moneyColumn("month-close-payable", t("business.month_close.payable_title", "To pay"), payable, { title: t("business.month_close.payable_empty", "All paid"), body: t("business.month_close.payable_empty_body", "You have no bills waiting.") })}
      </div>
    );
  }

  /** A read that failed: what failed, the reference to quote, and the way out (Reintentar, or the contact line for a refusal for good). */
  function loadFailure(title: string, failedRefused: boolean, failedReference: string | null, retry: () => void) {
    return (
      <>
        <EmptyState kind="error" compact title={title} body={failedRefused ? t("auth.business_unavailable.body", { supportEmail }) : t("business.empty.error_body", "Your data is still saved. Check your connection and try again.")} action={failedRefused ? undefined : { label: t("business.month_close.retry", "Try again"), run: retry }} />
        {failedReference ? <div className="flex justify-center pb-2"><ReferenceCode reference={failedReference} /></div> : null}
      </>
    );
  }

  function moneyError() {
    return (
      <div data-testid="month-close-money-error" className={`${cardClass} flex-1`}>
        {loadFailure(t("business.month_close.open_items_error", "We couldn't load what is left to collect and pay"), openRefused, openReference, () => setOpenAttempt((value) => value + 1))}
      </div>
    );
  }

  const loadingBar = "rounded-mark bg-black/[0.06] dark:bg-white/[0.08]";
  // Inicio's month card: the month and its currency head it; the figures and what they include sit below. The
  // labels and the month render at once; only the server's facts wait, as bars in their final places.
  const loadingMonth = !snapshot && phase !== "error";
  const label = shownCurrency ? t("business.month_close.subtitle_in", { currency: currencySymbol(shownCurrency) }) : t("business.month_close.subtitle");
  const switcher = (
    <MonthSwitcher
      month={shownMonth ?? seed}
      current={currentMonth ?? shownMonth ?? seed}
      earliest={snapshot?.earliest_month ?? null}
      onMonth={(next) => { setMonth(next); setExpanded(new Set()); onMonthChange?.(next); }}
      heading
    />
  );
  // The choice stays in view whenever the Business holds a second currency in some month (the server's fact); its
  // list is this month's currencies, and a month without the chosen one shows the Business's currency.
  const choosable = snapshot?.more_than_one_currency ?? currencies.length > 1;
  const listed = currencies.length > 0 ? currencies : businessCurrency ? [businessCurrency] : [];
  const counts = Object.fromEntries(blocks.flatMap((block) => (block.documents_total === null ? [] : [[block.currency, block.documents_total] as const])));
  const pillCurrency = shownCurrency ?? businessCurrency;
  const currencyMenu = choosable && pillCurrency && listed.length > 0 && !loadingMonth ? (
    <MonthCurrencyMenu currencies={listed} value={pillCurrency} counts={counts} onChoose={(next) => { if (currencyKey !== null) setCurrencyView(currencyKey, next); }} />
  ) : null;
  const range = snapshot ? { from: snapshot.from, to: snapshot.to } : null;
  const cardCurrency = shownCurrency ?? businessCurrency;
  const monthPart = (
    <HomeMonthCard
      switcher={switcher}
      currencyMenu={currencyMenu}
      state={phase === "error" ? "error" : loadingMonth ? "loading" : "ready"}
      error={loadFailure(t("business.month_close.error_title", "We couldn't load the month"), refused, reference, () => setAttempt((value) => value + 1))}
      block={shown}
      currency={cardCurrency}
      net={net}
      firstDay={snapshot !== null && snapshot.earliest_month === null}
      notReadyRows={snapshot?.not_ready_rows?.filter((row) => row.currency === cardCurrency) ?? null}
      openBandeja={openBandeja}
      // Registros lists only the currencies it can show one at a time; a row in another keeps its count and no Ver.
      openNotReady={(row) => (openRecords && range && recordsCurrencySchema.safeParse(row.currency).success ? () => openRecords({ family: row.family, currency: row.currency, ...range, ready: false }) : null)}
      label={label}
      locale={locale}
    />
  );
  const moneyPart = settlement ? <div className="@container">{moneySection()}</div> : null;
  // A month that could not load cannot say whether any document ever arrived: the card then says only what the
  // Bandeja holds.
  const firstDay = snapshot ? snapshot.earliest_month === null : phase === "error" ? false : null;
  return arrange ? <>{arrange({ month: monthPart, money: moneyPart, receiptStatus: receiptStatusInLead ? receiptStatus : null, firstDay })}</> : <div className="space-y-6">{monthPart}{moneyPart}</div>;
}

export type MonthCloseSource = { client: MonthCloseClient; scopeKey: string | null };

/** The month close the selected Business reads. One per view, so the sample books Inicio closes are the books its export sees. */
// One sample book per sample source and settlement answer, so Inicio and an export opened from the top bar see the same closed months.
const SAMPLE_CLIENTS = new WeakMap<object, Map<boolean, MonthCloseClient>>();
function sampleClientFor(source: object, empty = false, settlement = false): MonthCloseClient {
  const books = SAMPLE_CLIENTS.get(source) ?? new Map<boolean, MonthCloseClient>();
  SAMPLE_CLIENTS.set(source, books);
  const known = books.get(settlement);
  if (known) return known;
  // `?currencies=two` on the preview adds dollar documents to the open month.
  const dollars = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("currencies") === "two";
  const made = createMockMonthCloseClient({ dollars, empty, settlement });
  books.set(settlement, made);
  return made;
}

export function useMonthCloseSource(): MonthCloseSource {
  const { chosen, source, spaces, records } = useBusiness();
  // One key per selected Business, so a switch, even between two Businesses the person owns, reloads that Business's
  // month. Null until the directory says which Business that is; "own" only for a person with no Business chosen.
  const scopeKey = spaces === null ? null : chosen?.grant_id ?? "own";
  // The sample books answer as the sample workspace's settlement switch says, the way the server would.
  return { client: source.mode === "fixture" ? sampleClientFor(source, chosen?.space_id?.startsWith(LOCAL_BUSINESS_PREFIX), businessSettlementAvailable(records?.workspace)) : monthCloseClient, scopeKey };
}

export default function BusinessMonthClosePanel({ monthClose, onMonthChange, review, headingAction, layout, arrange, receiptStatusPlacement }: { monthClose: MonthCloseSource; onMonthChange?: (month: string) => void; review?: MonthCloseReview | null; headingAction?: ReactNode; layout?: "finance"; arrange?: BusinessMonthCloseViewProps["arrange"]; receiptStatusPlacement?: BusinessMonthCloseViewProps["receiptStatusPlacement"] }) {
  const { chosen, openPanel, records } = useBusiness();
  // An open item carries only its activity id. A receipt's is its saved expense's id; an invoice has no record screen yet.
  const openDocument = (document: MonthCloseDocument) => (document.kind === "receipt" ? () => openPanel({ kind: "expense", expenseId: document.id }) : null);
  // A Para cerrar row's action is work (fixing fiscal data, reviewing): only someone who may prepare gets one. A
  // read-only person sees the same rows and counts without actions.
  const prepares = Boolean(chosen?.capabilities.includes("prepare"));
  const openRecords = prepares ? (focus: RecordsFocus) => openPanel({ kind: "transactions", focus }) : undefined;
  const openBandeja = prepares ? () => openPanel({ kind: "inbox" }) : undefined;
  return (
    <BusinessMonthCloseView
      client={monthClose.client}
      scopeKey={monthClose.scopeKey}
      onMonthChange={onMonthChange}
      review={review}
      headingAction={headingAction}
      openDocument={openDocument}
      openRecords={openRecords}
      openBandeja={openBandeja}
      businessCurrency={businessWorkspaceCurrency(records?.workspace)}
      businessId={chosen?.space_id ?? null}
      settlement={businessSettlementAvailable(records?.workspace)}
      layout={layout}
      arrange={arrange}
      receiptStatusPlacement={receiptStatusPlacement}
    />
  );
}
