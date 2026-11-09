"use client";
import { LOCAL_BUSINESS_PREFIX } from "@/lib/business-grant";

import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
  electronicNcf,
  fiscalNumberPresent,
  formatMonthLabel,
  joinCurrencyList,
  loadCurrentMonth,
  monthCloseClient,
  MonthCloseError,
  monthCloseNetDisplay,
  monthClosePendingRateCurrencies,
  monthPickerMonths,
  oneTapPaymentMethod,
  openItemsHeaderCurrency,
  openItemsInDueOrder,
  openItemsTotalsInOrder,
  overdueTotalsInOrder,
  paperNcf,
  rncPresent,
  shiftMonthKey,
  type MonthCloseClient,
  type MonthCloseDocument,
  type MonthCloseSnapshot,
  type MonthCloseStatus,
  type OpenItems,
  type OpenItemsList,
} from "@/lib/business-month-close";
import { formatAmount, formatLateness, formatMoney, formatRelativeDay, formatShortDay, UNKNOWN_VALUE, type Lateness } from "./business-format";
import type { RecordsFocus } from "./transacciones/records-focus";
import { canAddRecords, cardClass, quietButtonClass } from "./business-ui";
import { useBusiness } from "./BusinessWorkspace";
import { businessSettlementAvailable, businessWorkspaceCurrency } from "@/lib/business-api";
import { recordsCurrencySchema } from "@/lib/business-reports-api";
import { dismissToast, showToast, useToasts } from "./foundation/toasts";
import { EmptyState } from "./foundation/EmptyState";
import { resolveLanguage } from "@/lib/language-features";
import { referenceCode, refusedForGood } from "@/lib/failure-screen";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { setCurrencyView, useCurrencyView } from "@/lib/business-currency-view";
import { currencySymbol } from "@/lib/money-entry";
import { MonthCurrencyMenu } from "./MonthCurrencyMenu";
import moneyCard from "./month-close-money.module.css";
import { previewOpenItems } from "./inicio/money-preview";
import { HomeMonthCard } from "./inicio/HomeMonthCard";

const monthArrowClass =
  "inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-black/70 transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent dark:text-white/70 dark:hover:bg-white/5";

/** Rows each money card shows before "Ver las N". */
const MONEY_ROWS = 4;
/** The reference a failed read shows: the API error's request id when the client wrapped it, else a generated one. */
const readReference = (error: unknown) => referenceCode(error instanceof MonthCloseError && error.cause ? error.cause : error);

/** Home's cards preview a short list; the reveal opens the rest in place. */
const HOME_MONEY_ROWS = 3;

/**
 * Inicio in two columns once its canvas is wide enough (56rem, about a
 * 1024px screen with the rail closed): 38fr for the month, 62fr for what is
 * pending, 24px apart. Row 1 holds the month and the Pendiente hoy heading
 * at one height; row 2 the checklist beside Por cobrar and Por pagar; row 3
 * the month's figures as two cards on the same columns. Cards in a row end
 * together. Narrower, it is one column in reading order.
 */
const WIDE = {
  grid: "@min-[56rem]:grid @min-[56rem]:grid-cols-[38fr_62fr] @min-[56rem]:gap-6 @min-[56rem]:space-y-0",
  head: "@min-[56rem]:col-start-1 @min-[56rem]:row-start-1 @min-[56rem]:self-center",
  left: "@min-[56rem]:col-start-1 @min-[56rem]:row-start-2",
  full: "@min-[56rem]:col-span-2",
  money: "@min-[56rem]:col-start-2 @min-[56rem]:row-span-2 @min-[56rem]:row-start-1 @min-[56rem]:grid @min-[56rem]:grid-rows-subgrid @min-[56rem]:pt-0",
  moneyTitle: "@min-[56rem]:flex @min-[56rem]:min-h-11 @min-[56rem]:items-center @min-[56rem]:text-[26px] @min-[56rem]:tracking-tight",
  moneyBody: "@min-[56rem]:mt-0 @min-[56rem]:flex @min-[56rem]:flex-col",
  cards: "@min-[56rem]:col-span-2 @min-[56rem]:grid-cols-subgrid",
  resultGap: "@min-[56rem]:gap-x-16",
} as const;

const LATENESS_TONE: Record<Lateness["tone"], string> = {
  overdue: "bg-[#d66d75]/15 text-[#9e2f39] dark:text-[#ec9aa0]",
  today: "bg-[#f4ead2] text-[#3f3414] dark:bg-[#4a3d1c] dark:text-[#f6e7c1]",
  upcoming: "bg-black/[0.05] text-[#56635e] dark:bg-white/[0.08] dark:text-white/75",
};
type WorkProblem = {
  kind: MonthCloseDocument["kind"];
  name?: string;
  text: string;
  retry?: () => void;
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
  openRequest = 0,
  heading = false,
}: {
  month: string;
  current: string;
  earliest: string | null;
  onMonth: (month: string) => void;
  openRequest?: number;
  /** In Inicio's month card band, the label takes the card-title type. */
  heading?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const options = useMemo(() => monthPickerMonths(current, earliest), [current, earliest]);
  const [open, setOpen] = useState(false);
  const [seenRequest, setSeenRequest] = useState(0);
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
    if (openRequest === seenRequest) return;
    setSeenRequest(openRequest);
    if (openRequest < 1) return;
    setActive(Math.max(0, options.findIndex((option) => option.month === month)));
    setOpen(true);
  }, [month, openRequest, options, seenRequest]);

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
        className={`inline-flex min-h-11 min-w-0 items-center rounded-full px-2 font-medium tabular-nums hover:bg-black/5 ${heading ? "font-display text-[17px] text-[#172b26]" : "text-[16px] text-black"} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40 dark:text-white dark:hover:bg-white/5`}
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

