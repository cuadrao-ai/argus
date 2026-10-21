"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, Paperclip } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { BusinessExpense } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { formatDay, formatMoney } from "./business-format";
import { expensePanel } from "./business-expense-target";
import { isOpenRecord, OPEN_ROW_CLASS } from "./record-tray";
import { cardClass, PanelHeading, useCategoryLabel, RecordMarks, recordFiscalMark } from "./business-ui";
import { Settle } from "./business-skeletons";
import BusinessPeriodControl from "./BusinessPeriodControl";
import OutsidePeriodNote from "./OutsidePeriodNote";
import BusinessAddMenu from "./BusinessAddMenu";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { EmptyState } from "./foundation/EmptyState";

export default function BusinessExpensesPanel() {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const categoryLabel = useCategoryLabel();
  const { isBelowTablet } = useResponsiveLayout();
  const { source, revision, period, setPeriod, records, panel, openPanel, actions, reload } = useBusiness();
  const found = panel.kind === "expenses" ? panel.expenseId : undefined;
  const [items, setItems] = useState<BusinessExpense[] | null>(null);
  const [failed, setFailed] = useState(false);
  const accounts = useMemo(
    () => new Map((records.workspace?.accounts ?? []).map((account) => [account.id, account])),
    [records.workspace],
  );

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    source
      .expenses(period.from, period.to)
      .then((next) => !cancelled && setItems(next))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [period.from, period.to, revision, source]);

  const record = actions.create.find((action) => action.id === "upload_receipt");
  // Coming back from one expense's panel: focus its row once the list has
  // rendered, so keyboard focus returns where it left. A row outside the
  // period is not in the list; the panel itself takes focus then. Once per
  // arrival: a background reload re-renders the list but never takes focus
  // back from wherever the person moved it.
  const section = useRef<HTMLElement>(null);
  const focusedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!found) focusedFor.current = null;
  }, [found]);
  useEffect(() => {
    if (!found || items === null || focusedFor.current === found) return;
    focusedFor.current = found;
    const row = section.current?.querySelector<HTMLButtonElement>(`[data-expense-id="${CSS.escape(found)}"] button`);
    (row ?? section.current)?.focus();
  }, [found, items]);

  return (
    <section ref={section} tabIndex={-1} className="outline-none">
      {isBelowTablet ? <div className="mb-4"><BusinessAddMenu placement="page" /></div> : null}
      <PanelHeading
        title={t("business.expenses.title", "Expenses")}
        subtitle={t("business.expenses.subtitle", "Saved expenses from {{from}} to {{to}}.", {
          from: formatDay(period.from, locale),
          to: formatDay(period.to ?? records.overview?.to ?? period.from, locale),
        })}
      />
      <div className="mb-4">
        <BusinessPeriodControl period={period} setPeriod={setPeriod} />
        {records.overview ? <OutsidePeriodNote count={records.overview.outside_period_count} latestOn={records.overview.outside_period_latest_on} onShowAll={() => setPeriod("all")} /> : null}
      </div>
      {failed ? (
        <EmptyState kind="error" testId="business-expenses-error" title={t("business.empty.expenses_error", "We couldn't load your expenses")} body={t("business.empty.error_body", "Your data is still saved. Check your connection and try again.")} action={{ label: t("common.retry", "Retry"), run: reload }} />
      ) : items === null ? (
        <Settle pending layout="expenses" />
      ) : items.length === 0 ? (
        <div className={cardClass} data-testid="business-expenses-empty">
          {period.key === "this_month" || period.key === "all" ? (
            <EmptyState kind="first_run" mark="receipt" compact title={t("business.empty.expenses_title", "Your approved expenses show here")} body={t("business.empty.expenses_body", "Every receipt you approve in the Inbox becomes an expense for its month.")} action={record ? { label: record.label, run: record.run } : undefined} />
          ) : (
            <EmptyState kind="filtered" compact title={t("business.empty.expenses_filtered_title", "No expenses in this period")} body={t("business.empty.expenses_filtered_body", "There may be expenses in other months.")} action={{ label: t("business.empty.see_all_periods", "See all periods"), run: () => setPeriod("all") }} />
          )}
        </div>
      ) : (
        <ul className={`${cardClass} divide-y divide-black/[0.05] p-2 dark:divide-white/[0.05]`}>
          {items.map((expense) => {
            const facts = (
              <>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[15px] font-medium text-black dark:text-white">
                    {expense.merchant ?? t("business.expenses.no_merchant", "Expense")}
                  </span>
                  <span className="mt-0.5 block truncate text-[13px] text-black/50 dark:text-white/50">
                    {[formatDay(expense.occurred_on, locale), categoryLabel(expense.category_id), expense.funding === "owner_funds" ? t("business.dossier.owner_funds", "Owner's money") : expense.account_id ? accounts.get(expense.account_id)?.nickname : null]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                  <RecordMarks personal={expense.personal} fiscal={recordFiscalMark(expense)} markedBy={expense.personal_marked_by} className="mt-1" />
                </span>
                <span className="cuadrao-amount text-right text-[15px] font-medium tabular-nums text-black dark:text-white">
                  {formatMoney(expense.amount, expense.currency, locale)}
                </span>
              </>
            );
            const target = expensePanel(expense);
            const current = expense.id === found || isOpenRecord(panel, target);
            return (
              <li
                key={expense.id}
                data-expense-id={expense.id}
                aria-current={current ? "true" : undefined}
                ref={current ? (row) => row?.scrollIntoView({ block: "nearest" }) : undefined}
                className={`rounded-item px-3 py-1 ${OPEN_ROW_CLASS}`}
              >
                <button
                  type="button"
                  onClick={() => openPanel(target)}
                  className="flex min-h-11 w-full items-center gap-3 rounded-item py-2 text-left hover:bg-black/[0.03] focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:hover:bg-white/[0.04] dark:focus-visible:ring-white/30"
                >
                  {facts}
                  {expense.receipt_id ? <Paperclip className="h-4 w-4 shrink-0 text-black/45 dark:text-white/45" aria-hidden="true" /> : null}
                  <span className="sr-only">{expense.receipt_id ? t("business.expenses.view_receipt", "Receipt") : t("business.expenses.view_detail", "Detail")}</span>
                  <ChevronRight className="h-4 w-4 shrink-0 text-black/35 dark:text-white/35" aria-hidden="true" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
