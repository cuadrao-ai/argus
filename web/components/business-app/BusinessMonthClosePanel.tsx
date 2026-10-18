"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { BadgeCheck, CircleCheck, Clock, AlertCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import {
  closeGate,
  filterDocuments,
  electronicNcf,
  fiscalNumberPresent,
  monthCloseBlockers,
  monthCloseClient,
  monthCloseSummary,
  paperNcf,
  rncPresent,
  sortDocuments,
  statusTotals,
  type MonthCloseBlocker,
  type MonthCloseClient,
  type MonthCloseDocument,
  type MonthCloseSnapshot,
  type MonthCloseStatus,
} from "@/lib/business-month-close";
import { formatDay, formatMoney, type Period, type PeriodKey } from "./business-format";
import BusinessPeriodControl from "./BusinessPeriodControl";
import { cardClass, pillButtonClass, secondaryButtonClass } from "./business-ui";
import { useBusiness } from "./BusinessWorkspace";

const FILTERS = ["all", "pendiente", "cobrado", "pagado"] as const;
type Filter = (typeof FILTERS)[number];
const SORTS = ["newest", "oldest"] as const;
type Sort = (typeof SORTS)[number];

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

function moveRadio(event: KeyboardEvent<HTMLDivElement>, values: readonly string[], current: string, choose: (next: string) => void) {
  const forward = event.key === "ArrowRight" || event.key === "ArrowDown";
  const backward = event.key === "ArrowLeft" || event.key === "ArrowUp";
  if (!forward && !backward) return;
  event.preventDefault();
  const index = values.indexOf(current);
  const next = values[(index + (forward ? 1 : values.length - 1)) % values.length];
  choose(next);
  event.currentTarget.querySelector<HTMLButtonElement>(`[data-value="${next}"]`)?.focus();
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
  const name = document.counterparty;
  if (blocker.kind === "pending") {
    return document.kind === "invoice"
      ? text("business.month_close.blocker_pending_invoice", "{{name}} is still uncollected", { name })
      : text("business.month_close.blocker_pending_receipt", "{{name}} is still unpaid", { name });
  }
  if (blocker.kind === "missing_rnc") return text("business.month_close.blocker_rnc", "{{name}} has no RNC", { name });
  return text("business.month_close.blocker_ncf", "{{name}} has no NCF or e-CF", { name });
}

