"use client";

import { ChevronLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessExpenseDetail } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { formatDay, formatMoney, formatTimestamp } from "./business-format";
import { cardClass, LoadingRows, useCategoryLabel } from "./business-ui";

/**
 * The plain detail of an expense entered by hand: no receipt and no draft to
 * open, so the record is the expense itself, when it was recorded and its
 * revision. Back returns to Expenses.
 */
export default function ExpenseDetailPanel({ expenseId }: { expenseId: string }) {
  const { t, i18n } = useTranslation();
  const { source, records, openPanel } = useBusiness();
  const categoryLabel = useCategoryLabel();
  const locale = i18n.resolvedLanguage ?? "en";
  const [state, setState] = useState<{ status: "loading" } | { status: "ready"; expense: BusinessExpenseDetail } | { status: "failed" }>({ status: "loading" });
  useEffect(() => {
    let active = true;
    setState({ status: "loading" });
    source.expense(expenseId).then(
      (expense) => active && setState({ status: "ready", expense }),
      () => active && setState({ status: "failed" }),
    );
    return () => {
      active = false;
    };
  }, [expenseId, source]);
  const accounts = new Map((records.workspace?.accounts ?? []).map((account) => [account.id, account]));
  return (
    <section aria-labelledby="expense-detail-title" data-testid="business-expense-detail">
      <button type="button" onClick={() => openPanel({ kind: "expenses" })} className="mb-4 flex min-h-11 items-center gap-1.5 rounded-full pr-3 text-[14px] text-black/65 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:text-white/65">
        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        {t("business.nav.expenses", "Expenses")}
      </button>
      {state.status === "loading" ? <LoadingRows /> : null}
      {state.status === "failed" ? <p role="alert" className="text-[14px] text-[#a8434c] dark:text-[#ec9aa0]">{t("business.expenses.detail_error", "We couldn't open this expense. Try again.")}</p> : null}
      {state.status === "ready" ? (
        <>
          <header className="mb-5">
            <p className="mb-2 text-[13px] text-black/55 dark:text-white/55">{t("business.expenses.detail_title", "Saved expense")}</p>
            <h2 id="expense-detail-title" className="min-w-0 break-words font-display text-[25px] font-medium tracking-tight text-black dark:text-white">{state.expense.merchant ?? t("business.expenses.no_merchant", "Expense")}</h2>
            <p className="mt-3 font-display text-[23px] font-medium tabular-nums text-black dark:text-white">{formatMoney(state.expense.amount, state.expense.currency, locale)}</p>
          </header>
          <div className={cardClass}>
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-[14px]">
              <dt className="text-black/55 dark:text-white/55">{t("business.review.date", "Date")}</dt>
              <dd className="text-black dark:text-white">{formatDay(state.expense.occurred_on, locale)}</dd>
              <dt className="text-black/55 dark:text-white/55">{t("business.review.category", "Category")}</dt>
              <dd className="text-black dark:text-white">{categoryLabel(state.expense.category_id)}</dd>
              <dt className="text-black/55 dark:text-white/55">{t("business.review.account", "Paid from")}</dt>
              <dd className="text-black dark:text-white">{state.expense.funding === "owner_funds" ? t("business.dossier.owner_funds", "Owner's money") : (state.expense.account_id && accounts.get(state.expense.account_id)?.nickname) || t("business.expenses.account_unknown", "Unknown")}</dd>
            </dl>
            <p className="mt-5 text-[14px] text-black/65 dark:text-white/65">{t("business.expenses.no_receipt", "No receipt attached")}</p>
            <p className="mt-2 text-[13px] text-black/55 dark:text-white/55">
              {[state.expense.recorded_at ? t("business.expenses.recorded_on", "Recorded on {{when}}", { when: formatTimestamp(state.expense.recorded_at, locale) }) : null, state.expense.revision != null ? t("business.dossier.revision", "Revision {{version}}", { version: state.expense.revision }) : null].filter(Boolean).join(" · ")}
            </p>
          </div>
        </>
      ) : null}
    </section>
  );
}