/** A figure the server did not send is unknown. */
function figureCard(value: string | null | undefined): { state: "pending" | "final"; value: string } {
  return value === null || value === undefined ? { state: "pending", value: "" } : { state: "final", value };
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
  /** Close and settlement marks follow the grant's approve capability. */
  canMutate?: boolean;
  /** Only picks the first month asked for; the server's `today` decides the current month. Tests pin it. */
  now?: Date;
  /** Told each time the owner moves to another month. */
  onMonthChange?: (month: string) => void;
  /** The server receipt count, or why it is unavailable; null keeps older callers unknown. */
  review?: MonthCloseReview | null;
  /** Opens Agregar; an empty month offers it as its next step. */
  onAdd?: () => void;
  /** Places the month switcher with the phone greeting or above the desktop checklist. */
  header?: (switcher: ReactNode) => ReactNode;
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
  /** The Business's own currency: the figures' default and the first in its menu. Null while unknown. */
  businessCurrency?: string | null;
  /**
   * `inicio` is the approved Home block. `finance` is the design-lane draft for the new Inicio: one Finanzas
   * section where the month switcher heads only what it controls (a compact close summary and the month's
   * figures) and Cobros y pagos, which spans every month, sits apart under its own heading. Same data,
   * calculations and marks; only the arrangement differs.
   */
  layout?: "inicio" | "finance";
};

/** Local month and document state belongs to one selected Business. */
export function BusinessMonthCloseView(props: BusinessMonthCloseViewProps) {
  return <BusinessMonthCloseContent key={props.scopeKey === null ? "pending" : `selected:${props.scopeKey ?? "default"}`} {...props} />;
}

