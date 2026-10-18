"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, BadgeCheck, Check, ChevronLeft, ChevronRight, CircleCheck, Clock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import {
  canCloseMonth,
  canStepMonth,
  currentMonthKey,
  electronicNcf,
  fiscalNumberPresent,
  formatMonthLabel,
  monthCloseBlockers,
  monthCloseClient,
  monthCloseNetDisplay,
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

const monthArrowClass =
  "inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-black/70 transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent dark:text-white/70 dark:hover:bg-white/5";

function MonthSwitcher({
  month,
  current,
  earliest,
  onMonth,
  headingId,
}: {
  month: string;
  current: string;
  earliest: string | null;
  onMonth: (month: string) => void;
  headingId: string;
}) {
  const { t } = useTranslation();
  const options = monthPickerMonths(current, earliest);
  const [open, setOpen] = useState(false);
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

function StatusChip({ status, label }: { status: MonthCloseStatus; label: string }) {
  const Icon = status === "pendiente" ? Clock : status === "cobrado" ? BadgeCheck : CircleCheck;
  return (
    <span data-testid="month-close-status" data-status={status} className={`inline-flex min-h-6 items-center gap-1 rounded-full px-2.5 py-1 text-[12px] font-medium ${CHIP_TONE[status]}`}>
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {label}
    </span>
  );
}

function fiscalLine(document: MonthCloseDocument, text: (key: string, fallback: string, options?: Record<string, unknown>) => string): string {
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
    <article className={cardClass} data-testid={testId} data-state={state} data-amount={money ? amount ?? value : undefined}>
      <h4 className="text-[13px] font-medium text-black/55 dark:text-white/55">{label}</h4>
      <p className={`mt-2 font-display text-[24px] font-medium leading-tight tracking-tight text-black dark:text-white ${money ? "tabular-nums" : ""}`}>
        {money ? formatMoney(value, "DOP", locale) : value}
      </p>
      <p className="mt-2 text-[12px] text-black/55 dark:text-white/55">{hint}</p>
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
  const clock = useRef(now ?? new Date());
  const currentMonth = currentMonthKey(clock.current);
  const [month, setMonth] = useState(currentMonth);
  const [snapshot, setSnapshot] = useState<MonthCloseSnapshot | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const [busyClose, setBusyClose] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [pendingIds, setPendingIds] = useState<ReadonlySet<string>>(() => new Set());
  const inFlight = useRef(new Set<string>());
  const generation = useRef(0);

  useEffect(() => {
    const request = ++generation.current;
    setPhase("loading");
    setSnapshot(null);
    setConfirming(false);
    client.load(month, scopeKey).then(
      (next) => {
        if (generation.current !== request) return;
        setSnapshot(next);
        setPhase("ready");
      },
      () => {
        if (generation.current !== request) return;
        setPhase("error");
      },
    );
  }, [attempt, client, month, scopeKey]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(timer);
  }, [toast]);

  const summary = snapshot ? monthCloseSummary(snapshot.documents) : null;
  const net = snapshot ? monthCloseNetDisplay(snapshot.documents) : null;
  const blockers = snapshot ? monthCloseBlockers(snapshot.documents) : [];
  const gate = snapshot ? canCloseMonth(snapshot) : { ok: false as const, reason: "not_calendar_month" as const };
  const closed = Boolean(snapshot?.closed_at);
  const statusLabel = (status: MonthCloseStatus) =>
    ({
      pendiente: t("business.month_close.status_pendiente", "Pending"),
      cobrado: t("business.month_close.status_cobrado", "Collected"),
      pagado: t("business.month_close.status_pagado", "Paid"),
    })[status];

  async function mark(document: MonthCloseDocument) {
    if (!canMutate || !snapshot || snapshot.closed_at || document.status !== "pendiente" || inFlight.current.has(document.id)) return;
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
      const saved = document.kind === "invoice" ? await client.markCobrado(documentId, scopeKey) : await client.markPagado(documentId, scopeKey);
      if (started !== generation.current) return;
      setSnapshot((current) => (current ? { ...current, documents: current.documents.map((item) => (item.id === saved.id ? saved : item)) } : current));
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
  const stillHere = (document: MonthCloseDocument) => document.status === "pendiente" || pendingIds.has(document.id);
  const receivable = sortDocuments(documents.filter((document) => document.kind === "invoice" && stillHere(document)), "newest");
  const payable = sortDocuments(documents.filter((document) => document.kind === "receipt" && stillHere(document)), "newest");
  const fiscalGaps = sortDocuments(
    documents.filter((document) => document.status !== "pendiente" && !pendingIds.has(document.id) && (!rncPresent(document.rnc) || !fiscalNumberPresent(document))),
    "newest",
  );
  const lockedRows = closed ? sortDocuments(documents, "newest") : [];

  function renderRow(document: MonthCloseDocument) {
    const pending = canMutate && document.status === "pendiente" && !closed;
    return (
      <li
        key={document.id}
        id={`month-close-row-${document.id}`}
        tabIndex={-1}
        data-testid="month-close-row"
        data-document-id={document.id}
        data-kind={document.kind}
        data-status={document.status}
        data-locked={closed ? "true" : "false"}
        className="flex flex-col gap-3 px-4 py-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/50 tablet:grid tablet:grid-cols-[minmax(0,1.4fr)_6.5rem_7rem_auto] tablet:items-center tablet:gap-3"
      >
        <div className="min-w-0">
          <span className="block text-[12px] text-black/45 dark:text-white/45">
            {document.kind === "invoice" ? t("business.month_close.kind_invoice", "Invoice") : t("business.month_close.kind_receipt", "Expense")}
          </span>
          <span className="block truncate text-[15px] font-medium text-black dark:text-white">{document.counterparty}</span>
          <span className="mt-1 block text-[13px] text-black/60 dark:text-white/60">{fiscalLine(document, t)}</span>
        </div>
        <time dateTime={document.occurred_on} className="text-[14px] text-black/70 dark:text-white/70">
          {formatDay(document.occurred_on, locale)}
        </time>
        <div>
          <span className="text-[15px] font-medium tabular-nums text-black dark:text-white">{formatMoney(document.amount, "DOP", locale)}</span>
          {document.itbis ? <span className="mt-1 block text-[12px] tabular-nums text-black/50 dark:text-white/50">{t("business.month_close.itbis_line", "ITBIS {{amount}}", { amount: formatMoney(document.itbis, "DOP", locale) })}</span> : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip status={document.status} label={statusLabel(document.status)} />
          {pending ? (
            <button
              type="button"
              data-testid={document.kind === "invoice" ? "month-close-mark-cobrado" : "month-close-mark-pagado"}
              className={`${secondaryButtonClass} px-3.5`}
              disabled={pendingIds.has(document.id)}
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

  function renderList(testId: string, title: string, rows: MonthCloseDocument[], empty: string) {
    return (
      <section aria-labelledby={`${testId}-title`} data-testid={testId} className="mt-6">
        <h4 id={`${testId}-title`} className="text-[15px] font-medium text-black dark:text-white">{title}</h4>
        {rows.length === 0 ? (
          <p className="mt-2 text-[14px] text-black/60 dark:text-white/60" data-testid={`${testId}-empty`}>{empty}</p>
        ) : (
          <ul className="mt-2 divide-y divide-black/[0.06] rounded-[20px] border border-black/[0.06] bg-white dark:divide-white/[0.06] dark:border-white/[0.06] dark:bg-[#1f2225]">
            {rows.map(renderRow)}
          </ul>
        )}
      </section>
    );
  }

  return (
    <section aria-labelledby="month-close-title" data-testid="month-close" data-closed={closed ? "true" : "false"} className="mb-8">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <MonthSwitcher
            month={month}
            current={currentMonth}
            earliest={snapshot?.earliest_month ?? null}
            onMonth={setMonth}
            headingId="month-close-title"
          />
          <p className="mt-1 px-2 text-[13px] text-black/55 dark:text-white/55">{t("business.month_close.subtitle", "Income, expenses, and ITBIS for the month.")}</p>
        </div>
        <div className="flex flex-col items-stretch gap-2 tablet:items-end">
          {closed && snapshot?.closed_at ? (
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
                className={`${pillButtonClass} ${gate.ok ? "bg-[var(--cuadrao-green)] text-[var(--cuadrao-cream)]" : ""}`}
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
        <div role="alert" className={`${cardClass} text-[14px] text-black/70 dark:text-white/70`}>
          <p>{t("business.month_close.error", "We couldn't load the month. Try again.")}</p>
          <button type="button" className={`${secondaryButtonClass} mt-3`} onClick={() => setAttempt((value) => value + 1)}>
            {t("business.month_close.retry", "Try again")}
          </button>
        </div>
      ) : phase === "loading" || !snapshot || !summary || !net ? (
        <p role="status" data-testid="month-close-loading" className="text-[14px] text-black/60 dark:text-white/60">
          {t("business.month_close.loading", "Loading the month")}
        </p>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 tablet:grid-cols-2 desktop:grid-cols-4" data-testid="month-close-cards">
            <SummaryCard testId="month-close-income" label={t("business.month_close.income_label", "Income")} value={summary.income_before_itbis} hint={t("business.month_close.income_hint", "Invoice totals before ITBIS.")} locale={locale} />
            <SummaryCard testId="month-close-expenses" label={t("business.month_close.expense_label", "Expenses")} value={summary.expense_before_itbis} hint={t("business.month_close.expense_hint", "Expense totals before ITBIS.")} locale={locale} />
            <SummaryCard
              testId="month-close-net"
              label={t("business.month_close.net_label", "Net result")}
              state={net.state}
              value={net.state === "final" ? net.net_before_itbis : t("business.month_close.pending_label", "Pending")}
              hint={net.state === "pending"
                ? t("business.month_close.pending_reason", "{{count}} documents still pending", { count: net.pending_count })
                : t("business.month_close.net_hint", "Income minus expenses, before ITBIS.")}
              locale={locale}
            />
            <SummaryCard testId="month-close-itbis" label={t("business.month_close.itbis_label", "ITBIS to pay")} value={summary.itbis_owed} hint={t("business.month_close.itbis_hint", "ITBIS on invoices minus ITBIS on expenses.")} locale={locale} />
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

          {closed ? (
            <section aria-labelledby="month-close-locked-title" data-testid="month-close-rows" className="mt-6">
              <h4 id="month-close-locked-title" className="text-[15px] font-medium text-black dark:text-white">{t("business.month_close.locked_title", "Documents in this month")}</h4>
              <ul className="mt-2 divide-y divide-black/[0.06] rounded-[20px] border border-black/[0.06] bg-white dark:divide-white/[0.06] dark:border-white/[0.06] dark:bg-[#1f2225]">
                {lockedRows.map(renderRow)}
              </ul>
            </section>
          ) : (
            <>
              {renderList("month-close-receivable", t("business.month_close.receivable_title", "To collect"), receivable, t("business.month_close.receivable_empty", "Nothing to collect."))}
              {renderList("month-close-payable", t("business.month_close.payable_title", "To pay"), payable, t("business.month_close.payable_empty", "Nothing to pay."))}
              {fiscalGaps.length > 0 ? renderList("month-close-fiscal-gaps", t("business.month_close.fiscal_gaps_title", "Missing RNC or NCF"), fiscalGaps, "") : null}
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
    </section>
  );
}

export default function BusinessMonthClosePanel() {
  const { chosen } = useBusiness();
  return (
    <BusinessMonthCloseView
      client={monthCloseClient}
      scopeKey={chosen?.grant_id ?? "own"}
      canMutate={Boolean(chosen?.capabilities.includes("approve"))}
    />
  );
}
