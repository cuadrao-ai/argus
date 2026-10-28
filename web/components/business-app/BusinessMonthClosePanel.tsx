"use client";
import { LOCAL_BUSINESS_PREFIX } from "@/lib/business-grant";

import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, BadgeCheck, Check, ChevronDown, ChevronLeft, ChevronRight, CircleCheck, Clock, FileWarning, Inbox } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Tooltip } from "@/components/ui/Tooltip";
import {
  canCloseMonth,
  canStepMonth,
  createMockMonthCloseClient,
  currenciesInOrder,
  currencyShown,
  currentMonthKey,
  documentOverdue,
  electronicNcf,
  fiscalNumberPresent,
  formatMonthLabel,
  itbisBalanceDisplay,
  loadCurrentMonth,
  monthCloseBlockers,
  monthCloseClient,
  MonthCloseError,
  monthCloseNetDisplay,
  monthPickerMonths,
  oneTapPaymentMethod,
  openItemsHeaderCurrency,
  openItemsInDueOrder,
  openItemsTotalsInOrder,
  overdueTotalsInOrder,
  paperNcf,
  rncPresent,
  shiftMonthKey,
  sortDocuments,
  type MonthCloseBlocker,
  type MonthCloseClient,
  type MonthCloseDocument,
  type MonthCloseSnapshot,
  type MonthCloseStatus,
  type OpenItems,
  type OpenItemsList,
} from "@/lib/business-month-close";
import { formatAmount, formatDay, formatHeadlineMoney, formatLateness, formatMoney, formatRelativeDay, formatShortDay, UNKNOWN_VALUE, type Lateness } from "./business-format";
import { canAddRecords, cardClass, primaryButtonClass, quietButtonClass } from "./business-ui";
import { useBusiness } from "./BusinessWorkspace";
import { businessWorkspaceCurrency } from "@/lib/business-api";
import { dismissToast, showToast, useToasts } from "./foundation/toasts";
import { EmptyState } from "./foundation/EmptyState";
import { resolveLanguage } from "@/lib/language-features";
import { refusedForGood } from "@/lib/failure-screen";
import { setCurrencyView, useCurrencyView } from "@/lib/business-currency-view";
import { currencySymbol } from "@/lib/money-entry";
import { MonthCurrencyMenu } from "./MonthCurrencyMenu";

const monthArrowClass =
  "inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-black/70 transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent dark:text-white/70 dark:hover:bg-white/5";