function BusinessMonthCloseContent({
  client,
  scopeKey = "default",
  canMutate = true,
  now,
  onMonthChange,
  review,
  onAdd,
  header = (switcher) => switcher,
  headingAction,
  openDocument,
  openRecords,
  openBandeja,
  arrange,
  receiptStatusPlacement = "default",
  businessCurrency = null,
  layout = "inicio",
  settlement,
}: BusinessMonthCloseViewProps) {
  const finance = layout === "finance";
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
  const [pickerRequest, setPickerRequest] = useState(0);
  const [pendingIds, setPendingIds] = useState<ReadonlySet<string>>(() => new Set());
  const [openItems, setOpenItems] = useState<OpenItems | null>(null);
  const [openPhase, setOpenPhase] = useState<"loading" | "ready" | "error">("loading");
  const [openRefused, setOpenRefused] = useState(false);
  const [openReference, setOpenReference] = useState<string | null>(null);
  const [openAttempt, setOpenAttempt] = useState(0);
  const inFlight = useRef(new Set<string>());
  const [workProblems, setWorkProblems] = useState<ReadonlyMap<string, WorkProblem>>(() => new Map());
  // Marks in a row share one toast and one Deshacer, instead of a stack of toasts.
  const markToast = useRef<{ id: number; kind: MonthCloseDocument["kind"]; ids: string[] } | null>(null);
  const liveToasts = useToasts();
  const liveToastIds = useRef<ReadonlySet<number>>(new Set());
  useEffect(() => { liveToastIds.current = new Set(liveToasts.map((toast) => toast.id)); }, [liveToasts]);
  const generation = useRef(0);
  const openGeneration = useRef(0);
  const mounted = useRef(true);
  useLayoutEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

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
        setSnapshot(preview === "empty" ? { ...next, documents: [], figures: [], fiscal_rows: [] } : next);
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

  const unreviewed = snapshot?.unreviewed_movements ?? 0;
  // The cards show one currency's block at a time; the others stay one choice away, never added in.
  // Settlement off: no document is left to mark, so a block the server does not call final waits on a rate.
  const blocks = (snapshot?.figures ?? []).map((block) => (settlement ? block : { ...block, pending_count: 0 }));
  const currencies = currenciesInOrder(blocks.map((block) => block.currency), businessCurrency);
  const chosenCurrency = useCurrencyView(scopeKey);
  const shownCurrency = currencyShown(currencies, businessCurrency, chosenCurrency);
  const shown = blocks.find((block) => block.currency === shownCurrency) ?? null;
  const net = shown ? monthCloseNetDisplay(shown) : { state: "pending" as const, pending_count: 0, reason: "unknown" as const };
  // Each list is judged by the day its own response carries. An older server sends none: lateness is unknown and no mark can say when it settled.
  const monthToday = snapshot?.today ?? null;
  const openToday = openItems?.today ?? null;
  const markMethod = oneTapPaymentMethod(snapshot?.payment_methods ?? null);
  const canMark = settlement && canMutate && markMethod !== null && openToday !== null;
  async function mark(document: MonthCloseDocument) {
    if (!canMark || !markMethod || !openToday || !snapshot || phase === "loading" || document.status !== "pendiente" || inFlight.current.has(document.id)) return;
    const settlement = { settled_on: openToday, payment_method: markMethod };
    const documentId = document.id;
    inFlight.current.add(documentId);
    const previousStatus = document.status;
    const nextStatus: MonthCloseStatus = document.kind === "invoice" ? "cobrado" : "pagado";
    setPendingIds((current) => new Set(current).add(documentId));
    setSnapshot((current) =>
      current
        ? { ...current, documents: current.documents.map((item) => (item.id === documentId ? { ...item, status: nextStatus } : item)) }
        : current,
    );
    let saved: MonthCloseDocument;
    try {
      saved = document.kind === "invoice" ? await client.markCobrado(documentId, scopeKey ?? undefined, settlement) : await client.markPagado(documentId, scopeKey ?? undefined, settlement);
    } catch (error) {
      if (!mounted.current) return;
      if (settledByBank(error)) {
        setWorkProblems((current) => new Map(current).set(documentId, { kind: document.kind, name: nameOf(document, t), text: bankMatchedText(document.kind) }));
        await rereadSettlements();
        settle(documentId);
        return;
      }
      setSnapshot((current) =>
        current
          ? {
              ...current,
              documents: current.documents.map((item) =>
                item.id === documentId && item.status === nextStatus ? { ...item, status: previousStatus } : item,
              ),
            }
          : current,
      );
      setWorkProblems((current) => new Map(current).set(documentId, { kind: document.kind, name: nameOf(document, t), text: t("business.month_close.mark_failed", "We couldn't save that change. The status is back to what it was."), retry: () => void mark(document) }));
      settle(documentId);
      return;
    }
    if (!mounted.current) return;
    clearWorkProblem(documentId);
    setSnapshot((current) => (current ? { ...current, documents: current.documents.map((item) => (item.id === documentId ? { ...item, status: saved.status } : item)) } : current));
    const earlier = markToast.current && markToast.current.kind === document.kind && liveToastIds.current.has(markToast.current.id) ? markToast.current : null;
    if (earlier) dismissToast(earlier.id);
    const ids = earlier ? [...earlier.ids, documentId] : [documentId];
    const invoice = document.kind === "invoice";
    const text = ids.length > 1
      ? invoice ? t("business.month_close.marked_cobrado_many", "{{count}} invoices collected.", { count: ids.length }) : t("business.month_close.marked_pagado_many", "{{count}} expenses paid.", { count: ids.length })
      : invoice ? t("business.month_close.marked_cobrado", "{{name}} invoice collected.", { name: nameOf(document, t) }) : t("business.month_close.marked_pagado", "{{name}} expense paid.", { name: nameOf(document, t) });
    const id = showToast({ kind: "success", text, action: { label: t("business.marks.undo", "Undo"), run: () => { markToast.current = null; ids.forEach((each) => void reopen(each, document.kind)); } } });
    markToast.current = { id, kind: document.kind, ids };
    // The row stays hidden until the reread confirms it left the open items.
    await readOpenItems();
    settle(documentId);
  }

  async function reopen(documentId: string, kind: MonthCloseDocument["kind"]) {
    if (inFlight.current.has(documentId)) return;
    inFlight.current.add(documentId);
    setPendingIds((current) => new Set(current).add(documentId));
    const document = snapshot?.documents.find((item) => item.id === documentId);
    const name = document ? nameOf(document, t) : undefined;
    try {
      await client.markPendiente(documentId, scopeKey ?? undefined);
    } catch (error) {
      if (settledByBank(error)) {
        setWorkProblems((current) => new Map(current).set(documentId, { kind, name, text: bankMatchedText(kind) }));
        await rereadSettlements();
        settle(documentId);
        return;
      }
      setWorkProblems((current) => new Map(current).set(documentId, { kind, name, text: t("business.month_close.undo_failed", "We couldn't undo that change. Try again."), retry: () => void reopen(documentId, kind) }));
      settle(documentId);
      return;
    }
    clearWorkProblem(documentId);
    setSnapshot((current) => (current ? { ...current, documents: current.documents.map((item) => (item.id === documentId ? { ...item, status: "pendiente" } : item)) } : current));
    await readOpenItems();
    settle(documentId);
  }

  /** A document igualada with a bank movement keeps the cobrado or pagado the match wrote; only Transacciones can take it back. */
  const settledByBank = (error: unknown) => error instanceof MonthCloseError && error.code === "matched";
  const bankMatchedText = (kind: MonthCloseDocument["kind"]) => (kind === "invoice"
    ? t("business.month_close.matched_cobrado", "This sale is already matched with a bank deposit, so it counts as collected. To change that, unmatch it in Transactions.")
    : t("business.month_close.matched_pagado", "This expense is already matched with a bank charge, so it counts as paid. To change that, unmatch it in Transactions."));

  /** Read the month and the open items again, quietly, so every row shows the settlement the server holds. */
  async function rereadSettlements() {
    if (scopeKey === null || !snapshot?.month) return;
    const request = ++generation.current;
    const [next] = await Promise.all([client.load(snapshot.month, scopeKey).catch(() => null), readOpenItems()]);
    if (next && generation.current === request) setSnapshot(preview === "empty" ? { ...next, documents: [], figures: [], fiscal_rows: [] } : next);
  }

  function clearWorkProblem(documentId: string) {
    setWorkProblems((current) => {
      const next = new Map(current);
      next.delete(documentId);
      return next;
    });
  }

  function settle(documentId: string) {
    inFlight.current.delete(documentId);
    setPendingIds((current) => {
      const next = new Set(current);
      next.delete(documentId);
      return next;
    });
  }

  const knownReview = review && "count" in review ? review : null;
  const documents = snapshot?.documents ?? [];
  const overdueOn = (document: MonthCloseDocument, today: string | null) => today !== null && documentOverdue(document, today);
  /** A day against the server's day, or the plain date when the server sent none. */
  const dayText = (day: string, today: string | null) => (today === null ? formatShortDay(day, locale) : formatRelativeDay(day, today, locale));
  // The server sends a block for each currency that has a document, so no block and no line is an empty month.
  const noDocuments = blocks.length === 0 && documents.length === 0 && unreviewed === 0;
  const shownMonth = month ?? currentMonth;
  const reviewProblem = review && "state" in review ? review : { state: "unknown" as const };
  const receiptStatus = knownReview ? null : (
    <div data-testid="month-close-receipts-status">
      <div role={reviewProblem.state === "failed" || reviewProblem.state === "refused" ? "alert" : undefined} data-testid={reviewProblem.state === "failed" || reviewProblem.state === "refused" ? "inicio-error" : undefined} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[14px] text-[#56635e] dark:text-white/70">
        <div className="min-w-0 flex-1 basis-full tablet:basis-auto">
          <p>{reviewProblem.state === "refused" ? t("auth.business_unavailable.title") : t(`business.month_close.receipts_${reviewProblem.state}`)}</p>
          {reviewProblem.state === "refused" ? <p>{t("auth.business_unavailable.body")}{reviewProblem.reference ? <span className="ml-2 inline-flex align-middle"><ReferenceCode reference={reviewProblem.reference} /></span> : null}</p> : null}
        </div>
        {reviewProblem.state === "failed" ? <button type="button" className={`${quietButtonClass} shrink-0 px-3`} onClick={reviewProblem.retry}>{t("common.retry")}</button> : null}
        {reviewProblem.state === "failed" && reviewProblem.reference ? <ReferenceCode reference={reviewProblem.reference} /> : null}
      </div>
    </div>
  );
  const receiptStatusInLead = finance && Boolean(arrange) && receiptStatusPlacement === "lead";
  const embeddedReceiptStatus = receiptStatusInLead ? null : receiptStatus;
  /** A round check with a 44px target; its circle sits on the card's content edge. */
  function markButton(document: MonthCloseDocument) {
    return (
      <button
        type="button"
        data-testid={document.kind === "invoice" ? "month-close-mark-cobrado" : "month-close-mark-pagado"}
        className="group -ml-[11px] inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/50 disabled:opacity-40"
        disabled={pendingIds.has(document.id) || phase === "loading"}
        aria-label={document.kind === "invoice"
          ? t("business.month_close.mark_cobrado_named", "Mark {{name}} collected", { name: nameOf(document, t) })
          : t("business.month_close.mark_pagado_named", "Mark {{name}} paid", { name: nameOf(document, t) })}
        onClick={() => void mark(document)}
      >
        <span aria-hidden="true" className="inline-flex h-[22px] w-[22px] items-center justify-center rounded-full border-[1.5px] border-[#7d8a84] text-transparent transition-colors group-hover:border-[var(--cuadrao-green)] group-hover:text-[var(--cuadrao-green)]/45 group-disabled:group-hover:border-[#7d8a84] group-disabled:group-hover:text-transparent dark:border-white/45">
          <Check className="h-3.5 w-3.5" strokeWidth={3} />
        </span>
      </button>
    );
  }

  function renderWorkProblem(documentId: string, showName = false) {
    const problem = workProblems.get(documentId);
    if (!problem) return null;
    const saving = pendingIds.has(documentId);
    return (
      <div data-testid="month-close-work-problem" data-problem-id={documentId} className="mt-2 text-[14px]">
        {showName && problem.name ? <p className="font-medium text-black dark:text-white">{problem.name}</p> : null}
        <p role="alert" className="text-[#9e2f39] dark:text-[#ec9aa0]">{problem.text}</p>
        {problem.retry ? <button type="button" disabled={saving} aria-busy={saving} onClick={problem.retry} className={quietButtonClass}>
          {saving ? t("business.capture.saving", "Saving…") : t("common.retry", "Retry")}
        </button> : null}
      </div>
    );
  }

  function moneyColumn(testId: string, title: string, list: OpenItemsList, empty: { title: string; body: string }) {
    const open = expanded.has(testId);
    const rows = openItemsInDueOrder(list.items.filter((document) => !pendingIds.has(document.id) || workProblems.has(document.id)));
    const kind = testId === "month-close-receivable" ? "invoice" : "receipt";
    const problems = [...workProblems].filter(([, problem]) => problem.kind === kind);
    const shown = open ? rows : rows.slice(0, finance ? HOME_MONEY_ROWS : MONEY_ROWS);
    const header = openItemsHeaderCurrency(list, businessCurrency);
    const totals = openItemsTotalsInOrder(list, businessCurrency);
    if (totals.length === 0 && list.count === 0 && businessCurrency) totals.push({ currency: businessCurrency, total: "0.00" });
    const beyond = list.count - list.items.length;
    // The total names the currency; a row in it is the number alone, any other keeps its own symbol, and one with no currency is unknown.
    const amount = (value: string | null, currency: string | null) => (value === null || currency === null ? UNKNOWN_VALUE : currency === header ? formatAmount(value, currency, locale) : formatMoney(value, currency, locale));
    const totalsBlock = (
        <div className="mt-1 flex flex-col border-b border-black/[0.06] pb-4 dark:border-white/[0.06]">
          {totals.length > 0 ? totals.map((total) => (
            <span key={total.currency} data-testid={`${testId}-total`} data-currency={total.currency} className="cuadrao-amount font-display text-[22px] font-medium leading-tight tracking-tight tabular-nums text-black dark:text-white">
              {formatMoney(total.total, total.currency, locale)}
            </span>
          )) : <span data-testid={`${testId}-total`} className="cuadrao-amount font-display text-[22px] font-medium leading-tight tracking-tight tabular-nums text-black dark:text-white"><span aria-hidden="true">{UNKNOWN_VALUE}</span><span className="sr-only">{t("business.dossier.unknown_amount", "Amount unknown")}</span></span>}
        </div>
    );
    const listPart = (
      <>
        {rows.length === 0 ? (
          problems.length > 0 ? null : <div data-testid={`${testId}-empty`} className={finance ? "" : "flex flex-1 flex-col justify-center"}>
            <EmptyState kind="done" settled compact={finance} title={empty.title}
              body={empty.body}
              action={onAdd && !finance ? { label: t("business.actions.add", "Add"), run: onAdd } : undefined} />
          </div>
        ) : (
          <>
            {!finance && list.overdue && list.overdue.count > 0 ? (
              <p data-testid={`${testId}-overdue`} className="mt-1 text-[14px] font-medium tabular-nums text-[#9e2f39] dark:text-[#ec9aa0]">
                {t("business.month_close.overdue_count", { count: list.overdue.count, defaultValue: "{{count}} overdue" })}
                {overdueTotalsInOrder(list, businessCurrency).map((total) => (
                  <span key={total.currency}>{" · "}<span className="cuadrao-amount" data-currency={total.currency}>{formatMoney(total.total, total.currency, locale)}</span></span>
                ))}
              </p>
            ) : null}
            <ul className={finance ? "mt-1" : "mt-3"}>
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
                const bodyClass = `-mr-2 ${finance ? "-ml-2 " : ""}flex min-h-11 min-w-0 flex-1 items-center gap-3 rounded-item px-2 py-1 text-left`;
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
                    <div className={finance ? moneyCard.row : "flex items-center"}>
                      {/* Home never settles in one tap. */}
                      {canMark && !finance ? markButton(document) : null}
                      {opens ? (
                        <button type="button" data-testid="month-close-row-open" onClick={opens} className={`${bodyClass} transition-colors hover:bg-black/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--cuadrao-green)]/50 dark:hover:bg-white/[0.05]`}>
                          {body}
                        </button>
                      ) : (
                        <div className={bodyClass}>{body}</div>
                      )}
                    </div>
                    {renderWorkProblem(document.id)}
                  </li>
                );
              })}
            </ul>
          </>
        )}
        {problems.filter(([id]) => !shown.some((document) => document.id === id)).map(([id]) => <div key={id}>{renderWorkProblem(id, true)}</div>)}
        {rows.length > (finance ? HOME_MONEY_ROWS : MONEY_ROWS) ? (
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
    if (finance) {
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
    return (
      <section aria-labelledby={`${testId}-title`} data-testid={testId} className={`${cardClass} flex min-w-0 flex-col`}>
        <h4 id={`${testId}-title`} className="text-[14px] font-medium text-[#56635e] dark:text-white/70">{title}</h4>
        {totalsBlock}
        {listPart}
      </section>
    );
  }

  /** Pendiente hoy: what every month left open, so it sits apart from the month above it. */
  function moneySection() {
    if (!settlement) return null;
    return (
      <section id="month-close-money" aria-labelledby="month-close-money-title" data-testid="month-close-money" className={finance ? "scroll-mt-6" : `scroll-mt-6 pt-4 tablet:pt-6 ${WIDE.money}`}>
        <div className={`flex flex-wrap items-center justify-between gap-3 ${finance ? "min-h-11" : ""}`}>
        {finance ? (
          <h3 id="month-close-money-title" className="font-display text-[17px] font-medium text-[#172b26] dark:text-white">{t("business.month_close.collections_title", "Collections and payments")}</h3>
        ) : (
        <h3 id="month-close-money-title" className={`font-display text-[21px] font-medium text-black dark:text-white ${WIDE.moneyTitle}`}>
          {t("business.month_close.pending_today", "Pending today")}
        </h3>
        )}
        {headingAction}
        </div>
        {/* Home's section rhythm: a 44px title row, then 16px to its cards, as "Resumen del negocio" has. */}
        <div className={finance ? "mt-4" : `mt-3 ${WIDE.moneyBody}`}>
          {moneyBody()}
        </div>
      </section>
    );
  }

  function moneyBody() {
    if (!openItems && finance && openPhase !== "error") {
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
    if (!openItems) {
      return openPhase === "error" ? moneyError() : (
        <div role="status" aria-busy="true" data-testid="month-close-money-loading" className="grid flex-1 grid-cols-1 gap-4 tablet:grid-cols-2 tablet:gap-6">
          <span className="sr-only">{t("business.month_close.loading", "Loading the month")}</span>
          {[t("business.month_close.receivable_title", "To collect"), t("business.month_close.payable_title", "To pay")].map((title) => (
            <div key={title} aria-hidden="true" className={cardClass}>
              <p className="text-[14px] font-medium text-[#56635e] dark:text-white/70">{title}</p>
              <div className={`${loadingBar} mt-2 h-6 w-40 animate-pulse motion-reduce:animate-none`} />
              <div className={`${loadingBar} mt-4 h-4 w-3/4 animate-pulse motion-reduce:animate-none`} />
            </div>
          ))}
        </div>
      );
    }
    if (openPhase === "error") return moneyError();
    const { cuentas_por_cobrar: receivable, cuentas_por_pagar: payable } = openItems;
    if (receivable.count === 0 && payable.count === 0 && workProblems.size === 0) {
      return (
        <div data-testid="month-close-nothing-open" className={`${cardClass} flex-1`}>
          <EmptyState kind="done" settled compact={finance} title={t("business.month_close.nothing_open", "All settled")} />
        </div>
      );
    }
    return (
      <div className={`grid flex-1 grid-cols-1 gap-4 tablet:grid-cols-2 tablet:gap-6 ${finance ? "items-start" : ""}`}>
        {moneyColumn("month-close-receivable", t("business.month_close.receivable_title", "To collect"), receivable, { title: t("business.month_close.receivable_empty", "All collected"), body: t("business.month_close.receivable_empty_body", "No one owes you right now.") })}
        {moneyColumn("month-close-payable", t("business.month_close.payable_title", "To pay"), payable, { title: t("business.month_close.payable_empty", "All paid"), body: t("business.month_close.payable_empty_body", "You have no bills waiting.") })}
      </div>
    );
  }

  /** A read that failed: what failed, the reference to quote, and the way out (Reintentar, or the contact line for a refusal for good). */
  function loadFailure(title: string, failedRefused: boolean, failedReference: string | null, retry: () => void) {
    return (
      <>
        <EmptyState kind="error" compact title={title} body={failedRefused ? t("auth.business_unavailable.body", "If you think this is a mistake, email us at hola@cuadrao.ai.") : t("business.empty.error_body", "Your data is still saved. Check your connection and try again.")} action={failedRefused ? undefined : { label: t("business.month_close.retry", "Try again"), run: retry }} />
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

  /** An overview total: whole currency units, from the one formatter; the record screens keep the cents. */
  function figure(testId: string, label: string, state: "pending" | "final" | undefined, value: string, why?: ReactNode, className = "") {
    const known = state !== "pending" && shownCurrency !== null;
    return (
      <div data-testid={testId} data-layout="summary" data-state={state} data-amount={known ? value : undefined} className={`min-w-0 ${className}`}>
        <p className="text-[14px] text-[#56635e] dark:text-white/70">{label}</p>
        <p className={`mt-2 font-display text-[22px] font-medium leading-tight tracking-tight text-black dark:text-white ${known ? "cuadrao-amount tabular-nums" : ""}`}>
          {known && shownCurrency ? formatMoney(value, shownCurrency, locale, { decimals: 0 }) : <><span aria-hidden="true">{UNKNOWN_VALUE}</span><span className="sr-only">{t("business.dossier.unknown_amount", "Amount unknown")}</span></>}
        </p>
        {why ? <p className="mt-2 text-[14px] text-[#56635e] dark:text-white/70">{why}</p> : null}
      </div>
    );
  }

  const loadingBar = "rounded-mark bg-black/[0.06] dark:bg-white/[0.08]";
  const figures = { income: figureCard(shown?.income_before_itbis), expenses: figureCard(shown?.expense_before_itbis) };
  const itbisSales = figureCard(shown?.itbis_charged);
  const itbisPurchases = figureCard(shown?.itbis_paid);
  const manyCurrencies = currencies.length > 1 && shownCurrency !== null;
  // ITBIS cobrado needs marks: only while settlement is on, under ITBIS en ventas.
  const itbisCobrado = settlement
    ? <>{t("business.month_close.itbis_cobrado", "ITBIS collected")} <span data-testid="month-close-itbis-cobrado" className="cuadrao-amount tabular-nums">{shown?.itbis_cobrado && shownCurrency ? formatMoney(shown.itbis_cobrado, shownCurrency, locale, { decimals: 0 }) : UNKNOWN_VALUE}</span></>
    : undefined;
  const unknownWhy = (state: "pending" | "final") => (state === "pending" ? t("business.month_close.figure_unknown", "Can't be calculated yet.") : undefined);
  function netDetail(): ReactNode | undefined {
    // While settlement is off the server's final net is the approved income minus the approved expenses.
    if (net.state === "final") return settlement ? undefined : t("business.month_close.approved_figures.net_detail", "Approved income minus expenses");
    if (net.state !== "pending") return undefined;
    if (net.reason === "documents") {
      return manyCurrencies && shownCurrency
        ? t("business.month_close.net_waits_in", { count: net.pending_count, currency: currencySymbol(shownCurrency), defaultValue: "{{count}} documents in {{currency}} left to mark" })
        : t("business.month_close.net_waits", { count: net.pending_count, defaultValue: "{{count}} documents left to mark" });
    }
    if (net.reason === "pending_rate") {
      const codes = monthClosePendingRateCurrencies(blocks);
      const named = codes.length > 0
        ? t("business.month_close.net_pending_rate", { codes: joinCurrencyList(codes, t("business.month_close.list_and", "and")), defaultValue: "Foreign currency: exchange rate pending in {{codes}}" })
        : t("business.month_close.net_pending_rate_plain", "Foreign currency: exchange rate pending");
      return (
        <>
          <span className="block">{named}</span>
          <span className="block">{t("business.month_close.net_pending_rate_aside", "These amounts are not included in the result.")}</span>
        </>
      );
    }
    return t("business.month_close.figure_unknown", "Can't be calculated yet.");
  }

  if (finance) {
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
        openRequest={pickerRequest}
        heading
      />
    );
    const counts = Object.fromEntries(blocks.flatMap((block) => (block.documents_total === null ? [] : [[block.currency, block.documents_total] as const])));
    const currencyMenu = manyCurrencies && !loadingMonth ? (
      <MonthCurrencyMenu currencies={currencies} value={shownCurrency} counts={counts} onChoose={(next) => { if (scopeKey !== null) setCurrencyView(scopeKey, next); }} />
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
        fiscalRows={(snapshot?.fiscal_rows ?? []).filter((row) => row.currency === cardCurrency)}
        openBandeja={openBandeja}
        // Registros lists only the currencies it can show one at a time; a row in another keeps its count and no Ver.
        openFiscal={(row) => (openRecords && range && recordsCurrencySchema.safeParse(row.currency).success ? () => openRecords({ family: row.family, currency: row.currency, ...range, fiscal_data: "missing" }) : null)}
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

  return (
    <div className="@container">
    <div aria-busy={phase === "loading" ? true : undefined} data-testid="month-close" data-layout="two-columns" className={`mb-8 space-y-4 tablet:space-y-6 ${WIDE.grid}`}>
      <div data-testid="month-close-head" className={`min-w-0 ${WIDE.head}`}>
        {header(
          shownMonth && currentMonth ? (
            <MonthSwitcher
              month={shownMonth}
              current={currentMonth}
              earliest={snapshot?.earliest_month ?? null}
              onMonth={(next) => { setMonth(next); setExpanded(new Set()); onMonthChange?.(next); }}
              openRequest={pickerRequest}
            />
          ) : null,
        )}
      </div>

      {embeddedReceiptStatus ? <div className={`${cardClass} ${WIDE.left}`}>{embeddedReceiptStatus}</div> : null}

      {phase === "error" ? (
        <div data-testid="month-close-error" data-layout="error" className={`${cardClass} ${WIDE.full}`}>
          {/* A refusal for good is not the connection's fault, and asking again gets the same answer. */}
          {loadFailure(t("business.month_close.error_title", "We couldn't load the month"), refused, reference, () => setAttempt((value) => value + 1))}
        </div>
      ) : !snapshot ? (
        <div role="status" data-testid="month-close-loading" data-layout="loading" aria-busy="true" className={WIDE.full}>
          <span className="sr-only">{t("business.month_close.loading", "Loading the month")}</span>
          <div aria-hidden="true" className="space-y-4 animate-pulse motion-reduce:animate-none">
            <div className={cardClass}>
              <div className={`${loadingBar} h-5 w-40`} />
              {Array.from({ length: 3 }, (_, index) => <div key={index} data-testid="month-close-loading-row" className={`${loadingBar} mt-4 h-4 w-3/4`} />)}
            </div>
            <div className={`${cardClass} grid grid-cols-2 gap-4 desktop:grid-cols-4`}>
              {Array.from({ length: 4 }, (_, index) => (
                <div key={index} data-testid="month-close-loading-card">
                  <div className={`${loadingBar} h-3 w-16`} />
                  <div className={`${loadingBar} mt-2 h-6 w-28`} />
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : noDocuments ? (
        <>
        <div data-testid="month-close-empty" data-layout="empty" className={`${cardClass} ${WIDE.left}`}>
          <EmptyState
            kind="first_run"
            mark="calendar"
            compact
            title={t("business.month_close.empty_title", "This month has no documents")}
            body={t("business.empty.month_body", "Add this month's receipts and invoices to see your income, expenses and ITBIS.")}
            action={onAdd ? { label: t("business.actions.add", "Add"), run: onAdd } : undefined}
            secondary={{ label: t("business.month_close.choose_month", "Choose month"), run: () => setPickerRequest((value) => value + 1) }}
          />
        </div>
        {/* An empty month still owes or is owed what earlier months left pending. */}
        {!headingAction && openItems && (openItems.cuentas_por_cobrar.count > 0 || openItems.cuentas_por_pagar.count > 0) ? moneySection() : null}
        </>
      ) : (
        <>
          {phase === "loading" ? <p role="status" data-testid="month-close-refreshing" className="sr-only">{t("business.month_close.loading", "Loading the month")}</p> : null}


          <section aria-label={shownCurrency ? t("business.month_close.subtitle_in", { currency: currencySymbol(shownCurrency), defaultValue: "Income, expenses, and ITBIS for the month in {{currency}}." }) : t("business.month_close.subtitle", "Income, expenses, and ITBIS for the month.")} data-testid="month-close-cards" data-currency={shownCurrency ?? undefined} data-loading={phase === "loading" ? "true" : undefined} className={`grid gap-4 tablet:gap-6 ${WIDE.cards}`}>
            {manyCurrencies ? (
              <div className={WIDE.full}>
                <MonthCurrencyMenu currencies={currencies} value={shownCurrency} onChoose={(next) => { if (scopeKey !== null) setCurrencyView(scopeKey, next); }} />
              </div>
            ) : null}
            <div data-testid="month-close-cards-month" className={`${cardClass} grid grid-cols-2 gap-x-4 gap-y-5`}>
            {figure("month-close-income", t("business.month_close.income_label", "Income"), figures.income.state, figures.income.value, unknownWhy(figures.income.state))}
            {figure("month-close-expenses", t("business.month_close.expense_label", "Expenses"), figures.expenses.state, figures.expenses.value, unknownWhy(figures.expenses.state))}
            {figure("month-close-net", t("business.month_close.net_label", "Net result"), net.state, net.state === "final" ? net.net_before_itbis : "", netDetail(), "col-span-2")}
            </div>
            {/* The gap is twice the card's padding plus the 24px between Por cobrar and Por pagar, so these two figures sit on those cards' columns. */}
            <div data-testid="month-close-cards-result" className={`${cardClass} grid grid-cols-2 gap-x-4 gap-y-5 ${WIDE.resultGap}`}>
            {figure("month-close-itbis-sales", t("business.month_close.placeholder.itbis_sales_label"), itbisSales.state, itbisSales.value, itbisSales.state === "pending" ? unknownWhy("pending") : itbisCobrado)}
            {figure("month-close-itbis-purchases", t("business.month_close.placeholder.itbis_purchases_label"), itbisPurchases.state, itbisPurchases.value, unknownWhy(itbisPurchases.state))}
            </div>
          </section>

          {headingAction ? null : moneySection()}
        </>
      )}
      {headingAction ? moneySection() : null}
    </div>
    </div>
  );
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
  // One key per Business, known before the first load: the own Business is "own" before and after the list arrives.
  const scopeKey = spaces === null ? null : chosen && (chosen.role !== "owner" || chosen.space_id?.startsWith(LOCAL_BUSINESS_PREFIX)) ? chosen.grant_id : "own";
  // The sample books answer as the sample workspace's settlement switch says, the way the server would.
  return { client: source.mode === "fixture" ? sampleClientFor(source, chosen?.space_id?.startsWith(LOCAL_BUSINESS_PREFIX), businessSettlementAvailable(records?.workspace)) : monthCloseClient, scopeKey };
}

export default function BusinessMonthClosePanel({ monthClose, onMonthChange, review, header, headingAction, layout, arrange, receiptStatusPlacement }: { monthClose: MonthCloseSource; onMonthChange?: (month: string) => void; review?: MonthCloseReview | null; header?: (switcher: ReactNode) => ReactNode; headingAction?: ReactNode; layout?: "inicio" | "finance"; arrange?: BusinessMonthCloseViewProps["arrange"]; receiptStatusPlacement?: BusinessMonthCloseViewProps["receiptStatusPlacement"] }) {
  const { chosen, actions, openPanel, records } = useBusiness();
  const add = canAddRecords(chosen) ? actions.create.find((action) => action.id === "upload_receipt") : undefined;
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
      canMutate={Boolean(chosen?.capabilities.includes("approve"))}
      onMonthChange={onMonthChange}
      review={review}
      onAdd={add?.run}
      header={header}
      headingAction={headingAction}
      openDocument={openDocument}
      openRecords={openRecords}
      openBandeja={openBandeja}
      businessCurrency={businessWorkspaceCurrency(records?.workspace)}
      settlement={businessSettlementAvailable(records?.workspace)}
      layout={layout}
      arrange={arrange}
      receiptStatusPlacement={receiptStatusPlacement}
    />
  );
}
