"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, BadgeCheck, Check, ChevronDown, ChevronLeft, ChevronRight, CircleCheck, Clock, FileWarning, Inbox } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
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
  monthPickerMonths,
  paperNcf,
  rncPresent,
  shiftMonthKey,
  sortDocuments,
  type MonthCloseBlocker,
  type MonthCloseClient,
  type MonthCloseDocument,
  type MonthCloseSnapshot,
  type MonthCloseStatus,
} from "@/lib/business-month-close";
import { formatDay, formatMoney } from "./business-format";
import { cardClass, pillButtonClass, secondaryButtonClass } from "./business-ui";
import { useBusiness } from "./BusinessWorkspace";
import { showToast } from "./foundation/toasts";
import { EmptyState } from "./foundation/EmptyState";

const monthArrowClass =
  "inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-black/70 transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent dark:text-white/70 dark:hover:bg-white/5";

/** Rows each money column shows before "Ver más". */
const MONEY_ROWS = 3;
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

export function BusinessMonthCloseView({
  client,
  scopeKey = "default",
  canMutate = true,
  now,
  onMonthChange,
  review,
  onAdd,
}: {
  client: MonthCloseClient;
  /** Selected Business grant. A change reloads this snapshot and keeps the mock's books apart; null holds the load until the Business is known. */
  scopeKey?: string | null;
  /** Close and settlement marks follow the grant's approve capability. */
  canMutate?: boolean;
  /** Clock for the current month. Tests pin it; Inicio uses today. */
  now?: Date;
  /** Told each time the owner moves to another month. */
  onMonthChange?: (month: string) => void;
  /** Receipts waiting in the Bandeja, the checklist's first line; null while unknown. */
  review?: { count: number; detail: string | null; open: () => void } | null;
  /** Opens Agregar; an empty month offers it as its next step. */
  onAdd?: () => void;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const [clock] = useState(() => now ?? new Date());
  const currentMonth = currentMonthKey(clock);
  const today = calendarDay(clock);
  const preview = previewHold();
  const [month, setMonth] = useState(currentMonth);
  const [snapshot, setSnapshot] = useState<MonthCloseSnapshot | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set());
  const [fiscalOpen, setFiscalOpen] = useState(false);
  const [pickerRequest, setPickerRequest] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const [busyClose, setBusyClose] = useState(false);
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
    if (scopeKey === null) return;
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

  const summary = snapshot ? monthCloseSummary(snapshot.documents) : null;
  const itbis = snapshot && summary
    ? itbisCard(summary.itbis_owed, snapshot.figures?.itbis_owed, Boolean(snapshot.figures), t("business.month_close.pending_label", "Pending"))
    : null;
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
      const saved = document.kind === "invoice" ? await client.markCobrado(documentId, scopeKey ?? undefined, today) : await client.markPagado(documentId, scopeKey ?? undefined, today);
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
      showToast({ kind: "error", text: t("business.month_close.mark_failed", "We couldn't save that change. The status is back to what it was.") });
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
      const next = await client.closeMonth(snapshot.month, scopeKey ?? undefined);
      setSnapshot(next);
      setConfirming(false);
    } catch {
      showToast({ kind: "error", text: t("business.month_close.close_failed", "We couldn't close the month. Try again.") });
    } finally {
      setBusyClose(false);
    }
  }

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
  const overdueNow = (document: MonthCloseDocument) => documentOverdue(document, today);
  const byDue = (rows: MonthCloseDocument[]) => [...rows].sort((a, b) => (a.due_on ?? a.occurred_on).localeCompare(b.due_on ?? b.occurred_on));
  const unsettled = documents.filter((document) => document.status === "pendiente");
  const receivable = byDue(unsettled.filter((document) => document.kind === "invoice"));
  const payable = byDue(unsettled.filter((document) => document.kind === "receipt"));
  const overdueCount = unsettled.filter(overdueNow).length;
  const fiscalDocuments = [...new Set(blockers.map((blocker) => blocker.documentId))].flatMap((id) => documents.filter((document) => document.id === id));
  const lockedRows = locked ? sortDocuments(documents, "newest") : [];
  const statusView = snapshot?.figures?.by_status ? monthCloseStatusView(snapshot.figures.by_status) : null;
  const noDocuments = statusView ? !statusView.any_documents : documents.length === 0;
  const rowGrid = "tablet:grid tablet:grid-cols-[7.5rem_minmax(0,1.4fr)_6.5rem_7rem_auto] tablet:items-center tablet:gap-3";
  const monthName = new Intl.DateTimeFormat(locale, { month: "long", timeZone: "UTC" }).format(new Date(Date.UTC(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1, 1)));
  const shortDay = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
  const tasks: { id: string; icon: typeof Inbox; text: string; detail?: string | null; action?: { label: string; run: () => void } }[] = [
    ...(review && review.count > 0 ? [{ id: "review", icon: Inbox, text: t("business.month_close.checklist_review", { count: review.count, defaultValue: "Review {{count}} receipts" }), detail: review.detail, action: { label: t("business.month_close.action_review", "Review"), run: review.open } }] : []),
    ...(fiscalDocuments.length > 0 ? [{ id: "fiscal", icon: FileWarning, text: t("business.month_close.checklist_fiscal", { count: fiscalDocuments.length, defaultValue: "Add the RNC or NCF to {{count}} documents" }), detail: gate.ok ? null : t("business.month_close.checklist_required", "Needed to close the month") }] : []),
    ...(unsettled.length > 0 ? [{
      id: "settle",
      icon: Clock,
      text: t("business.month_close.checklist_settle", { count: unsettled.length, defaultValue: "Mark {{count}} documents as collected or paid" }),
      detail: overdueCount > 0 ? t("business.month_close.checklist_overdue", { count: overdueCount, defaultValue: "{{count}} overdue" }) : null,
      action: { label: t("business.month_close.action_see", "See"), run: () => document.getElementById("month-close-money")?.scrollIntoView({ block: "start", behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }) },
    }] : []),
  ];

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
          <span className="block text-[12px] text-[#56635e] dark:text-white/70">
            {document.kind === "invoice" ? t("business.month_close.kind_invoice", "Invoice") : t("business.month_close.kind_receipt", "Expense")}
          </span>
          <span className="block break-words text-[15px] font-medium text-black dark:text-white">{document.counterparty}</span>
          <span className="mt-1 block text-[13px] text-[#56635e] dark:text-white/70">{fiscalLine(document, t)}</span>
        </div>
        <div>
          <time dateTime={document.due_on ?? document.occurred_on} className="block text-[14px] tabular-nums text-black/80 dark:text-white/80">
            {shortDay(document.due_on ?? document.occurred_on)}
          </time>
          {relative ? <span className="mt-1 block text-[12px] text-[#56635e] dark:text-white/70">{relative}</span> : null}
        </div>
        <span className="cuadrao-amount text-[15px] font-medium tabular-nums text-black dark:text-white">{formatMoney(document.amount, document.currency, locale)}</span>
        <div className="flex flex-wrap items-center gap-2">
          {pending ? markButton(document) : null}
        </div>
      </li>
    );
  }

  function markButton(document: MonthCloseDocument) {
    return (
      <button
        type="button"
        data-testid={document.kind === "invoice" ? "month-close-mark-cobrado" : "month-close-mark-pagado"}
        className="inline-flex min-h-11 shrink-0 items-center rounded-full px-3 text-[13px] font-medium text-[var(--cuadrao-green)] hover:bg-[var(--cuadrao-green)]/[0.06] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] disabled:opacity-40"
        disabled={pendingIds.has(document.id) || phase === "loading"}
        aria-label={document.kind === "invoice"
          ? t("business.month_close.mark_cobrado_named", "Mark {{name}} collected", { name: document.counterparty })
          : t("business.month_close.mark_pagado_named", "Mark {{name}} paid", { name: document.counterparty })}
        onClick={() => void mark(document)}
      >
        {document.kind === "invoice" ? t("business.month_close.mark_cobrado", "Mark collected") : t("business.month_close.mark_pagado", "Mark paid")}
      </button>
    );
  }

  function renderList(testId: string, title: string, rows: MonthCloseDocument[], empty: string, layout: "pending" | "overdue" | "closed" = "pending") {
    const listClass = "mt-2 divide-y divide-black/[0.06] overflow-hidden rounded-[20px] border border-black/[0.06] bg-white dark:divide-white/[0.06] dark:border-white/[0.06] dark:bg-[#1f2225]";
    return (
      <section aria-labelledby={`${testId}-title`} data-testid={testId} data-layout={layout} className="mt-6">
        <h4 id={`${testId}-title`} className="text-[15px] font-medium text-black dark:text-white">{title}</h4>
        {rows.length === 0 ? (
          <p className="mt-2 text-[14px] text-[#56635e] dark:text-white/70" data-testid={`${testId}-empty`}>{empty}</p>
        ) : (
          <ul className={listClass}>{rows.map((document) => renderRow(document, layout))}</ul>
        )}
      </section>
    );
  }

  function moneyColumn(testId: string, title: string, rows: MonthCloseDocument[], empty: string) {
    const open = expanded.has(testId);
    const shown = open ? rows : rows.slice(0, MONEY_ROWS);
    return (
      <section aria-labelledby={`${testId}-title`} data-testid={testId} className={`${cardClass} flex flex-col`}>
        <div className="flex items-baseline justify-between gap-3">
          <h4 id={`${testId}-title`} className="font-display text-[17px] font-medium text-black dark:text-white">{title}</h4>
          {rows.length > 0 ? <span data-testid={`${testId}-total`} className="cuadrao-amount text-[15px] font-medium tabular-nums text-black dark:text-white">{formatMoney(documentsTotal(rows), "DOP", locale)}</span> : null}
        </div>
        {rows.length === 0 ? (
          <p className="mt-3 text-[14px] text-[#56635e] dark:text-white/70" data-testid={`${testId}-empty`}>{empty}</p>
        ) : (
          <ul className="mt-2 divide-y divide-black/[0.06] dark:divide-white/[0.06]">
            {shown.map((document) => {
              const overdue = overdueNow(document);
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
                  // Two lines that share their edges: who and how much, then when and what to do.
                  className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3 gap-y-0.5 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/50"
                >
                  <p className="break-words text-[15px] font-medium text-black dark:text-white">{document.counterparty}</p>
                  <span className="cuadrao-amount text-right text-[15px] font-medium tabular-nums text-black dark:text-white">{formatMoney(document.amount, document.currency, locale)}</span>
                  <p className={`text-[13px] tabular-nums ${overdue ? "text-[#9e2f39] dark:text-[#ec9aa0]" : "text-[#56635e] dark:text-white/70"}`}>
                    {overdue
                      ? [t("business.month_close.status_vencida", "Overdue"), relative?.toLocaleLowerCase(locale)].filter(Boolean).join(" · ")
                      : document.due_on
                        ? t("business.month_close.due_on", { date: shortDay(document.due_on), defaultValue: "Due {{date}}" })
                        : shortDay(document.occurred_on)}
                  </p>
                  {/* The button keeps its 44px target but gives back its padding, so its words end on the amount's edge. */}
                  <span className="-my-3 -mr-3 justify-self-end">{canMutate ? markButton(document) : null}</span>
                </li>
              );
            })}
          </ul>
        )}
        {rows.length > MONEY_ROWS ? (
          <button
            type="button"
            aria-expanded={open}
            className="mt-1 inline-flex min-h-11 items-center self-start rounded-full px-1 text-[14px] font-medium text-[var(--cuadrao-green)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)]"
            onClick={() => setExpanded((current) => {
              const next = new Set(current);
              if (next.has(testId)) next.delete(testId);
              else next.add(testId);
              return next;
            })}
          >
            {open ? t("business.month_close.show_less", "Show less") : t("business.month_close.show_more", { count: rows.length - MONEY_ROWS, defaultValue: "Show {{count}} more" })}
          </button>
        ) : null}
      </section>
    );
  }

  function figure(testId: string, label: string, state: "pending" | "final" | undefined, value: string, why?: string) {
    const known = state !== "pending";
    return (
      <div data-testid={testId} data-layout="summary" data-state={state} data-amount={known ? value : undefined} className="min-w-0">
        <p className="text-[13px] text-[#56635e] dark:text-white/70">{label}</p>
        <p className={`mt-1 font-display text-[22px] font-medium leading-tight tracking-tight text-black dark:text-white ${known ? "cuadrao-amount tabular-nums" : ""}`}>
          {known ? formatMoney(value, "DOP", locale) : "—"}
        </p>
        {why ? <p className="mt-1 text-[12px] text-[#56635e] dark:text-white/70">{why}</p> : null}
      </div>
    );
  }

  const loadingBar = "rounded-md bg-black/[0.06] dark:bg-white/[0.08]";
  const figures = snapshot && summary && net ? {
    income: figureCard(summary.income_before_itbis, snapshot.figures?.income_before_itbis, Boolean(snapshot.figures), ""),
    expenses: figureCard(summary.expense_before_itbis, snapshot.figures?.expense_before_itbis, Boolean(snapshot.figures), ""),
  } : null;

  return (
    <section aria-labelledby="month-close-title" aria-busy={phase === "loading" ? true : undefined} data-testid="month-close" data-closed={locked ? "true" : "false"} className="mb-8 space-y-4">
      <MonthSwitcher
        month={month}
        current={currentMonth}
        earliest={snapshot?.earliest_month ?? null}
        onMonth={(next) => { setMonth(next); setExpanded(new Set()); setFiscalOpen(false); onMonthChange?.(next); }}
        headingId="month-close-title"
        openRequest={pickerRequest}
      />

      {phase === "error" ? (
        <div data-testid="month-close-error" data-layout="error" className={cardClass}>
          <EmptyState kind="error" compact title={t("business.month_close.error_title", "We couldn't load the month")} body={t("business.empty.error_body", "Your data is still saved. Check your connection and try again.")} action={{ label: t("business.month_close.retry", "Try again"), run: () => setAttempt((value) => value + 1) }} />
        </div>
      ) : !snapshot || !summary || !net || !figures ? (
        <div role="status" data-testid="month-close-loading" data-layout="loading" aria-busy="true">
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
        <div data-testid="month-close-empty" data-layout="empty" className={cardClass}>
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
      ) : (
        <>
          {phase === "loading" ? <p role="status" data-testid="month-close-refreshing" className="sr-only">{t("business.month_close.loading", "Loading the month")}</p> : null}

          {locked && snapshot.closed_at ? (
            <p role="status" data-testid="month-close-closed" className={`${cardClass} flex items-center gap-3 text-[15px] font-medium text-[var(--cuadrao-green)]`}>
              <CircleCheck className="h-5 w-5 shrink-0" aria-hidden="true" />
              <span>
                {t("business.month_close.closed", "Month closed")}
                <span className="block text-[13px] font-normal text-[#56635e] dark:text-white/70">
                  {t("business.month_close.closed_on", "Closed on {{date}}.", { date: formatDay(snapshot.closed_at.slice(0, 10), locale) })}
                </span>
              </span>
            </p>
          ) : (
            <section aria-labelledby="month-close-checklist-title" data-testid="month-close-checklist" className={cardClass}>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 id="month-close-checklist-title" className="font-display text-[18px] font-medium text-black dark:text-white">
                  {t("business.month_close.checklist_title", { month: monthName, defaultValue: "To close {{month}}" })}
                </h3>
                {tasks.length > 0 ? (
                  <span data-testid="month-close-checklist-left" className="text-[14px] tabular-nums text-[#56635e] dark:text-white/70">{t("business.month_close.checklist_left", { count: tasks.length, defaultValue: "{{count}} left" })}</span>
                ) : null}
              </div>
              {tasks.length === 0 ? (
                <p className="mt-3 flex items-center gap-2 text-[15px] text-[var(--cuadrao-green)]" data-testid="month-close-checklist-ready">
                  <CircleCheck className="h-5 w-5 shrink-0" aria-hidden="true" />
                  {t("business.month_close.checklist_ready", { month: monthName, defaultValue: "Everything is ready to close {{month}}." })}
                </p>
              ) : (
                <ul className="mt-2 divide-y divide-black/[0.06] dark:divide-white/[0.06]">
                  {tasks.map((task) => (
                    <li key={task.id} data-testid={`month-close-task-${task.id}`} className="py-2">
                      <div className="flex min-h-11 items-center gap-3">
                        <task.icon className={`h-5 w-5 shrink-0 ${task.id === "fiscal" ? "text-[#9e2f39] dark:text-[#ec9aa0]" : "text-[#735c14] dark:text-[#f6e7c1]"}`} aria-hidden="true" />
                        <div className="min-w-0 flex-1">
                          <p className="text-[15px] text-black dark:text-white">{task.text}</p>
                          {task.detail ? <p id={task.id === "fiscal" ? "month-close-fiscal-required" : undefined} className={`text-[13px] ${task.id === "fiscal" ? "text-[#9e2f39] dark:text-[#ec9aa0]" : "text-[#56635e] dark:text-white/70"}`}>{task.detail}</p> : null}
                        </div>
                        {task.id === "fiscal" ? (
                          <button
                            type="button"
                            aria-expanded={fiscalOpen}
                            aria-controls="month-close-blockers"
                            className="inline-flex min-h-11 shrink-0 items-center gap-1 rounded-full px-3 text-[14px] font-medium text-[var(--cuadrao-green)] hover:bg-[var(--cuadrao-green)]/[0.06] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)]"
                            onClick={() => setFiscalOpen((value) => !value)}
                          >
                            {fiscalOpen ? t("business.month_close.action_hide", "Hide") : t("business.month_close.action_which", "Which ones")}
                            <ChevronDown className={`h-4 w-4 transition-transform motion-reduce:transition-none ${fiscalOpen ? "rotate-180" : ""}`} aria-hidden="true" />
                          </button>
                        ) : task.action ? (
                          <button type="button" className="inline-flex min-h-11 shrink-0 items-center gap-1 rounded-full px-3 text-[14px] font-medium text-[var(--cuadrao-green)] hover:bg-[var(--cuadrao-green)]/[0.06] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)]" onClick={task.action.run}>
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
              <div className="mt-3 flex flex-wrap items-center justify-end gap-x-4 gap-y-2 border-t border-black/[0.06] pt-3 dark:border-white/[0.06]">
                {reason ? (
                  <p id="month-close-reason" data-testid="month-close-reason" className="min-w-0 flex-1 text-[13px] text-[#56635e] dark:text-white/70">{reason}</p>
                ) : !gate.ok && gate.reason === "closed" && !locked ? (
                  <p data-testid="month-close-filing" className="min-w-0 flex-1 text-[13px] text-[#56635e] dark:text-white/70">{t("business.month_close.filing_ready", "You already have everything for the 606 and the 607. Close the month when you finish marking what was collected and what was paid.")}</p>
                ) : gate.ok && tasks.length > 0 ? (
                  <p data-testid="month-close-close-note" className="min-w-0 flex-1 text-[13px] text-[#56635e] dark:text-white/70">{t("business.month_close.close_with_open_tasks", "You can close now; whatever is left stays as it is.")}</p>
                ) : null}
                <button
                  type="button"
                  data-testid="month-close-close"
                  className={gate.ok && canMutate ? `${pillButtonClass} bg-[var(--cuadrao-green)] text-[var(--cuadrao-cream)]` : `${secondaryButtonClass} min-w-11`}
                  disabled={!canMutate || !gate.ok}
                  aria-describedby={reason ? "month-close-reason" : !gate.ok && fiscalDocuments.length > 0 ? "month-close-fiscal-required" : undefined}
                  onClick={() => setConfirming(true)}
                >
                  {t("business.month_close.close_named", { month: monthName, defaultValue: "Close {{month}}" })}
                </button>
              </div>
            </section>
          )}


          {locked ? null : receivable.length === 0 && payable.length === 0 ? (
            <p id="month-close-money" data-testid="month-close-nothing-open" className={`${cardClass} flex scroll-mt-6 items-center gap-2 text-[15px] text-[#56635e] dark:text-white/70`}>
              <CircleCheck className="h-5 w-5 shrink-0 text-[var(--cuadrao-green)]" aria-hidden="true" />
              {t("business.month_close.nothing_open", "Nothing to collect or pay.")}
            </p>
          ) : (
            <div id="month-close-money" className="grid scroll-mt-6 grid-cols-1 gap-4 tablet:grid-cols-2">
              {moneyColumn("month-close-receivable", t("business.month_close.receivable_title", "To collect"), receivable, t("business.month_close.receivable_empty", "Nothing to collect."))}
              {moneyColumn("month-close-payable", t("business.month_close.payable_title", "To pay"), payable, t("business.month_close.payable_empty", "Nothing to pay."))}
            </div>
          )}

          <section aria-label={t("business.month_close.subtitle", "Income, expenses, and ITBIS for the month.")} data-testid="month-close-cards" data-loading={phase === "loading" ? "true" : undefined} className={`${cardClass} grid grid-cols-2 gap-x-4 gap-y-5 desktop:grid-cols-4`}>
            {figure("month-close-income", t("business.month_close.income_label", "Income"), figures.income.state, figures.income.value, figures.income.state === "pending" ? t("business.month_close.figure_unknown", "Can't be calculated yet.") : undefined)}
            {figure("month-close-expenses", t("business.month_close.expense_label", "Expenses"), figures.expenses.state, figures.expenses.value, figures.expenses.state === "pending" ? t("business.month_close.figure_unknown", "Can't be calculated yet.") : undefined)}
            {figure(
              "month-close-net",
              t("business.month_close.net_label", "Net result"),
              net.state,
              net.state === "final" ? net.net_before_itbis : "",
              net.state === "pending"
                ? net.reason === "documents"
                  ? t("business.month_close.net_waits", { count: net.pending_count, defaultValue: "{{count}} documents left to mark" })
                  : t("business.month_close.figure_unknown", "Can't be calculated yet.")
                : undefined,
            )}
            {itbis ? figure(
              "month-close-itbis",
              itbis.credit ? t("business.month_close.itbis_credit_label", "ITBIS balance in your favor") : t("business.month_close.itbis_label", "ITBIS to pay"),
              itbis.state,
              itbis.value,
              itbis.state === "pending" ? t("business.month_close.figure_unknown", "Can't be calculated yet.") : undefined,
            ) : null}
          </section>

          {locked ? renderList("month-close-rows", t("business.month_close.locked_title", "Documents in this month"), lockedRows, "", "closed") : null}
        </>
      )}

      <ConfirmDialog
        isOpen={confirming}
        tone="primary"
        title={t("business.month_close.close_confirm_title", "Close this month?")}
        description={t("business.month_close.close_confirm_body", "The month becomes read-only. Statuses cannot be changed.")}
        confirmLabel={t("business.month_close.close_confirm_action", "Yes, close the month")}
        cancelLabel={t("business.month_close.close_back", "Back")}
        isBusy={busyClose}
        onCancel={() => { if (!busyClose) setConfirming(false); }}
        onConfirm={() => void confirmClose()}
      />


    </section>
  );
}

export type MonthCloseSource = { client: MonthCloseClient; scopeKey: string | null };

/** The month close the selected Business reads. One per view, so the sample books Inicio closes are the books its export sees. */
// One sample book per sample source, so Inicio and an export opened from the top bar see the same closed months.
const SAMPLE_CLIENTS = new WeakMap<object, MonthCloseClient>();
function sampleClientFor(source: object): MonthCloseClient {
  const known = SAMPLE_CLIENTS.get(source);
  if (known) return known;
  const made = createMockMonthCloseClient();
  SAMPLE_CLIENTS.set(source, made);
  return made;
}

export function useMonthCloseSource(): MonthCloseSource {
  const { chosen, source, spaces } = useBusiness();
  // One key per Business, known before the first load: the own Business is "own" before and after the list arrives.
  const scopeKey = spaces === null ? null : chosen && chosen.role !== "owner" ? chosen.grant_id : "own";
  return { client: source.mode === "fixture" ? sampleClientFor(source) : monthCloseClient, scopeKey };
}

export default function BusinessMonthClosePanel({ monthClose, onMonthChange, review }: { monthClose: MonthCloseSource; onMonthChange?: (month: string) => void; review?: { count: number; detail: string | null; open: () => void } | null }) {
  const { chosen, actions } = useBusiness();
  const add = chosen?.role === "owner" ? actions.create.find((action) => action.id === "upload_receipt") : undefined;
  return (
    <BusinessMonthCloseView
      client={monthClose.client}
      scopeKey={monthClose.scopeKey}
      canMutate={Boolean(chosen?.capabilities.includes("approve"))}
      onMonthChange={onMonthChange}
      review={review}
      onAdd={add?.run}
    />
  );
}
