"use client";

import { ArrowRight, Inbox } from "lucide-react";
import { useTranslation } from "react-i18next";
import StarterActions from "@/components/chat/StarterActions";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { useBusiness } from "./BusinessWorkspace";
import { inboxCount } from "./inbox-count";
import { formatBusinessName, formatDay, formatMoney, formatRelativeTime } from "./business-format";
import { cardClass, LoadingRows, pillButtonClass } from "./business-ui";
import BusinessPeriodControl, { usePeriodLabel } from "./BusinessPeriodControl";
import OutsidePeriodNote from "./OutsidePeriodNote";

export default function BusinessOverviewPanel() {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const { isBelowTablet } = useResponsiveLayout();
  const { records, period, setPeriod, openPanel, actions, chosen } = useBusiness();
  const overview = records.overview;
  const upload = chosen?.role === "owner" ? actions.create.find((action) => action.id === "upload_receipt") : null;
  const periodLabel = usePeriodLabel();
  // The Bandeja's own counts, from the same server answer as the sidebar badge.
  const inbox = inboxCount(records);
  const attention = records.receiptActivity?.needs_attention_count ?? null;

  return (
    <section aria-labelledby="business-overview-title">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <h2 id="business-overview-title" className="font-display text-[26px] font-medium tracking-tight text-black dark:text-white">
          {formatBusinessName(chosen?.name, t("business.overview.title", "My business"))}
        </h2>
        <div className="flex flex-wrap items-center justify-end gap-3">
          <BusinessPeriodControl period={period} setPeriod={setPeriod} />
          {upload ? (
            <button type="button" data-testid="business-primary-upload" className={`${pillButtonClass} bg-[var(--cuadrao-green)] text-[var(--cuadrao-cream)]`} onClick={upload.run}>
              {upload.label}
            </button>
          ) : null}
        </div>
      </div>

      {records.error ? (
        <div role="alert" className={`${cardClass} text-[14px] text-black/70 dark:text-white/70`}>
          {t("business.overview.error", "We couldn't load your business records. Your saved receipts and expenses are safe. Try again.")}
        </div>
      ) : !overview ? (
        <LoadingRows rows={3} layout="overview" />
      ) : (
        <div className="grid gap-3 tablet:grid-cols-2">
          <button
            type="button"
            data-testid="overview-inbox"
            onClick={() => openPanel({ kind: "inbox" })}
            className={`${cardClass} flex items-center gap-3 text-left tablet:col-span-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40`}
          >
            <Inbox className="h-5 w-5 shrink-0 text-[var(--cuadrao-green)]" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="block font-display text-[20px] font-medium text-black dark:text-white">
                {inbox === null ? t("business.overview.in_inbox", "In your inbox") : <><span data-testid="overview-inbox-count">{inbox}</span>{" "}{locale === "es-419" ? "por revisar" : t("business.overview.in_inbox", "In your inbox")}</>}
                {attention !== null && attention > 0 ? <span data-testid="overview-attention" className="text-[15px] font-normal text-black/70 dark:text-white/75">{locale === "es-419" ? ` · ${attention} con problema` : ` · ${t("business.overview.attention", "{{count}} receipts need your attention", { count: attention })}`}</span> : null}
              </span>
              <span className="mt-1 block text-[13px] text-black/60 dark:text-white/65">{t("business.overview.open_inbox", "Open inbox")}</span>
            </span>
            <ArrowRight className="h-4 w-4 shrink-0 text-black/60 dark:text-white/65" aria-hidden="true" />
          </button>
          <button
            type="button"
            data-testid="overview-real-expenses"
            onClick={() => openPanel({ kind: "expenses" })}
            className={`${cardClass} group flex flex-col text-left transition-colors hover:border-black/15 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:hover:border-white/15`}
          >
            <span className={`${overview.totals.length === 0 ? "sr-only" : ""} text-[13px] font-medium text-black/55 dark:text-white/55`}>
              {t("business.marks.real_expenses", "Actual expenses")} · {periodLabel(period.key).toLowerCase()}
            </span>
            {overview.totals.length === 0 ? (
              <span className="flex w-full items-center justify-between gap-3 text-[14px] text-black/70 dark:text-white/75">
                {t("business.overview.no_expenses", "No expenses saved in this period yet.")}<ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
              </span>
            ) : (
              <ul className="mt-3 space-y-1">
                {overview.totals.map((total) => (
                  <li key={total.currency} className="flex items-baseline justify-between gap-3">
                    <span className="font-display text-[24px] font-medium tabular-nums tracking-tight text-black dark:text-white">
                      {formatMoney(total.amount, total.currency, locale)}
                    </span>
                    <span className="text-[13px] tabular-nums text-black/50 dark:text-white/50">
                      {t("business.overview.expense_count", "{{count}} expenses", { count: total.count })}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <span className={`${overview.totals.length === 0 ? "hidden" : "mt-auto pt-3"} text-[12px] text-black/45 dark:text-white/45`}>
              {t("business.overview.separate_currencies", "Each currency is totaled on its own. No conversion.")}
            </span>
          </button>

          <button
            type="button"
            data-testid="overview-fiscal-expenses"
            onClick={() => openPanel({ kind: "expenses" })}
            className={`${cardClass} group flex flex-col text-left transition-colors hover:border-black/15 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:hover:border-white/15`}
          >
            <span className={`${(overview.fiscal_totals ?? []).length === 0 ? "sr-only" : ""} text-[13px] font-medium text-black/55 dark:text-white/55`}>
              {t("business.marks.fiscal_expenses", "With fiscal value")} · {periodLabel(period.key).toLowerCase()}
            </span>
            {(overview.fiscal_totals ?? []).length === 0 ? (
              <span className="flex w-full items-center justify-between gap-3 text-[14px] text-black/70 dark:text-white/75">
                {t("business.marks.none_fiscal", "None with fiscal value in this period.")}<ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
              </span>
            ) : (
              <ul className="mt-3 space-y-1">
                {(overview.fiscal_totals ?? []).map((total) => (
                  <li key={total.currency} className="flex items-baseline justify-between gap-3">
                    <span className="font-display text-[24px] font-medium tabular-nums tracking-tight text-black dark:text-white">
                      {formatMoney(total.amount, total.currency, locale)}
                    </span>
                    <span className="text-[13px] tabular-nums text-black/50 dark:text-white/50">
                      {t("business.overview.expense_count", "{{count}} expenses", { count: total.count })}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <span className={`${(overview.fiscal_totals ?? []).length === 0 && !(overview.without_fiscal_totals ?? []).some((total) => total.count > 0) ? "hidden" : "mt-auto pt-3"} text-[12px] text-black/55 dark:text-white/55`} data-testid="overview-without-fiscal">
              {(overview.without_fiscal_totals ?? []).filter((total) => total.count > 0).map((total) => t("business.marks.without_fiscal", "No fiscal receipt: {{amount}} does not go into the 606", { amount: formatMoney(total.amount, total.currency, locale) })).join(" · ") || t("business.overview.separate_currencies", "Each currency is totaled on its own. No conversion.")}
            </span>
          </button>

          {overview.outside_period_count > 0 ? (
            <div className="tablet:col-span-2">
              <OutsidePeriodNote count={overview.outside_period_count} latestOn={overview.outside_period_latest_on} onShowAll={() => setPeriod("all")} />
            </div>
          ) : null}

          <p className="text-[12px] text-black/45 tablet:col-span-2 dark:text-white/45">
            {t("business.overview.coverage", "Covers {{from}} to {{to}}. Last receipt {{received}}. Totals include saved expenses only, not receipts waiting for review.", {
              from: formatDay(overview.from, locale),
              to: formatDay(overview.to, locale),
              received: overview.last_received_at
                ? formatRelativeTime(overview.last_received_at, locale)
                : t("business.overview.never", "none yet"),
            })}
          </p>
        </div>
      )}

      <div className="mt-8">
        <StarterActions
          onSelect={() => undefined}
          entries={actions.starterEntries.filter((entry) => !upload || entry.key !== "upload_receipt")}
          layout={isBelowTablet ? "scroll" : "wrap"}
        />
      </div>
    </section>
  );
}
