"use client";

import { useContext, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, BadgeCheck, Check, ChevronLeft, ChevronRight, CircleCheck, Clock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import {
  calendarDay,
  canCloseMonth,
  canStepMonth,
  createMockMonthCloseClient,
  currentMonthKey,
  documentOverdue,
  documentsTotal,
  dueDistance,
  electronicNcf,
  fiscalNumberPresent,
  formatMonthLabel,
  itbisBalanceDisplay,
  monthCloseBlockers,
  monthCloseClient,
  monthCloseNetDisplay,
  monthCloseStatusView,
  monthCloseSummary,
  monthFilingNotice,
  monthPickerMonths,
  paperNcf,
  rncPresent,
  shiftMonthKey,
  windowForMonth,
  sortDocuments,
  type MonthCloseBlocker,
  type MonthCloseClient,
  type MonthCloseDocument,
  type MonthCloseSnapshot,
  type MonthCloseStatus,
} from "@/lib/business-month-close";
import { formatDay, formatMoney } from "./business-format";
import { cardClass, pillButtonClass, secondaryButtonClass } from "./business-ui";
import { BusinessContext, useBusiness } from "./BusinessWorkspace";
import { ReceiptPeriodExport } from "./ReceiptDossierReview";

const monthArrowClass =
  "inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-black/70 transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent dark:text-white/70 dark:hover:bg-white/5";

type ListFilter = "all" | "receivable" | "payable" | "overdue" | "matched";
type PreviewHold = "loading" | "empty" | "error";

function previewHold(): PreviewHold | null {
  if (typeof window === "undefined") return null;
  const value = new URLSearchParams(window.location.search).get("monthClose");
  if (value === "loading" || value === "empty" || value === "error") return value;
  return null;
}

export function MonthSwitcher({
  month,
  current,
  earliest,
  onMonth,
  headingId,
  openRequest = 0,
}: {
  month: string;
  current: string;
  earliest: string | null;
  onMonth: (month: string) => void;
  headingId: string;
  openRequest?: number;
}) {
  const { t } = useTranslation();
  const options = useMemo(() => monthPickerMonths(current, earliest), [current, earliest]);
  const [open, setOpen] = useState(false);
  const [seenRequest, setSeenRequest] = useState(0);
  const [active, setActive] = useState(0);
  const [position, setPosition] = useState({ left: 8, top: 48 });
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();
  const label = formatMonthLabel(month);

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
    <div className="flex items-center" data-testid="month-close-switcher">
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
      <h3 id={headingId} className="min-w-0 font-display font-medium">
        <button
          ref={buttonRef}
          type="button"
          data-testid="month-close-month"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={listId}
          className="inline-flex min-h-11 items-center rounded-full px-2 font-display text-[26px] font-medium leading-tight tracking-tight text-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40 dark:text-white"
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
      </h3>
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
          className="fixed z-[100] max-h-80 w-64 overflow-y-auto rounded-[16px] border border-black/10 bg-white p-1.5 shadow-lg focus-visible:outline-none dark:border-white/10 dark:bg-[var(--cuadrao-menu-surface)]"
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
                className={`flex min-h-11 items-center justify-between gap-2 rounded-[12px] px-3 font-display text-[15px] font-medium ${option.selectable ? "cursor-pointer text-black dark:text-white" : "cursor-not-allowed text-black/35 dark:text-white/30"} ${index === active ? "bg-black/5 dark:bg-white/5" : ""}`}
              >
                <span>{formatMonthLabel(option.month)}</span>
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
  const tone = overdue ? "bg-[#d66d75]/15 text-[#a8434c] dark:text-[#ec9aa0]" : CHIP_TONE[status];
  return (
    <span data-testid="month-close-status" data-status={overdue ? "vencida" : status} className={`inline-flex min-h-11 items-center gap-1 rounded-full px-3 text-[12px] font-medium ${tone}`}>
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {label}
    </span>
  );
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

function blockerLabel(blocker: MonthCloseBlocker, document: MonthCloseDocument, text: (key: string, fallback: string, options?: Record<string, unknown>) => string): string {
  if (blocker.kind === "missing_rnc") return text("business.month_close.blocker_rnc", "{{name}} has no RNC", { name: document.counterparty });
  return text("business.month_close.blocker_ncf", "{{name}} has no NCF or e-CF", { name: document.counterparty });
}

function figureCard(computed: string, override: string | null | undefined, hasFigures: boolean, pending: string): { state: "pending" | "final"; value: string } {
  if (!hasFigures) return { state: "final", value: computed };
  if (override === null || override === undefined) return { state: "pending", value: pending };
  return { state: "final", value: override };
}

function itbisCard(
  computed: string,
  override: string | null | undefined,
  hasFigures: boolean,
  pending: string,
): { state: "pending" | "final"; value: string; credit: boolean } {
  const figure = figureCard(computed, override, hasFigures, pending);
  if (figure.state !== "final") return { state: "pending", value: figure.value, credit: false };
  const balance = itbisBalanceDisplay(figure.value);
  if (balance.kind === "credit") return { state: "final", value: balance.amount, credit: true };
  return { state: "final", value: figure.value, credit: false };
}

function SummaryCard({
  testId,
  label,
  value,
  hint,
  locale,
  state,
  amount,
}: {
  testId: string;
  label: string;
  /** Money string, or the pending word. Never both. */
  value: string;
  hint: string;
  locale: string;
  state?: "pending" | "final";
  amount?: string;
}) {
  const money = state !== "pending";
  return (
    <article className={cardClass} data-testid={testId} data-layout="summary" data-state={state} data-amount={money ? amount ?? value : undefined}>
      <p className={`font-display text-[24px] font-medium leading-tight tracking-tight text-black dark:text-white ${money ? "tabular-nums" : ""}`}>
        {money ? formatMoney(value, "DOP", locale) : value}
      </p>
      <h4 className="mt-2 text-[15px] font-medium text-black dark:text-white">{label}</h4>
      <p className="mt-1 text-[13px] text-black/55 dark:text-white/55">{hint}</p>
    </article>
  );
}

export function BusinessMonthCloseView({
  client,
  scopeKey = "default",
  canMutate = true,
  now,
}: {
  client: MonthCloseClient;
  /** Selected Business grant. A change reloads this snapshot and keeps the mock's books apart. */
  scopeKey?: string;
  /** Close and settlement marks follow the grant's approve capability. */
  canMutate?: boolean;
  /** Clock for the current month. Tests pin it; Inicio uses today. */
  now?: Date;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const workspace = useContext(BusinessContext);
  const [clock] = useState(() => now ?? new Date());
  const currentMonth = currentMonthKey(clock);
  const today = calendarDay(clock);
  const preview = previewHold();
  const [month, setMonth] = useState(currentMonth);
  const bounds = windowForMonth(month);
  const [snapshot, setSnapshot] = useState<MonthCloseSnapshot | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  const [filter, setFilter] = useState<ListFilter>("all");
  const [pickerRequest, setPickerRequest] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const [busyClose, setBusyClose] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [pendingIds, setPendingIds] = useState<ReadonlySet<string>>(() => new Set());
  const inFlight = useRef(new Set<string>());
  const generation = useRef(0);

  useEffect(() => {
    const request = ++generation.current;
    const held = preview === "loading" || preview === "error";
    setPhase(preview === "error" ? "error" : "loading");
    setConfirming(false);
    if (held) {
      setSnapshot(null);
      return;
    }
    client.load(month, scopeKey).then(
      (next) => {
        if (generation.current !== request) return;
        setSnapshot(preview === "empty" ? { ...next, documents: [] } : next);
        setPhase("ready");
      },
      () => {
        if (generation.current !== request) return;
        setPhase("error");
      },
    );
  }, [attempt, client, month, preview, scopeKey]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(timer);
  }, [toast]);

  const summary = snapshot ? monthCloseSummary(snapshot.documents) : null;
  const itbis = snapshot && summary
    ? itbisCard(summary.itbis_owed, snapshot.figures?.itbis_owed, Boolean(snapshot.figures), t("business.month_close.pending_label", "Pending"))
    : null;
  const filingNotice = snapshot ? monthFilingNotice(snapshot) : false;
  const listedBlockers = snapshot ? snapshot.blockers ?? monthCloseBlockers(snapshot.documents) : [];
  const blockers = listedBlockers.filter((blocker) => blocker.kind === "missing_rnc" || blocker.kind === "missing_ncf");
  const net = snapshot ? monthCloseNetDisplay(snapshot.documents, listedBlockers, snapshot.figures ? snapshot.figures.net_before_itbis : undefined) : null;
  const gate = snapshot ? canCloseMonth(snapshot) : { ok: false as const, reason: "not_calendar_month" as const };
  const locked = Boolean(snapshot?.closed_at);
  const statusLabel = (status: MonthCloseStatus) =>
    ({
      pendiente: t("business.month_close.status_pendiente", "Pending"),
      cobrado: t("business.month_close.status_cobrado", "Collected"),
      pagado: t("business.month_close.status_pagado", "Paid"),
    })[status];
  const countLabel = (count: number) => t("business.month_close.documents", { count });
  function dueLabel(document: MonthCloseDocument): string | null {
    if (!document.due_on) return null;
    const distance = dueDistance(document.due_on, today);
    if (!distance) return null;
    if (distance.direction === "today") return t("business.month_close.due_today", "Today");
    if (distance.direction === "past") return t("business.month_close.due_past", { count: distance.days });
    return t("business.month_close.due_future", { count: distance.days });
  }

  async function mark(document: MonthCloseDocument) {
    if (!canMutate || !snapshot || snapshot.closed_at || phase === "loading" || document.status !== "pendiente" || inFlight.current.has(document.id)) return;
    const started = generation.current;
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
    try {
      const saved = document.kind === "invoice" ? await client.markCobrado(documentId, scopeKey, today) : await client.markPagado(documentId, scopeKey, today);
      if (started !== generation.current) return;
      setSnapshot((current) => (current ? { ...current, documents: current.documents.map((item) => (item.id === documentId ? { ...item, status: saved.status } : item)) } : current));
    } catch {
      if (started !== generation.current) return;
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
      setToast(t("business.month_close.mark_failed", "We couldn't save that change. The status is back to what it was."));
    } finally {
      inFlight.current.delete(documentId);
      setPendingIds((current) => {
        const next = new Set(current);
        next.delete(documentId);
        return next;
      });
    }
  }

  async function confirmClose() {
    if (!canMutate || !snapshot?.month || busyClose) return;
    setBusyClose(true);
    try {
      const next = await client.closeMonth(snapshot.month, scopeKey);
      setSnapshot(next);
      setConfirming(false);
    } catch {
      setToast(t("business.month_close.close_failed", "We couldn't close the month. Try again."));
    } finally {
      setBusyClose(false);
    }
  }

  function scrollToDocument(documentId: string) {
    const row = document.getElementById(`month-close-row-${documentId}`);
    row?.scrollIntoView({ block: "center" });
    row?.focus();
  }

  const reason = !canMutate
    ? t("business.month_close.reason_permission", "Marking collection, marking payment, and closing the month requires approval permission.")
    : !snapshot || gate.ok
    ? ""
    : gate.reason === "not_calendar_month"
      ? t("business.month_close.reason_not_month", "Choose a calendar month to close it.")
      : gate.reason === "closed"
        ? ""
        : t("business.month_close.reason_blockers", "A document is missing its RNC or NCF.");

  const documents = snapshot?.documents ?? [];
  const overdueNow = (document: MonthCloseDocument) => documentOverdue(document, today);
  const receivable = sortDocuments(documents.filter((document) => document.kind === "invoice" && document.status === "pendiente" && !overdueNow(document)), "newest");
  const payable = sortDocuments(documents.filter((document) => document.kind === "receipt" && document.status === "pendiente" && !overdueNow(document)), "newest");
  const overdueRows = sortDocuments(documents.filter(overdueNow), "newest");
  const matchedRows = sortDocuments(
    documents.filter((document) => document.status !== "pendiente" && rncPresent(document.rnc) && fiscalNumberPresent(document)),
    "newest",
  );
  const fiscalGaps = sortDocuments(
    documents.filter((document) => document.status !== "pendiente" && !pendingIds.has(document.id) && (!rncPresent(document.rnc) || !fiscalNumberPresent(document))),
    "newest",
  );
  const lockedRows = locked ? sortDocuments(documents, "newest") : [];
  const statusView = snapshot?.figures?.by_status ? monthCloseStatusView(snapshot.figures.by_status) : null;
  const noDocuments = statusView ? !statusView.any_documents : documents.length === 0;
  const rowGrid = "tablet:grid tablet:grid-cols-[7.5rem_minmax(0,1.4fr)_6.5rem_7rem_auto] tablet:items-center tablet:gap-3";

  function renderRow(document: MonthCloseDocument, layout: "pending" | "overdue" | "closed" = "pending") {
    const overdue = overdueNow(document);
    const pending = canMutate && document.status === "pendiente" && !locked;
    const relative = dueLabel(document);
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
        className={`flex flex-col gap-3 px-4 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/50 ${rowGrid}`}
      >
        <StatusChip status={document.status} overdue={overdue} label={overdue ? t("business.month_close.status_vencida", "Overdue") : statusLabel(document.status)} />
        <div className="min-w-0">
          <span className="block text-[12px] text-black/45 dark:text-white/45">
            {document.kind === "invoice" ? t("business.month_close.kind_invoice", "Invoice") : t("business.month_close.kind_receipt", "Expense")}
          </span>
          <span className="block truncate text-[15px] font-medium text-black dark:text-white">{document.counterparty}</span>
          <span className="mt-1 block text-[13px] text-black/60 dark:text-white/60">{fiscalLine(document, t)}</span>
        </div>
        <div>
          <time dateTime={document.due_on ?? document.occurred_on} className="block text-[14px] text-black/70 dark:text-white/70">
            {formatDay(document.due_on ?? document.occurred_on, locale)}
          </time>
          {relative ? <span className="mt-1 block text-[12px] text-black/50 dark:text-white/50">{relative}</span> : null}
        </div>
        <div>
          <span className="text-[15px] font-medium tabular-nums text-black dark:text-white">{formatMoney(document.amount, document.currency, locale)}</span>
          {document.itbis ? <span className="mt-1 block text-[12px] tabular-nums text-black/50 dark:text-white/50">{t("business.month_close.itbis_line", "ITBIS {{amount}}", { amount: formatMoney(document.itbis, document.currency, locale) })}</span> : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {pending ? (
            <button
              type="button"
              data-testid={document.kind === "invoice" ? "month-close-mark-cobrado" : "month-close-mark-pagado"}
              className={`${secondaryButtonClass} min-w-11 px-3.5`}
              disabled={pendingIds.has(document.id) || phase === "loading"}
              aria-label={document.kind === "invoice"
                ? t("business.month_close.mark_cobrado_named", "Mark {{name}} collected", { name: document.counterparty })
                : t("business.month_close.mark_pagado_named", "Mark {{name}} paid", { name: document.counterparty })}
              onClick={() => void mark(document)}
            >
              {document.kind === "invoice" ? t("business.month_close.mark_cobrado", "Mark collected") : t("business.month_close.mark_pagado", "Mark paid")}
            </button>
          ) : null}
        </div>
      </li>
    );
  }

  function renderMatched(document: MonthCloseDocument) {
    return (
      <li
        key={document.id}
        id={`month-close-row-${document.id}`}
        tabIndex={-1}
        data-testid="month-close-row"
        data-document-id={document.id}
        data-kind={document.kind}
        data-status={document.status}
        data-layout="matched"
        data-locked={locked ? "true" : "false"}
        className="flex min-h-12 items-center gap-3 px-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/50"
      >
        <Check className="h-4 w-4 shrink-0 text-[var(--cuadrao-green)]" aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate text-[15px] font-medium text-black dark:text-white">{document.counterparty}</span>
        <time dateTime={document.occurred_on} className="shrink-0 text-[13px] text-black/55 dark:text-white/55">{formatDay(document.occurred_on, locale)}</time>
        <span className="shrink-0 text-[15px] font-medium tabular-nums text-black dark:text-white">{formatMoney(document.amount, document.currency, locale)}</span>
        <StatusChip status={document.status} label={statusLabel(document.status)} />
      </li>
    );
  }

  function renderList(testId: string, title: string, rows: MonthCloseDocument[], empty: string, layout: "pending" | "overdue" | "matched" | "closed" = "pending") {
    const listClass = "mt-2 divide-y divide-black/[0.06] overflow-hidden rounded-[20px] border border-black/[0.06] bg-white dark:divide-white/[0.06] dark:border-white/[0.06] dark:bg-[#1f2225]";
    return (
      <section aria-labelledby={`${testId}-title`} data-testid={testId} data-layout={layout} className="mt-6">
        <h4 id={`${testId}-title`} className="text-[15px] font-medium text-black dark:text-white">{title}</h4>
        {rows.length === 0 ? (
          <p className="mt-2 text-[14px] text-black/60 dark:text-white/60" data-testid={`${testId}-empty`}>{empty}</p>
        ) : layout === "matched" ? (
          <ul className={listClass}>{rows.map(renderMatched)}</ul>
        ) : (
          <div className={listClass}>
            <div className={`hidden min-h-11 border-b border-black/[0.06] px-4 text-[12px] text-black/45 dark:border-white/[0.06] dark:text-white/45 tablet:grid ${rowGrid}`} aria-hidden="true">
              <span>{t("business.month_close.column_status", "Status")}</span>
              <span>{t("business.month_close.column_counterparty", "Counterparty")}</span>
              <span>{t("business.month_close.column_due", "Due")}</span>
              <span>{t("business.month_close.column_amount", "Amount")}</span>
              <span />
            </div>
            <ul className="divide-y divide-black/[0.06] dark:divide-white/[0.06]">{rows.map((document) => renderRow(document, layout === "overdue" ? "overdue" : layout === "closed" ? "closed" : "pending"))}</ul>
          </div>
        )}
      </section>
    );
  }

  function stateCard(testId: string, next: ListFilter, label: string, rows: MonthCloseDocument[], totals?: { count: number; amount: string }) {
    const pressed = filter === next;
    const amount = totals?.amount ?? documentsTotal(rows);
    const count = totals?.count ?? rows.length;
    return (
      <button
        type="button"
        data-testid={testId}
        aria-pressed={pressed}
        onClick={() => setFilter((current) => (current === next ? "all" : next))}
        className={`${cardClass} min-h-11 w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40 ${pressed ? "ring-2 ring-[var(--cuadrao-green)]" : ""}`}
      >
        <p className="font-display text-[24px] font-medium leading-tight tracking-tight tabular-nums text-black dark:text-white">{formatMoney(amount, "DOP", locale)}</p>
        <span className="mt-2 block text-[15px] font-medium text-black dark:text-white">{label}</span>
        <span className="mt-1 block text-[13px] text-black/55 dark:text-white/55">{countLabel(count)}</span>
      </button>
    );
  }

  const loadingBar = "rounded-md bg-black/[0.06] dark:bg-white/[0.08]";

  return (
    <section aria-labelledby="month-close-title" aria-busy={phase === "loading" ? true : undefined} data-testid="month-close" data-closed={locked ? "true" : "false"} className="mb-8">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <MonthSwitcher
            month={month}
            current={currentMonth}
            earliest={snapshot?.earliest_month ?? null}
            onMonth={setMonth}
            headingId="month-close-title"
            openRequest={pickerRequest}
          />
          <p className="mt-1 px-2 text-[13px] text-black/55 dark:text-white/55">{t("business.month_close.subtitle", "Income, expenses, and ITBIS for the month.")}</p>
        </div>
        <div className="flex flex-col items-stretch gap-2 tablet:items-end">
          {locked && snapshot?.closed_at ? (
            <p role="status" data-testid="month-close-closed" className="text-[14px] font-medium text-[var(--cuadrao-green)]">
              {t("business.month_close.closed", "Month closed")}
              <span className="mt-0.5 block text-[13px] font-normal text-black/60 dark:text-white/60">
                {t("business.month_close.closed_on", "Closed on {{date}}.", { date: formatDay(snapshot.closed_at.slice(0, 10), locale) })}
              </span>
            </p>
          ) : (
            <>
              <button
                type="button"
                data-testid="month-close-close"
                className={`${secondaryButtonClass} min-w-11`}
                disabled={!canMutate || !gate.ok}
                aria-describedby={reason ? "month-close-reason" : undefined}
                onClick={() => setConfirming(true)}
              >
                {t("business.month_close.close", "Close month")}
              </button>
              {reason ? (
                <p id="month-close-reason" data-testid="month-close-reason" className="max-w-sm text-[13px] text-black/70 dark:text-white/70">
                  {reason}
                </p>
              ) : null}
              {filingNotice ? (
                <p data-testid="month-close-filing" className="max-w-sm text-[13px] text-black/70 dark:text-white/70">
                  <span data-testid="month-close-filing-status" className="block text-[14px] font-medium text-black dark:text-white">
                    {t("business.month_close.status_pendiente", "Pending")}
                  </span>
                  <span data-testid="month-close-filing-line" className="mt-0.5 block">
                    {t("business.month_close.filing_ready", "You already have everything for the 606 and the 607. Close the month when you finish marking what was collected and what was paid.")}
                  </span>
                </p>
              ) : null}
            </>
          )}
        </div>
      </div>

      {client.mode === "mock" ? (
        <p role="note" data-testid="month-close-sample" className="mb-5 rounded-[14px] border border-dashed border-[#c2a44d]/60 bg-[#c2a44d]/10 px-4 py-2.5 text-[13px] text-black/70 dark:text-white/70">
          {t("business.month_close.sample", "Sample figures. These are not your records and nothing is saved.")}
        </p>
      ) : null}

      {phase === "error" ? (
        <div role="alert" data-testid="month-close-error" data-layout="error" className="flex flex-col items-center justify-center gap-4 py-16 text-center">
          <h4 className="font-display text-[18px] font-medium text-black dark:text-white">{t("business.month_close.error_title", "We couldn't load the month")}</h4>
          <button type="button" className={`${secondaryButtonClass} min-w-11`} onClick={() => setAttempt((value) => value + 1)}>
            {t("business.month_close.retry", "Try again")}
          </button>
        </div>
      ) : !snapshot || !summary || !net ? (
        <div role="status" data-testid="month-close-loading" data-layout="loading" aria-busy="true">
          <span className="sr-only">{t("business.month_close.loading", "Loading the month")}</span>
          <div aria-hidden="true" className="animate-pulse motion-reduce:animate-none">
            <div className="grid grid-cols-1 gap-3 tablet:grid-cols-2 desktop:grid-cols-4">
              {Array.from({ length: 4 }, (_, index) => (
                <div key={index} className={cardClass} data-testid="month-close-loading-card">
                  <div className={`${loadingBar} h-8 w-32`} />
                  <div className={`${loadingBar} mt-3 h-4 w-24`} />
                  <div className={`${loadingBar} mt-2 h-3 w-28`} />
                </div>
              ))}
            </div>
            <div className="mt-6 overflow-hidden rounded-[20px] border border-black/[0.06] bg-white dark:border-white/[0.06] dark:bg-[#1f2225]">
              {Array.from({ length: 6 }, (_, index) => (
                <div key={index} data-testid="month-close-loading-row" className="flex min-h-11 items-center gap-3 border-b border-black/[0.06] px-4 last:border-b-0 dark:border-white/[0.06]">
                  <div className={`${loadingBar} h-4 w-16`} />
                  <div className={`${loadingBar} h-4 min-w-0 flex-1`} />
                  <div className={`${loadingBar} h-4 w-16 shrink-0`} />
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <>
          {phase === "loading" ? <p role="status" data-testid="month-close-refreshing" className="sr-only">{t("business.month_close.loading", "Loading the month")}</p> : null}
          <div className="grid grid-cols-1 gap-3 tablet:grid-cols-2 desktop:grid-cols-4" data-testid="month-close-cards" data-loading={phase === "loading" ? "true" : undefined}>
            <SummaryCard testId="month-close-income" label={t("business.month_close.income_label", "Income")} {...figureCard(summary.income_before_itbis, snapshot.figures?.income_before_itbis, Boolean(snapshot.figures), t("business.month_close.pending_label", "Pending"))} hint={t("business.month_close.income_hint", "Invoice totals before ITBIS.")} locale={locale} />
            <SummaryCard testId="month-close-expenses" label={t("business.month_close.expense_label", "Expenses")} {...figureCard(summary.expense_before_itbis, snapshot.figures?.expense_before_itbis, Boolean(snapshot.figures), t("business.month_close.pending_label", "Pending"))} hint={t("business.month_close.expense_hint", "Expense totals before ITBIS.")} locale={locale} />
            <SummaryCard
              testId="month-close-net"
              label={t("business.month_close.net_label", "Net result")}
              state={net.state}
              value={net.state === "final" ? net.net_before_itbis : t("business.month_close.pending_label", "Pending")}
              hint={net.state === "pending"
                ? (net.reason === "documents"
                  ? t("business.month_close.pending_reason", "{{count}} documents still pending", { count: net.pending_count })
                  : t("business.month_close.pending_label", "Pending"))
                : t("business.month_close.net_hint", "Income minus expenses, before ITBIS.")}
              locale={locale}
            />
            {itbis ? (
              <SummaryCard
                testId="month-close-itbis"
                label={itbis.credit ? t("business.month_close.itbis_credit_label", "ITBIS balance in your favor") : t("business.month_close.itbis_label", "ITBIS to pay")}
                state={itbis.state}
                value={itbis.value}
                hint={itbis.credit
                  ? t("business.month_close.itbis_credit_line", "This month you paid more ITBIS than you collected. That difference normally stays as a balance in your favor for the coming months. Your accountant confirms it on the IT-1.")
                  : t("business.month_close.itbis_hint", "ITBIS on invoices minus ITBIS on expenses.")}
                locale={locale}
              />
            ) : null}
          </div>

          {blockers.length > 0 ? (
            <section aria-labelledby="month-close-blockers-title" data-testid="month-close-blockers" className="mt-5 rounded-[20px] border border-[#c2a44d]/50 bg-[#f4ead2]/40 p-4 dark:border-[#c2a44d]/40 dark:bg-[#4a3d1c]/40">
              <h4 id="month-close-blockers-title" className="flex items-center gap-2 text-[14px] font-medium text-[#3f3414] dark:text-[#f6e7c1]">
                <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
                {t("business.month_close.blockers_title", "Before you close")}
              </h4>
              <ul className="mt-2 space-y-1">
                {blockers.map((blocker) => {
                  const document = snapshot.documents.find((item) => item.id === blocker.documentId);
                  if (!document) return null;
                  return (
                    <li key={blocker.id}>
                      <a
                        href={`#month-close-row-${document.id}`}
                        data-testid="month-close-blocker"
                        data-blocker={blocker.kind}
                        className="inline-flex min-h-11 items-center text-[14px] text-[#3f3414] underline decoration-[#3f3414]/40 underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3f3414]/40 dark:text-[#f6e7c1] dark:decoration-[#f6e7c1]/40"
                        onClick={(event) => {
                          event.preventDefault();
                          scrollToDocument(document.id);
                        }}
                      >
                        {blockerLabel(blocker, document, t)}
                      </a>
                    </li>
                  );
                })}
              </ul>
            </section>
          ) : null}

          {noDocuments ? (
            <div data-testid="month-close-empty" data-layout="empty" className="flex items-center justify-center">
              <div className="flex flex-col items-center py-16 text-center">
                <h4 className="font-display text-[18px] font-medium text-black dark:text-white">{t("business.month_close.empty_title", "This month has no documents")}</h4>
                <p className="mt-2 max-w-sm text-[14px] text-black/60 dark:text-white/60">{t("business.month_close.empty", "No invoices or expenses in this month.")}</p>
                <button type="button" data-testid="month-close-empty-action" className={`${secondaryButtonClass} mt-6 min-w-11`} onClick={() => setPickerRequest((value) => value + 1)}>
                  {t("business.month_close.choose_month", "Choose month")}
                </button>
              </div>
            </div>
          ) : locked ? (
            renderList("month-close-rows", t("business.month_close.locked_title", "Documents in this month"), lockedRows, "", "closed")
          ) : (
            <>
              <div className="mt-4 grid grid-cols-1 gap-3 tablet:grid-cols-2 desktop:grid-cols-4" data-testid="month-close-states">
                {stateCard("month-close-state-receivable", "receivable", t("business.month_close.receivable_title", "To collect"), receivable)}
                {stateCard("month-close-state-overdue", "overdue", t("business.month_close.filter_overdue", "Overdue"), overdueRows)}
                {statusView
                  ? stateCard("month-close-state-matched", "matched", t("business.month_close.filter_matched", "Collected and paid"), matchedRows, { count: statusView.settled_count, amount: statusView.settled_before_itbis })
                  : snapshot.figures
                    ? null
                    : stateCard("month-close-state-matched", "matched", t("business.month_close.filter_matched", "Collected and paid"), matchedRows)}
                {stateCard("month-close-state-payable", "payable", t("business.month_close.payable_title", "To pay"), payable)}
              </div>
              {filter === "overdue" ? renderList("month-close-overdue", t("business.month_close.filter_overdue", "Overdue"), overdueRows, t("business.month_close.overdue_empty", "Nothing overdue."), "overdue") : null}
              {filter === "matched" ? renderList("month-close-matched", t("business.month_close.matched_title", "Collected and paid"), [...matchedRows, ...fiscalGaps], t("business.month_close.matched_empty", "Nothing collected or paid."), "matched") : null}
              {filter === "receivable" ? renderList("month-close-receivable", t("business.month_close.receivable_title", "To collect"), receivable, t("business.month_close.receivable_empty", "Nothing to collect.")) : null}
              {filter === "payable" ? renderList("month-close-payable", t("business.month_close.payable_title", "To pay"), payable, t("business.month_close.payable_empty", "Nothing to pay.")) : null}
              {filter === "all" ? (
                <>
                  {renderList("month-close-receivable", t("business.month_close.receivable_title", "To collect"), receivable, t("business.month_close.receivable_empty", "Nothing to collect."))}
                  {renderList("month-close-payable", t("business.month_close.payable_title", "To pay"), payable, t("business.month_close.payable_empty", "Nothing to pay."))}
                  {overdueRows.length > 0 ? renderList("month-close-overdue", t("business.month_close.filter_overdue", "Overdue"), overdueRows, "", "overdue") : null}
                  {matchedRows.length > 0 ? renderList("month-close-matched", t("business.month_close.matched_title", "Collected and paid"), matchedRows, "", "matched") : null}
                  {fiscalGaps.length > 0 ? renderList("month-close-fiscal-gaps", t("business.month_close.fiscal_gaps_title", "Missing RNC or NCF"), fiscalGaps, "") : null}
                </>
              ) : null}
            </>
          )}
        </>
      )}

      {confirming ? (
        <AdaptivePanel
          title={t("business.month_close.close_confirm_title", "Close this month?")}
          closeLabel={t("business.month_close.close_back", "Back")}
          onClose={() => setConfirming(false)}
          footer={
            <button type="button" data-testid="month-close-confirm" className={`${pillButtonClass} bg-[var(--cuadrao-green)] text-[var(--cuadrao-cream)]`} disabled={busyClose} onClick={() => void confirmClose()}>
              {t("business.month_close.close_confirm_action", "Yes, close the month")}
            </button>
          }
        >
          <p className="px-5 py-4 text-[14px] text-black/70 dark:text-white/70">{t("business.month_close.close_confirm_body", "The month becomes read-only. Statuses cannot be changed.")}</p>
        </AdaptivePanel>
      ) : null}

      {toast ? (
        <div role="alert" data-testid="month-close-toast" className="fixed inset-x-4 bottom-24 z-[60] mx-auto max-w-md rounded-[14px] bg-black px-4 py-3 text-[13px] text-white shadow-lg dark:bg-white dark:text-black">
          {toast}
        </div>
      ) : null}

      {workspace?.chosen && bounds.to ? (
        <div className="mt-6">
          <ReceiptPeriodExport
            key={`${workspace.chosen.grant_id}:${bounds.from}:${bounds.to}`}
            scope={{
              name: workspace.chosen.name,
              capabilities: workspace.chosen.capabilities,
              grantId: workspace.chosen.role === "owner" ? null : workspace.chosen.grant_id,
            }}
            start={bounds.from}
            end={bounds.to}
            available={workspace.source.mode === "live"}
          />
        </div>
      ) : null}
    </section>
  );
}

export default function BusinessMonthClosePanel() {
  const { chosen, source } = useBusiness();
  const [sampleClient] = useState(() => createMockMonthCloseClient());
  const client = source.mode === "fixture" ? sampleClient : monthCloseClient;
  return (
    <BusinessMonthCloseView
      client={client}
      scopeKey={chosen?.grant_id ?? "own"}
      canMutate={Boolean(chosen?.capabilities.includes("approve"))}
    />
  );
}