/** Rows each money card shows before "Ver las N". */
const MONEY_ROWS = 4;

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
}: {
  month: string;
  current: string;
  earliest: string | null;
  onMonth: (month: string) => void;
  openRequest?: number;
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
        className="inline-flex min-h-11 min-w-0 items-center rounded-full px-2 text-[16px] font-medium tabular-nums text-black hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40 dark:text-white dark:hover:bg-white/5"
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

const CHIP_TONE: Record<MonthCloseStatus, string> = {
  pendiente: "bg-[#f4ead2] text-[#3f3414] dark:bg-[#4a3d1c] dark:text-[#f6e7c1]",
  cobrado: "bg-[#e4f0ea] text-[#1c3d30] dark:bg-[#1c3d30] dark:text-[#d7f3e6]",
  pagado: "bg-black/[0.06] text-black/80 dark:bg-white/10 dark:text-white/85",
};

function StatusChip({ status, label, overdue = false }: { status: MonthCloseStatus; label: string; overdue?: boolean }) {
  const Icon = overdue ? AlertCircle : status === "pendiente" ? Clock : status === "cobrado" ? BadgeCheck : CircleCheck;
  const tone = overdue ? "bg-[#d66d75]/15 text-[#9e2f39] dark:text-[#ec9aa0]" : CHIP_TONE[status];
  return (
    <span data-testid="month-close-status" data-status={overdue ? "vencida" : status} className={`inline-flex min-h-11 items-center gap-1 rounded-mark px-3 text-[14px] font-medium ${tone}`}>
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {label}
    </span>
  );
}

type Text = (key: string, fallback: string, options?: Record<string, unknown>) => string;

/** The counterparty, or the document's kind from the catalog when the record names none. */
function nameOf(document: MonthCloseDocument, text: Text): string {
  return document.counterparty ?? (document.kind === "invoice" ? text("business.month_close.kind_invoice", "Invoice") : text("business.month_close.kind_receipt", "Expense"));
}

function fiscalLine(document: MonthCloseDocument, text: (key: string, fallback: string, options?: Record<string, unknown>) => string): string {
  if (document.fiscal_known === false) return "";
  const parts: string[] = [];
  const rnc = rncPresent(document.rnc) ? document.rnc : null;
  if (rnc) parts.push(text("business.month_close.rnc", "RNC {{value}}", { value: rnc }));
  else parts.push(text("business.month_close.missing_rnc", "No RNC"));
  const ncf = paperNcf(document.ncf);
  const ecf = electronicNcf(document.ecf);
  if (ncf) parts.push(text("business.month_close.ncf", "NCF {{value}}", { value: ncf }));
  if (ecf) parts.push(text("business.month_close.ecf", "e-CF {{value}}", { value: ecf }));
  if (!fiscalNumberPresent(document)) parts.push(text("business.month_close.missing_ncf", "No NCF or e-CF"));
  return parts.join(" · ");
}

function blockerLabel(blocker: MonthCloseBlocker, document: MonthCloseDocument, text: Text): string {
  if (blocker.kind === "missing_rnc") return text("business.month_close.blocker_rnc", "{{name}} has no RNC", { name: nameOf(document, text) });
  return text("business.month_close.blocker_ncf", "{{name}} has no NCF or e-CF", { name: nameOf(document, text) });
}

/** A figure the server did not send is unknown. */
function figureCard(value: string | null | undefined): { state: "pending" | "final"; value: string } {
  return value === null || value === undefined ? { state: "pending", value: "" } : { state: "final", value };
}

function itbisCard(value: string | null | undefined): { state: "pending" | "final"; value: string; credit: boolean } {
  if (value === null || value === undefined) return { state: "pending", value: "", credit: false };
  const balance = itbisBalanceDisplay(value);
  return { state: "final", value: balance.amount, credit: balance.kind === "credit" };
}

export type MonthCloseReview =
  | { count: number; detail: string | null; reading?: number; attention?: number; open: () => void }
  | { state: "loading" | "unknown" | "refused" }
  | { state: "failed"; retry: () => void };

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
  /** The Business's own currency: the figures' default and the first in its menu. Null while unknown. */
  businessCurrency?: string | null;
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
  businessCurrency = null,
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
  const [attempt, setAttempt] = useState(0);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set());
  const [fiscalOpen, setFiscalOpen] = useState(false);
  const [pickerRequest, setPickerRequest] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const [busyClose, setBusyClose] = useState(false);
  const [pendingIds, setPendingIds] = useState<ReadonlySet<string>>(() => new Set());
  const [openItems, setOpenItems] = useState<OpenItems | null>(null);
  const [openPhase, setOpenPhase] = useState<"loading" | "ready" | "error">("loading");
  const [openRefused, setOpenRefused] = useState(false);
  const [openAttempt, setOpenAttempt] = useState(0);
  const inFlight = useRef(new Set<string>());
  const [workProblems, setWorkProblems] = useState<ReadonlyMap<string, WorkProblem>>(() => new Map());
  const [closeProblem, setCloseProblem] = useState<string | null>(null);
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
      setOpenItems(next);
      setOpenPhase("ready");
    } catch (error) {
      if (openGeneration.current !== request) return;
      setOpenRefused(refusedForGood(error));
      setOpenPhase("error");
    }
  }

  useEffect(() => {
    if (preview === "loading" || preview === "error") return;
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
  }, [client, openAttempt, preview, scopeKey]);

  useEffect(() => {
    const request = ++generation.current;
    const held = preview === "loading" || preview === "error";
    setPhase(preview === "error" ? "error" : "loading");
    setConfirming(false);
    if (held) {
      setSnapshot(null);
      return;
    }
    if (scopeKey === null) return;
    (month === null ? loadCurrentMonth(client, scopeKey, seed) : client.load(month, scopeKey)).then(
      (next) => {
        if (generation.current !== request) return;
        setCurrentMonth(next.today?.slice(0, 7) ?? seed);
        setSnapshot(preview === "empty" ? { ...next, documents: [], figures: [] } : next);
        setPhase("ready");
      },
      (error: unknown) => {
        if (generation.current !== request) return;
        setRefused(refusedForGood(error));
        setPhase("error");
      },
    );
  }, [attempt, client, month, preview, scopeKey, seed]);

  const listedBlockers = snapshot ? snapshot.blockers ?? monthCloseBlockers(snapshot.documents) : [];
  const blockers = listedBlockers.filter((blocker) => blocker.kind === "missing_rnc" || blocker.kind === "missing_ncf");
  // The cards show one currency's block at a time; the others stay one choice away, never added in.
  const blocks = snapshot?.figures ?? [];
  const currencies = currenciesInOrder(blocks.map((block) => block.currency), businessCurrency);
  const chosenCurrency = useCurrencyView(scopeKey);
  const shownCurrency = currencyShown(currencies, businessCurrency, chosenCurrency);
  const shown = blocks.find((block) => block.currency === shownCurrency) ?? null;
  const itbis = itbisCard(shown?.itbis_owed);
  const net = shown ? monthCloseNetDisplay(shown) : { state: "pending" as const, pending_count: 0, reason: "unknown" as const };
  // Each list is judged by the day its own response carries. An older server sends none: lateness is unknown and no mark can say when it settled.
  const monthToday = snapshot?.today ?? null;
  const openToday = openItems?.today ?? null;
  const markMethod = oneTapPaymentMethod(snapshot?.payment_methods ?? null);
  const canMark = canMutate && markMethod !== null && openToday !== null;
  const gate = snapshot ? canCloseMonth(snapshot) : { ok: false as const, reason: "not_calendar_month" as const };
  const locked = Boolean(snapshot?.closed_at);
  // A closed month locks its own documents; Pendiente hoy still marks what other months left open.
  const lockedHere = (document: Pick<MonthCloseDocument, "occurred_on">) => locked && snapshot !== null && document.occurred_on >= snapshot.from && document.occurred_on <= snapshot.to;
  const statusLabel = (status: MonthCloseStatus) =>
    ({
      pendiente: t("business.month_close.status_pendiente", "Pending"),
      cobrado: t("business.month_close.status_cobrado", "Collected"),
      pagado: t("business.month_close.status_pagado", "Paid"),
    })[status];
  async function mark(document: MonthCloseDocument) {
    if (!canMark || !markMethod || !openToday || !snapshot || lockedHere(document) || phase === "loading" || document.status !== "pendiente" || inFlight.current.has(document.id)) return;
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
    if (next && generation.current === request) setSnapshot(preview === "empty" ? { ...next, documents: [], figures: [] } : next);
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
  const receiptsReviewed = knownReview?.count === 0 && !knownReview.attention && !knownReview.reading;

  async function confirmClose() {
    if (!canMutate || !snapshot?.month || busyClose) return;
    if (!receiptsReviewed) {
      setConfirming(false);
      return;
    }
    setBusyClose(true);
    setCloseProblem(null);
    try {
      const next = await client.closeMonth(snapshot.month, scopeKey ?? undefined);
      setSnapshot(next);
      setConfirming(false);
    } catch {
      setCloseProblem(t("business.month_close.close_failed", "We couldn't close the month. Try again."));
    } finally {
      setBusyClose(false);
    }
  }

  const canClose = canMutate && gate.ok && !locked && receiptsReviewed;
  const reason = !canMutate
    ? t("business.month_close.reason_permission", "Marking collection, marking payment, and closing the month requires approval permission.")
    : !snapshot || gate.ok
    ? ""
    : gate.reason === "not_calendar_month"
      ? t("business.month_close.reason_not_month", "Choose a calendar month to close it.")
      : gate.reason === "closed"
        ? ""
        : "";

  const documents = snapshot?.documents ?? [];
  const overdueOn = (document: MonthCloseDocument, today: string | null) => today !== null && documentOverdue(document, today);
  /** A day against the server's day, or the plain date when the server sent none. */
  const dayText = (day: string, today: string | null) => (today === null ? formatShortDay(day, locale) : formatRelativeDay(day, today, locale));
  const unsettled = documents.filter((document) => document.status === "pendiente");
  const overdueCount = unsettled.filter((document) => overdueOn(document, monthToday)).length;
  const fiscalDocuments = [...new Set(blockers.map((blocker) => blocker.documentId))].flatMap((id) => documents.filter((document) => document.id === id));
  const lockedRows = locked ? sortDocuments(documents, "newest") : [];
  // The server sends a block for each currency that has a document, so no block and no line is an empty month.
  const noDocuments = blocks.length === 0 && documents.length === 0;
  const rowGrid = "tablet:grid tablet:grid-cols-[7.5rem_minmax(0,1.4fr)_6.5rem_7rem_auto] tablet:items-center tablet:gap-3";
  const shownMonth = month ?? currentMonth;
  const monthName = snapshot?.month ? new Intl.DateTimeFormat(locale, { month: "long", timeZone: "UTC" }).format(new Date(Date.UTC(Number(snapshot.month.slice(0, 4)), Number(snapshot.month.slice(5, 7)) - 1, 1))) : "";
  const tasks: { id: string; icon: typeof Inbox; text: string; detail?: string | null; action?: { label: string; run: () => void } }[] = [
    ...(knownReview && knownReview.count > 0 ? [{ id: "review", icon: Inbox, text: t("business.month_close.checklist_review", { count: knownReview.count, defaultValue: "{{count}} to review in the Inbox" }), detail: knownReview.detail, action: { label: t("business.month_close.action_review", "Review"), run: knownReview.open } }] : []),
    ...(knownReview?.attention ? [{ id: "attention", icon: FileWarning, text: t("business.overview.problem", { count: knownReview.attention }), action: { label: t("business.month_close.action_review", "Review"), run: knownReview.open } }] : []),
    ...(fiscalDocuments.length > 0 ? [{ id: "fiscal", icon: FileWarning, text: t("business.month_close.checklist_fiscal", { count: fiscalDocuments.length, defaultValue: "Add the RNC or NCF to {{count}} documents" }), detail: gate.ok ? null : t("business.month_close.checklist_required", "Needed to close the month") }] : []),
    ...(unsettled.length > 0 ? [{
      id: "settle",
      icon: Clock,
      text: t("business.month_close.checklist_settle", { count: unsettled.length, defaultValue: "Mark {{count}} documents as collected or paid" }),
      detail: overdueCount > 0 ? t("business.month_close.checklist_overdue", { count: overdueCount, defaultValue: "{{count}} overdue" }) : null,
      action: { label: t("business.month_close.action_see", "See"), run: () => document.getElementById("month-close-money")?.scrollIntoView({ block: "start", behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }) },
    }] : []),
  ];

  const reviewProblem = review && "state" in review ? review : { state: "unknown" as const };
  const receiptStatus = knownReview ? null : (
    <div data-testid="month-close-receipts-status">
      <div data-testid={reviewProblem.state === "failed" || reviewProblem.state === "refused" ? "inicio-error" : undefined} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[14px] text-[#56635e] dark:text-white/70">
        <div className="min-w-0 flex-1">
          <p>{reviewProblem.state === "refused" ? t("auth.business_unavailable.title") : t(`business.month_close.receipts_${reviewProblem.state}`)}</p>
          {reviewProblem.state === "refused" ? <p>{t("auth.business_unavailable.body")}</p> : null}
        </div>
        {reviewProblem.state === "failed" ? <button type="button" className={`${quietButtonClass} shrink-0 px-3`} onClick={reviewProblem.retry}>{t("common.retry")}</button> : null}
      </div>
    </div>
  );
  const showFilingReady = !gate.ok && gate.reason === "closed" && !locked;
  const showStepsNote = tasks.length > 0 && Boolean(knownReview) && !knownReview?.reading;
  const showClose = canClose && tasks.length === 0;
  const showChecklistFooter = Boolean(receiptStatus || reason || showFilingReady || showStepsNote || showClose);
  const checklistShown = phase !== "error" && snapshot !== null && !noDocuments && !locked;

  function renderRow(document: MonthCloseDocument, layout: "pending" | "overdue" | "closed" = "pending") {
    const overdue = overdueOn(document, monthToday);
    const pending = canMark && document.status === "pendiente" && !locked;
    return (
      <li
        key={document.id}
        id={`month-close-row-${document.id}`}
        tabIndex={-1}
        data-testid="month-close-row"
        data-document-id={document.id}
        data-kind={document.kind}
        data-status={document.status}
        data-overdue={overdue ? "true" : "false"}
        data-layout={overdue ? "overdue" : layout}
        data-locked={locked ? "true" : "false"}
        className={`flex flex-col gap-3 rounded-item px-4 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/50 ${rowGrid}`}
      >
        <StatusChip status={document.status} overdue={overdue} label={overdue ? t("business.month_close.status_vencida", "Overdue") : statusLabel(document.status)} />
        <div className="min-w-0">
          <span className="block text-[14px] text-[#56635e] dark:text-white/70">
            {document.kind === "invoice" ? t("business.month_close.kind_invoice", "Invoice") : t("business.month_close.kind_receipt", "Expense")}
          </span>
          <span className="block break-words text-[16px] font-medium text-black dark:text-white">{nameOf(document, t)}</span>
          <span className="mt-1 block text-[14px] text-[#56635e] dark:text-white/70">{fiscalLine(document, t)}</span>
        </div>
        <div>
          <time dateTime={document.due_on ?? document.occurred_on} className="block text-[14px] tabular-nums text-black/80 dark:text-white/80">
            {dayText(document.due_on ?? document.occurred_on, monthToday)}
          </time>
        </div>
        <span className="cuadrao-amount text-right text-[16px] font-medium tabular-nums text-black dark:text-white">{formatMoney(document.amount, document.currency, locale) || UNKNOWN_VALUE}</span>
        <div className="flex flex-wrap items-center gap-2">
          {pending ? markButton(document) : null}
        </div>
      </li>
    );
  }

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

  function renderList(testId: string, title: string, rows: MonthCloseDocument[], empty: string, layout: "pending" | "overdue" | "closed" = "pending") {
    const listClass = "mt-2 divide-y divide-black/[0.06] overflow-hidden rounded-surface border border-black/[0.06] bg-white dark:divide-white/[0.06] dark:border-white/[0.06] dark:bg-[#1f2225]";
    return (
      <section aria-labelledby={`${testId}-title`} data-testid={testId} data-layout={layout} className="mt-6">
        <h4 id={`${testId}-title`} className="text-[16px] font-medium text-black dark:text-white">{title}</h4>
        {rows.length === 0 ? (
          <p className="mt-2 text-[14px] text-[#56635e] dark:text-white/70" data-testid={`${testId}-empty`}>{empty}</p>
        ) : (
          <ul className={listClass}>{rows.map((document) => renderRow(document, layout))}</ul>
        )}
      </section>
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
    const shown = open ? rows : rows.slice(0, MONEY_ROWS);
    const header = openItemsHeaderCurrency(list, businessCurrency);
    const totals = openItemsTotalsInOrder(list, businessCurrency);
    if (totals.length === 0 && list.count === 0 && businessCurrency) totals.push({ currency: businessCurrency, total: "0.00" });
    const beyond = list.count - list.items.length;
    // The total names the currency; a row in it is the number alone, any other keeps its own symbol, and one with no currency is unknown.
    const amount = (value: string | null, currency: string | null) => (value === null || currency === null ? UNKNOWN_VALUE : currency === header ? formatAmount(value, currency, locale) : formatMoney(value, currency, locale));
    return (
      <section aria-labelledby={`${testId}-title`} data-testid={testId} className={`${cardClass} flex min-w-0 flex-col`}>
        <h4 id={`${testId}-title`} className="text-[14px] font-medium text-[#56635e] dark:text-white/70">{title}</h4>
        <div className="mt-1 flex flex-col border-b border-black/[0.06] pb-4 dark:border-white/[0.06]">
          {totals.length > 0 ? totals.map((total) => (
            <span key={total.currency} data-testid={`${testId}-total`} data-currency={total.currency} className="cuadrao-amount font-display text-[22px] font-medium leading-tight tracking-tight tabular-nums text-black dark:text-white">
              {formatMoney(total.total, total.currency, locale)}
            </span>
          )) : <span data-testid={`${testId}-total`} className="cuadrao-amount font-display text-[22px] font-medium leading-tight tracking-tight tabular-nums text-black dark:text-white"><span aria-hidden="true">{UNKNOWN_VALUE}</span><span className="sr-only">{t("business.dossier.unknown_amount", "Amount unknown")}</span></span>}
        </div>
        {rows.length === 0 ? (
          problems.length > 0 ? null : <div data-testid={`${testId}-empty`} className="flex flex-1 flex-col justify-center">
            <EmptyState kind="done" settled title={empty.title}
              body={empty.body}
              action={onAdd ? { label: t("business.actions.add", "Add"), run: onAdd } : undefined} />
          </div>
        ) : (
          <>
            {list.overdue && list.overdue.count > 0 ? (
              <p data-testid={`${testId}-overdue`} className="mt-1 text-[14px] font-medium tabular-nums text-[#9e2f39] dark:text-[#ec9aa0]">
                {t("business.month_close.overdue_count", { count: list.overdue.count, defaultValue: "{{count}} overdue" })}
                {overdueTotalsInOrder(list, businessCurrency).map((total) => (
                  <span key={total.currency}>{" · "}<span className="cuadrao-amount" data-currency={total.currency}>{formatMoney(total.total, total.currency, locale)}</span></span>
                ))}
              </p>
            ) : null}
            <ul className="mt-3">
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
                const bodyClass = "-mr-2 flex min-h-11 min-w-0 flex-1 items-center gap-3 rounded-item px-2 py-1 text-left";
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
                    <div className="flex items-center">
                      {canMark && !lockedHere(document) ? markButton(document) : null}
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
        {rows.length > MONEY_ROWS ? (
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
      </section>
    );
  }

  /** Pendiente hoy: what every month left open, so it sits apart from the month above it. */
  function moneySection() {
    return (
      <section id="month-close-money" aria-labelledby="month-close-money-title" data-testid="month-close-money" className={`scroll-mt-6 pt-4 tablet:pt-6 ${WIDE.money}`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 id="month-close-money-title" className={`font-display text-[21px] font-medium text-black dark:text-white ${WIDE.moneyTitle}`}>
          {t("business.month_close.pending_today", "Pending today")}
        </h3>
        {headingAction}
        </div>
        <div className={`mt-3 ${WIDE.moneyBody}`}>
          {moneyBody()}
        </div>
      </section>
    );
  }

  function moneyBody() {
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
          <EmptyState kind="done" settled title={t("business.month_close.nothing_open", "All settled")} />
        </div>
      );
    }
    return (
      <div className="grid flex-1 grid-cols-1 gap-4 tablet:grid-cols-2 tablet:gap-6">
        {moneyColumn("month-close-receivable", t("business.month_close.receivable_title", "To collect"), receivable, { title: t("business.month_close.receivable_empty", "All collected"), body: t("business.month_close.receivable_empty_body", "No one owes you right now.") })}
        {moneyColumn("month-close-payable", t("business.month_close.payable_title", "To pay"), payable, { title: t("business.month_close.payable_empty", "All paid"), body: t("business.month_close.payable_empty_body", "You have no bills waiting.") })}
      </div>
    );
  }

  function moneyError() {
    return (
      <div data-testid="month-close-money-error" className={`${cardClass} flex-1`}>
        {openRefused ? (
          <EmptyState kind="error" compact title={t("business.month_close.open_items_error", "We couldn't load what is left to collect and pay")} body={t("auth.business_unavailable.body", "If you think this is a mistake, email us at hola@cuadrao.ai.")} />
        ) : (
          <EmptyState kind="error" compact title={t("business.month_close.open_items_error", "We couldn't load what is left to collect and pay")} body={t("business.empty.error_body", "Your data is still saved. Check your connection and try again.")} action={{ label: t("business.month_close.retry", "Try again"), run: () => setOpenAttempt((value) => value + 1) }} />
        )}
      </div>
    );
  }

  /** Short when the row's largest figure is 10,000 or more, with the exact amount on hover, on focus, and for a screen reader. */
  function headline(value: string, currency: string, row: readonly string[]) {
    const { short, exact } = formatHeadlineMoney(value, currency, locale, row);
    if (short === exact) return exact;
    return (
      <Tooltip content={exact} side="top">
        <span tabIndex={0} data-testid="month-close-headline" data-exact={exact} className="rounded-mark focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)]">
          <span aria-hidden="true">{short}</span>
          <span className="sr-only">{exact}</span>
        </span>
      </Tooltip>
    );
  }

  function figure(testId: string, label: string, state: "pending" | "final" | undefined, value: string, why?: ReactNode) {
    const known = state !== "pending" && shownCurrency !== null;
    return (
      <div data-testid={testId} data-layout="summary" data-state={state} data-amount={known ? value : undefined} className="min-w-0">
        <p className="text-[14px] text-[#56635e] dark:text-white/70">{label}</p>
        <p className={`mt-1 font-display text-[22px] font-medium leading-tight tracking-tight text-black dark:text-white ${known ? "cuadrao-amount tabular-nums" : ""}`}>
          {known && shownCurrency ? headline(value, shownCurrency, headlineRow) : <><span aria-hidden="true">{UNKNOWN_VALUE}</span><span className="sr-only">{t("business.dossier.unknown_amount", "Amount unknown")}</span></>}
        </p>
        {why ? <p className="mt-1 text-[14px] text-[#56635e] dark:text-white/70">{why}</p> : null}
      </div>
    );
  }

  const loadingBar = "rounded-mark bg-black/[0.06] dark:bg-white/[0.08]";
  const figures = { income: figureCard(shown?.income_before_itbis), expenses: figureCard(shown?.expense_before_itbis) };
  // Every figure in the month's row, so one unit serves all of them.
  const headlineRow = [
    figures.income.state !== "pending" ? figures.income.value : null,
    figures.expenses.state !== "pending" ? figures.expenses.value : null,
    net.state === "final" ? net.net_before_itbis : null,
    itbis.state !== "pending" ? itbis.value : null,
  ].filter((value): value is string => Boolean(value));
  const manyCurrencies = currencies.length > 1 && shownCurrency !== null;

  return (
    <div className="@container">
    <div aria-busy={phase === "loading" ? true : undefined} data-testid="month-close" data-closed={locked ? "true" : "false"} data-layout="two-columns" className={`mb-8 space-y-4 tablet:space-y-6 ${WIDE.grid}`}>
      <div data-testid="month-close-head" className={`min-w-0 ${WIDE.head}`}>
        {header(
          shownMonth && currentMonth ? (
            <MonthSwitcher
              month={shownMonth}
              current={currentMonth}
              earliest={snapshot?.earliest_month ?? null}
              onMonth={(next) => { setMonth(next); setExpanded(new Set()); setFiscalOpen(false); onMonthChange?.(next); }}
              openRequest={pickerRequest}
            />
          ) : null,
        )}
      </div>

      {!checklistShown && receiptStatus ? <div className={`${cardClass} ${WIDE.left}`}>{receiptStatus}</div> : null}

      {phase === "error" ? (
        <div data-testid="month-close-error" data-layout="error" className={`${cardClass} ${WIDE.full}`}>
          {/* A refusal for good is not the connection's fault, and asking again gets the same answer. */}
          {refused ? (
            <EmptyState kind="error" compact title={t("business.month_close.error_title", "We couldn't load the month")} body={t("auth.business_unavailable.body", "If you think this is a mistake, email us at hola@cuadrao.ai.")} />
          ) : (
            <EmptyState kind="error" compact title={t("business.month_close.error_title", "We couldn't load the month")} body={t("business.empty.error_body", "Your data is still saved. Check your connection and try again.")} action={{ label: t("business.month_close.retry", "Try again"), run: () => setAttempt((value) => value + 1) }} />
          )}
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

          {locked && snapshot.closed_at ? (
            <p role="status" data-testid="month-close-closed" className={`${cardClass} flex items-center gap-3 text-[16px] font-medium text-[var(--cuadrao-green)] ${WIDE.left}`}>
              <CircleCheck className="h-5 w-5 shrink-0" aria-hidden="true" />
              <span>
                {t("business.month_close.closed", "Month closed")}
                <span className="block text-[14px] font-normal text-[#56635e] dark:text-white/70">
                  {t("business.month_close.closed_on", "Closed on {{date}}.", { date: formatDay(snapshot.closed_at.slice(0, 10), locale) })}
                </span>
              </span>
            </p>
          ) : (
            <section aria-labelledby="month-close-checklist-title" data-testid="month-close-checklist" className={`${cardClass} flex flex-col ${WIDE.left}`}>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 id="month-close-checklist-title" className="font-display text-[21px] font-medium text-black dark:text-white">
                  {t("business.month_close.checklist_title", { month: monthName, defaultValue: "To close {{month}}" })}
                </h3>
                {tasks.length > 0 ? (
                  <span data-testid="month-close-checklist-left" className="text-[14px] tabular-nums text-[#56635e] dark:text-white/70">{t("business.month_close.checklist_left", { count: tasks.length, defaultValue: "{{count}} left" })}</span>
                ) : null}
              </div>
              {knownReview?.reading ? <p className="mt-3 flex items-center gap-2 text-[14px] text-[#735c14] dark:text-[#f6e7c1]" data-testid="month-close-reading"><Clock className="h-4 w-4 shrink-0" aria-hidden="true" />{t("business.overview.reading", { count: knownReview.reading })}</p> : null}
              {tasks.length === 0 && receiptsReviewed ? (
                <p className="mt-3 flex items-center gap-2 text-[16px] text-[var(--cuadrao-green)]" data-testid="month-close-checklist-ready">
                  <CircleCheck className="h-5 w-5 shrink-0" aria-hidden="true" />
                  {t("business.month_close.checklist_ready", { month: monthName, defaultValue: "Everything is ready to close {{month}}." })}
                </p>
              ) : tasks.length === 0 && !knownReview?.reading ? (
                <p data-testid="month-close-checklist-unknown" aria-label={t("business.month_close.figure_unknown", "Can't be calculated yet.")} className="mt-3 text-[16px] text-[#56635e] dark:text-white/70">
                  {UNKNOWN_VALUE}
                </p>
              ) : (
                <ul className="mt-2 divide-y divide-black/[0.06] dark:divide-white/[0.06]">
                  {tasks.map((task) => (
                    <li key={task.id} data-testid={`month-close-task-${task.id}`} className="py-2">
                      <div className="flex min-h-11 items-center gap-3">
                        <task.icon className={`h-5 w-5 shrink-0 ${(task.id === "fiscal" || task.id === "attention") ? "text-[#9e2f39] dark:text-[#ec9aa0]" : "text-[#735c14] dark:text-[#f6e7c1]"}`} aria-hidden="true" />
                        <div className="min-w-0 flex-1">
                          <p className="text-[16px] text-black dark:text-white">{task.text}</p>
                          {task.detail ? <p id={task.id === "fiscal" ? "month-close-fiscal-required" : undefined} className={`text-[14px] ${(task.id === "fiscal" || task.id === "attention") ? "text-[#9e2f39] dark:text-[#ec9aa0]" : "text-[#56635e] dark:text-white/70"}`}>{task.detail}</p> : null}
                        </div>
                        {task.id === "fiscal" ? (
                          <button
                            type="button"
                            aria-expanded={fiscalOpen}
                            aria-controls="month-close-blockers"
                            className={`${quietButtonClass} shrink-0 px-3`}
                            onClick={() => setFiscalOpen((value) => !value)}
                          >
                            {fiscalOpen ? t("business.month_close.action_hide", "Hide") : t("business.month_close.action_which", "Which ones")}
                            <ChevronDown className={`h-4 w-4 transition-transform motion-reduce:transition-none ${fiscalOpen ? "rotate-180" : ""}`} aria-hidden="true" />
                          </button>
                        ) : task.action ? (
                          <button type="button" className={`${quietButtonClass} shrink-0 px-3`} onClick={task.action.run}>
                            {task.action.label}
                            <ChevronRight className="h-4 w-4" aria-hidden="true" />
                          </button>
                        ) : null}
                      </div>
                      {task.id === "fiscal" && fiscalOpen ? (
                        <ul id="month-close-blockers" data-testid="month-close-blockers" className="mb-1 ml-8 space-y-1">
                          {blockers.map((blocker) => {
                            const document = documents.find((item) => item.id === blocker.documentId);
                            return document ? (
                              <li key={blocker.id} data-testid="month-close-blocker" data-blocker={blocker.kind} className="text-[14px] text-[#56635e] dark:text-white/70">
                                {blockerLabel(blocker, document, t)}
                              </li>
                            ) : null;
                          })}
                        </ul>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
              {showChecklistFooter ? <div data-testid="month-close-checklist-footer" className="mt-auto flex min-h-11 flex-wrap items-center justify-end gap-x-4 gap-y-2 border-t border-black/[0.06] pt-3 dark:border-white/[0.06]">
                {receiptStatus ? <div className="basis-full">{receiptStatus}</div> : null}
                {reason ? (
                  <p id="month-close-reason" data-testid="month-close-reason" className="min-w-0 flex-1 text-[14px] text-[#56635e] dark:text-white/70">{reason}</p>
                ) : showFilingReady ? (
                  <p data-testid="month-close-filing" className="min-w-0 flex-1 text-[14px] text-[#56635e] dark:text-white/70">{t("business.month_close.filing_ready", "You already have everything for the 606 and the 607. Close the month when you finish marking what was collected and what was paid.")}</p>
                ) : showStepsNote ? (
                  <p data-testid="month-close-steps-note" className="min-w-0 flex-1 text-right text-[14px] text-[#56635e] dark:text-white/70">{t("business.month_close.close_after_steps", { count: tasks.length, month: monthName, defaultValue: "When you finish the {{count}} steps, you can close {{month}}." })}</p>
                ) : null}
                {showClose ? (
                  <button type="button" data-testid="month-close-close" className={primaryButtonClass} onClick={() => setConfirming(true)}>
                    {t("business.month_close.close_named", { month: monthName, defaultValue: "Close {{month}}" })}
                  </button>
                ) : null}
              </div> : null}
            </section>
          )}

          <section aria-label={shownCurrency ? t("business.month_close.subtitle_in", { currency: currencySymbol(shownCurrency), defaultValue: "Income, expenses, and ITBIS for the month in {{currency}}." }) : t("business.month_close.subtitle", "Income, expenses, and ITBIS for the month.")} data-testid="month-close-cards" data-currency={shownCurrency ?? undefined} data-loading={phase === "loading" ? "true" : undefined} className={`grid gap-4 tablet:gap-6 ${WIDE.cards}`}>
            {manyCurrencies ? (
              <div className={WIDE.full}>
                <MonthCurrencyMenu currencies={currencies} value={shownCurrency} businessCurrency={businessCurrency} onChoose={(next) => { if (scopeKey !== null) setCurrencyView(scopeKey, next); }} />
              </div>
            ) : null}
            <div data-testid="month-close-cards-month" className={`${cardClass} grid grid-cols-2 gap-x-4 gap-y-5`}>
            {figure("month-close-income", t("business.month_close.income_label", "Income"), figures.income.state, figures.income.value, figures.income.state === "pending" ? t("business.month_close.figure_unknown", "Can't be calculated yet.") : undefined)}
            {figure("month-close-expenses", t("business.month_close.expense_label", "Expenses"), figures.expenses.state, figures.expenses.value, figures.expenses.state === "pending" ? t("business.month_close.figure_unknown", "Can't be calculated yet.") : undefined)}
            </div>
            {/* The gap is twice the card's padding plus the 24px between Por cobrar and Por pagar, so these two figures sit on those cards' columns. */}
            <div data-testid="month-close-cards-result" className={`${cardClass} grid grid-cols-2 gap-x-4 gap-y-5 ${WIDE.resultGap}`}>
            {figure(
              "month-close-net",
              t("business.month_close.net_label", "Net result"),
              net.state,
              net.state === "final" ? net.net_before_itbis : "",
              net.state === "pending"
                ? net.reason === "documents"
                  ? manyCurrencies
                    ? t("business.month_close.net_waits_in", { count: net.pending_count, currency: currencySymbol(shownCurrency), defaultValue: "{{count}} documents in {{currency}} left to mark" })
                    : t("business.month_close.net_waits", { count: net.pending_count, defaultValue: "{{count}} documents left to mark" })
                  : t("business.month_close.figure_unknown", "Can't be calculated yet.")
                : undefined,
            )}
            {figure(
              "month-close-itbis",
              itbis.credit ? t("business.month_close.itbis_credit_label", "ITBIS balance in your favor") : t("business.month_close.itbis_label", "ITBIS to pay"),
              itbis.state,
              itbis.value,
              itbis.state === "pending"
                ? t("business.month_close.figure_unknown", "Can't be calculated yet.")
                : <>{t("business.month_close.itbis_cobrado", "ITBIS collected")} <span data-testid="month-close-itbis-cobrado" className="cuadrao-amount tabular-nums">{shown?.itbis_cobrado && shownCurrency ? formatMoney(shown.itbis_cobrado, shownCurrency, locale) : UNKNOWN_VALUE}</span></>,
            )}
            </div>
          </section>

          {headingAction ? null : moneySection()}

          {locked ? <div className={WIDE.full}>{renderList("month-close-rows", t("business.month_close.locked_title", "Documents in this month"), lockedRows, "", "closed")}</div> : null}
        </>
      )}
      {headingAction ? moneySection() : null}

      <ConfirmDialog
        isOpen={confirming}
        tone="primary"
        title={t("business.month_close.close_confirm_title", "Close this month?")}
        description={t("business.month_close.close_confirm_body", "The month becomes read-only. Statuses cannot be changed.")}
        confirmLabel={t("business.month_close.close_confirm_action", "Yes, close the month")}
        cancelLabel={t("business.month_close.close_back", "Back")}
        isBusy={busyClose}
        error={closeProblem}
        onCancel={() => { if (!busyClose) { setConfirming(false); setCloseProblem(null); } }}
        onConfirm={() => void confirmClose()}
      />
    </div>
    </div>
  );
}

export type MonthCloseSource = { client: MonthCloseClient; scopeKey: string | null };

/** The month close the selected Business reads. One per view, so the sample books Inicio closes are the books its export sees. */
// One sample book per sample source, so Inicio and an export opened from the top bar see the same closed months.
const SAMPLE_CLIENTS = new WeakMap<object, MonthCloseClient>();
function sampleClientFor(source: object, empty = false): MonthCloseClient {
  const known = SAMPLE_CLIENTS.get(source);
  if (known) return known;
  // `?currencies=two` on the preview adds dollar documents to the open month.
  const dollars = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("currencies") === "two";
  const made = createMockMonthCloseClient({ dollars, empty });
  SAMPLE_CLIENTS.set(source, made);
  return made;
}

export function useMonthCloseSource(): MonthCloseSource {
  const { chosen, source, spaces } = useBusiness();
  // One key per Business, known before the first load: the own Business is "own" before and after the list arrives.
  const scopeKey = spaces === null ? null : chosen && (chosen.role !== "owner" || chosen.space_id?.startsWith(LOCAL_BUSINESS_PREFIX)) ? chosen.grant_id : "own";
  return { client: source.mode === "fixture" ? sampleClientFor(source, chosen?.space_id?.startsWith(LOCAL_BUSINESS_PREFIX)) : monthCloseClient, scopeKey };
}

export default function BusinessMonthClosePanel({ monthClose, onMonthChange, review, header, headingAction }: { monthClose: MonthCloseSource; onMonthChange?: (month: string) => void; review?: MonthCloseReview | null; header?: (switcher: ReactNode) => ReactNode; headingAction?: ReactNode }) {
  const { chosen, actions, openPanel, records } = useBusiness();
  const add = canAddRecords(chosen) ? actions.create.find((action) => action.id === "upload_receipt") : undefined;
  // An open item carries only its activity id. A receipt's is its saved expense's id; an invoice has no record screen yet.
  const openDocument = (document: MonthCloseDocument) => (document.kind === "receipt" ? () => openPanel({ kind: "expense", expenseId: document.id }) : null);
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
      businessCurrency={businessWorkspaceCurrency(records?.workspace)}
    />
  );
}
