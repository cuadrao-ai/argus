"use client";

import { useEffect, useMemo, useState } from "react";
import { Paperclip } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { BusinessExpense } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { formatDay, formatMoney } from "./business-format";
import { cardClass, LoadingRows, PanelHeading, secondaryButtonClass, useCategoryLabel } from "./business-ui";
import BusinessPeriodControl from "./BusinessPeriodControl";
import OutsidePeriodNote from "./OutsidePeriodNote";

export default function BusinessExpensesPanel() {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const categoryLabel = useCategoryLabel();
  const { source, revision, period, setPeriod, records, panel, openPanel, actions } = useBusiness();
  const found = panel.kind === "expenses" ? panel.expenseId : undefined;
  const [items, setItems] = useState<BusinessExpense[] | null>(null);
  const [failed, setFailed] = useState(false);
  const accounts = useMemo(
    () => new Map((records.workspace?.accounts ?? []).map((account) => [account.id, account])),
    [records.workspace],
  );

  useEffect(() => {
    let cancelled = false;
    source
      .expenses(period.from, period.to)
      .then((next) => !cancelled && setItems(next))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [period.from, period.to, revision, source]);

  const record = actions.create.find((action) => action.id === "record_expense");

  return (
    <section>
      <PanelHeading
        title={t("business.expenses.title", "Expenses")}
        subtitle={t("business.expenses.subtitle", "Saved expenses from {{from}} to {{to}}.", {
          from: formatDay(period.from, locale),
          to: formatDay(period.to ?? records.overview?.to ?? period.from, locale),
        })}
        action={
          record ? (
            <button type="button" className={secondaryButtonClass} onClick={record.run}>
              {record.label}
            </button>
          ) : null
        }
      />
      <div className="mb-4">
        <BusinessPeriodControl period={period} setPeriod={setPeriod} />
        {records.overview ? <OutsidePeriodNote count={records.overview.outside_period_count} latestOn={records.overview.outside_period_latest_on} onShowAll={() => setPeriod("all")} /> : null}
      </div>
      {failed ? (
        <p role="alert" className="text-[14px] text-black/70 dark:text-white/70">
          {t("business.expenses.error", "We couldn't load your expenses. Try again.")}
        </p>
      ) : items === null ? (
        <LoadingRows />
      ) : items.length === 0 ? (
        <div className={`${cardClass} text-center text-[14px] text-black/55 dark:text-white/55`}>
          {t("business.expenses.empty", "No expenses saved in this period.")}
        </div>
      ) : (
        <ul className={`${cardClass} divide-y divide-black/[0.05] p-2 dark:divide-white/[0.05]`}>
          {items.map((expense) => (
            <li
              key={expense.id}
              aria-current={expense.id === found ? "true" : undefined}
              ref={expense.id === found ? (row) => row?.scrollIntoView({ block: "nearest" }) : undefined}
              className="flex items-center gap-3 rounded-[14px] px-3 py-3 aria-[current=true]:bg-black/[0.04] dark:aria-[current=true]:bg-white/[0.06]"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[15px] font-medium text-black dark:text-white">
                  {expense.merchant ?? t("business.expenses.no_merchant", "Expense")}
                </span>
                <span className="mt-0.5 block truncate text-[13px] text-black/50 dark:text-white/50">
                  {[formatDay(expense.occurred_on, locale), categoryLabel(expense.category_id), expense.funding === "owner_funds" ? t("business.dossier.owner_funds", "Owner's money") : expense.account_id ? accounts.get(expense.account_id)?.nickname : null]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </span>
              {expense.receipt_id ? (
                <button
                  type="button"
                  onClick={() => openPanel({ kind: "receipt", receiptId: expense.receipt_id as string })}
                  className="flex min-h-11 items-center gap-1.5 rounded-full px-3 text-[13px] font-medium text-black/60 hover:bg-black/5 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:text-white/60 dark:hover:bg-white/5"
                >
                  <Paperclip className="h-4 w-4" />
                  <span className="max-mobile:sr-only">{t("business.expenses.view_receipt", "Receipt")}</span>
                </button>
              ) : null}
              <span className="text-right text-[15px] font-medium tabular-nums text-black dark:text-white">
                {formatMoney(expense.amount, expense.currency, locale)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