export function BusinessMonthCloseView({
  client,
  period,
  setPeriod,
}: {
  client: MonthCloseClient;
  period: Period;
  setPeriod: (next: PeriodKey | Period) => void;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const [snapshot, setSnapshot] = useState<MonthCloseSnapshot | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("newest");
  const [confirming, setConfirming] = useState(false);
  const [busyClose, setBusyClose] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const generation = useRef(0);

  useEffect(() => {
    const request = ++generation.current;
    setPhase("loading");
    setSnapshot(null);
    setConfirming(false);
    client.load({ from: period.from, to: period.to }).then(
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
  }, [attempt, client, period.from, period.to]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(timer);
  }, [toast]);

  const summary = snapshot ? monthCloseSummary(snapshot.documents) : null;
  const totals = snapshot ? statusTotals(snapshot.documents) : null;
  const blockers = snapshot ? monthCloseBlockers(snapshot.documents) : [];
  const gate = snapshot ? closeGate(snapshot) : { ok: false as const, reason: "not_calendar_month" as const };
  const closed = Boolean(snapshot?.closed_at);
  const visible = snapshot ? sortDocuments(filterDocuments(snapshot.documents, filter), sort) : [];
  const statusLabel = (status: MonthCloseStatus) =>
    ({
      pendiente: t("business.month_close.status_pendiente", "Pending"),
      cobrado: t("business.month_close.status_cobrado", "Collected"),
      pagado: t("business.month_close.status_pagado", "Paid"),
    })[status];

  async function mark(document: MonthCloseDocument) {
    if (!snapshot || snapshot.closed_at || document.status !== "pendiente") return;
    const started = generation.current;
    const previous = snapshot;
    const nextStatus: MonthCloseStatus = document.kind === "invoice" ? "cobrado" : "pagado";
    setSnapshot({
      ...snapshot,
      documents: snapshot.documents.map((item) => (item.id === document.id ? { ...item, status: nextStatus } : item)),
    });
    try {
      const saved = document.kind === "invoice" ? await client.markCobrado(document.id) : await client.markPagado(document.id);
      if (started !== generation.current) return;
      setSnapshot((current) => (current ? { ...current, documents: current.documents.map((item) => (item.id === saved.id ? saved : item)) } : current));
    } catch {
      if (started !== generation.current) return;
      setSnapshot(previous);
      setToast(t("business.month_close.mark_failed", "We couldn't save that change. The status is back to what it was."));
    }
  }

  async function confirmClose() {
    if (!snapshot?.month || busyClose) return;
    setBusyClose(true);
    try {
      const next = await client.closeMonth(snapshot.month);
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

  const reason = !snapshot || gate.ok
    ? ""
    : gate.reason === "not_calendar_month"
      ? t("business.month_close.reason_not_month", "Choose a calendar month to close it.")
      : t("business.month_close.reason_blockers", "Pending items or documents without an RNC, NCF, or e-CF are still open.");

  return (
    <section aria-labelledby="month-close-title" data-testid="month-close" data-closed={closed ? "true" : "false"}>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 id="month-close-title" className="font-display text-[26px] font-medium tracking-tight text-black dark:text-white">
            {t("business.month_close.title", "Close the month")}
          </h2>
          <p className="mt-1 text-[14px] text-black/55 dark:text-white/55">{t("business.month_close.subtitle", "Income, expenses, and ITBIS for the month.")}</p>
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
                disabled={!gate.ok}
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

      <div className="mb-5">
        <BusinessPeriodControl period={period} setPeriod={setPeriod} />
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
      ) : phase === "loading" || !snapshot || !summary || !totals ? (
        <p role="status" data-testid="month-close-loading" className="text-[14px] text-black/60 dark:text-white/60">
          {t("business.month_close.loading", "Loading the month")}
        </p>
      ) : (
        <>
          {blockers.length > 0 ? (
            <section aria-labelledby="month-close-blockers-title" data-testid="month-close-blockers" className="mb-5 rounded-[20px] border border-[#c2a44d]/50 bg-[#f4ead2]/40 p-4 dark:border-[#c2a44d]/40 dark:bg-[#4a3d1c]/40">
              <h3 id="month-close-blockers-title" className="flex items-center gap-2 text-[14px] font-medium text-[#3f3414] dark:text-[#f6e7c1]">
                <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
                {t("business.month_close.blockers_title", "Before you close")}
              </h3>
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

          <div className="grid gap-3 tablet:grid-cols-2">
            <article className={cardClass} data-testid="month-close-net" data-amount={summary.net_before_itbis}>
              <h3 className="text-[13px] font-medium text-black/55 dark:text-white/55">{t("business.month_close.net_label", "Net result")}</h3>
              <p className="mt-2 font-display text-[28px] font-medium tabular-nums tracking-tight text-black dark:text-white">{formatMoney(summary.net_before_itbis, "DOP", locale)}</p>
              <p className="mt-2 text-[12px] text-black/55 dark:text-white/55">{t("business.month_close.net_hint", "Income minus expenses, before ITBIS.")}</p>
            </article>
            <article className={cardClass} data-testid="month-close-itbis" data-amount={summary.itbis_owed}>
              <h3 className="text-[13px] font-medium text-black/55 dark:text-white/55">{t("business.month_close.itbis_label", "ITBIS owed")}</h3>
              <p className="mt-2 font-display text-[28px] font-medium tabular-nums tracking-tight text-black dark:text-white">{formatMoney(summary.itbis_owed, "DOP", locale)}</p>
              <p className="mt-2 text-[12px] text-black/55 dark:text-white/55">{t("business.month_close.itbis_hint", "ITBIS on invoices minus ITBIS on expenses.")}</p>
            </article>
          </div>

          <div role="radiogroup" aria-label={t("business.month_close.filter_label", "Status")} data-testid="month-close-filters" className="mt-3 grid gap-3 tablet:grid-cols-4" onKeyDown={(event) => moveRadio(event, FILTERS, filter, (next) => setFilter(next as Filter))}>
            {FILTERS.map((value) => {
              const selected = filter === value;
              const total = value === "all" ? null : totals[value];
              return (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  data-value={value}
                  data-testid={`month-close-filter-${value}`}
                  onClick={() => setFilter(value)}
                  className={`${cardClass} text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/50 ${selected ? "ring-2 ring-[var(--cuadrao-green)]" : ""}`}
                >
                  <span className="block text-[13px] font-medium text-black/55 dark:text-white/55">
                    {value === "all" ? t("business.month_close.filter_all", "All") : statusLabel(value)}
                  </span>
                  {total ? (
                    <>
                      <span className="mt-2 block font-display text-[22px] font-medium tabular-nums tracking-tight text-black dark:text-white">{formatMoney(total.amount, "DOP", locale)}</span>
                      <span className="mt-1 block text-[12px] text-black/55 dark:text-white/55">{t("business.month_close.documents", "{{count}} documents", { count: total.count })}</span>
                    </>
                  ) : (
                    <span className="mt-2 block text-[14px] text-black/70 dark:text-white/70">{t("business.month_close.filter_all_hint", "Every invoice and expense")}</span>
                  )}
                </button>
              );
            })}
          </div>

          <div role="radiogroup" aria-label={t("business.month_close.sort_label", "Order")} className="mt-4 flex flex-wrap gap-2" onKeyDown={(event) => moveRadio(event, SORTS, sort, (next) => setSort(next as Sort))}>
            {SORTS.map((value) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={sort === value}
                data-value={value}
                onClick={() => setSort(value)}
                className={`min-h-11 rounded-full px-3.5 text-[13px] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/50 ${sort === value ? "bg-black text-white dark:bg-white dark:text-black" : "text-black/60 dark:text-white/60"}`}
              >
                {value === "newest" ? t("business.month_close.sort_newest", "Newest") : t("business.month_close.sort_oldest", "Oldest")}
              </button>
            ))}
          </div>

          {visible.length === 0 ? (
            <p className="mt-6 text-[14px] text-black/60 dark:text-white/60" data-testid="month-close-empty">
              {snapshot.documents.length === 0
                ? t("business.month_close.empty", "No invoices or expenses in this month.")
                : t("business.month_close.filtered_empty", "Nothing with this status.")}
            </p>
          ) : (
            <div className="mt-4">
              <div className="hidden px-4 pb-2 text-[12px] font-medium text-black/45 tablet:grid tablet:grid-cols-[minmax(0,1.5fr)_7rem_8rem_auto] tablet:gap-3 dark:text-white/45" aria-hidden="true">
                <span>{t("business.month_close.column_counterparty", "Counterparty")}</span>
                <span>{t("business.month_close.column_date", "Date")}</span>
                <span>{t("business.month_close.column_amount", "Amount")}</span>
                <span>{t("business.month_close.column_status", "Status")}</span>
              </div>
              <ul aria-label={t("business.month_close.list_label", "Invoices and expenses")} data-testid="month-close-rows" className="divide-y divide-black/[0.06] rounded-[20px] border border-black/[0.06] bg-white dark:divide-white/[0.06] dark:border-white/[0.06] dark:bg-[#1f2225]">
                {visible.map((document) => {
                  const pending = document.status === "pendiente" && !closed;
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
                      className="flex flex-col gap-3 px-4 py-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/50 tablet:grid tablet:grid-cols-[minmax(0,1.5fr)_7rem_8rem_auto] tablet:items-center tablet:gap-3"
                    >
                      <div className="min-w-0">
                        <span className="block text-[12px] text-black/45 dark:text-white/45">
                          {document.kind === "invoice" ? t("business.month_close.kind_invoice", "Invoice") : t("business.month_close.kind_receipt", "Expense")}
                        </span>
                        <span className="block truncate text-[15px] font-medium text-black dark:text-white">{document.counterparty}</span>
                        <span className="mt-1 block text-[13px] text-black/60 dark:text-white/60">{fiscalLine(document, t)}</span>
                      </div>
                      <time dateTime={document.occurred_on} className="text-[14px] text-black/70 dark:text-white/70">
                        <span className="mr-2 text-[12px] text-black/45 tablet:hidden dark:text-white/45">{t("business.month_close.column_date", "Date")}</span>
                        {formatDay(document.occurred_on, locale)}
                      </time>
                      <div>
                        <span className="mr-2 text-[12px] text-black/45 tablet:hidden dark:text-white/45">{t("business.month_close.column_amount", "Amount")}</span>
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
                })}
              </ul>
            </div>
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
  const { period, setPeriod } = useBusiness();
  return <BusinessMonthCloseView client={monthCloseClient} period={period} setPeriod={setPeriod} />;
}
