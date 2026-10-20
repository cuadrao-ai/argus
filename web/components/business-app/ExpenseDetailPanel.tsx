"use client";

import { ChevronLeft } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessExpenseDetail } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { expensePanel } from "./business-expense-target";
import { formatDay, formatMoney, formatTimestamp } from "./business-format";
import { cardClass, secondaryButtonClass, useCategoryLabel, RecordMarks, recordFiscalMark } from "./business-ui";
import { Settle } from "./business-skeletons";
import { useRecordTray } from "./record-tray";

/**
 * One saved expense opened by its id (a direct ?expense= link). It resolves
 * the record the same way an Expenses row does: an expense that names a
 * receipt or a draft opens that record; only an expense entered by hand,
 * with neither, shows its plain detail here, when it was recorded and its
 * revision. Back returns to Expenses naming this expense, so the list focuses
 * that row once it renders again (the workspace shows one panel at a time,
 * so the row that opened this panel is not on the page while it is open).
 * The panel takes focus when it opens. Inside the desktop tray the list
 * stays beside it, so there is no way back and the tray owns focus.
 */
export default function ExpenseDetailPanel({ expenseId }: { expenseId: string }) {
  const { t, i18n } = useTranslation();
  const { source, records, openPanel } = useBusiness();
  const categoryLabel = useCategoryLabel();
  const locale = i18n.resolvedLanguage ?? "en";
  const [state, setState] = useState<{ status: "loading" } | { status: "ready"; expense: BusinessExpenseDetail } | { status: "failed" }>({ status: "loading" });
  const panel = useRef<HTMLElement>(null);
  const inTray = useRecordTray() !== null;
  const [attempt, setAttempt] = useState(0);
  // The fetch keys on the expense, not on the navigation callback: a workspace
  // re-render that hands out a new openPanel must not ask for the record again.
  const open = useRef(openPanel);
  useEffect(() => {
    open.current = openPanel;
  }, [openPanel]);
  useEffect(() => {
    if (!inTray) panel.current?.focus();
  }, [inTray]);
  useEffect(() => {
    let active = true;
    setState({ status: "loading" });
    source.expense(expenseId).then(
      (expense) => {
        if (!active) return;
        const target = expensePanel(expense);
        if (target.kind === "expense") setState({ status: "ready", expense });
        else open.current(target);
      },
      () => active && setState({ status: "failed" }),
    );
    return () => {
      active = false;
    };
  }, [expenseId, source, attempt]);
  const accounts = new Map((records.workspace?.accounts ?? []).map((account) => [account.id, account]));
  const title = state.status === "ready" ? (state.expense.merchant ?? t("business.expenses.no_merchant", "Expense")) : t("business.expenses.detail_title", "Saved expense");
  return (
    <section ref={panel} tabIndex={-1} aria-labelledby="expense-detail-title" data-testid="business-expense-detail" className="outline-none">
      {inTray ? null : <button type="button" onClick={() => openPanel({ kind: "expenses", expenseId })} className="mb-4 flex min-h-11 items-center gap-1.5 rounded-full pr-3 text-[14px] text-black/65 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:text-white/65">
        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        {t("business.nav.expenses", "Expenses")}
      </button>}
      {state.status !== "ready" ? <h2 id="expense-detail-title" className="sr-only">{title}</h2> : null}
      {state.status === "loading" ? <Settle pending layout="rows" /> : null}
      {state.status === "failed" ? (
        <div role="alert" className="space-y-3">
          <p className="text-[14px] text-[#a8434c] dark:text-[#ec9aa0]">{t("business.expenses.detail_error", "We couldn't open this expense. Try again.")}</p>
          <button type="button" data-testid="expense-detail-retry" className={secondaryButtonClass} onClick={() => setAttempt((value) => value + 1)}>{t("business.expenses.retry", "Try again")}</button>
        </div>
      ) : null}
      {state.status === "ready" ? (
        <>
          <header className="mb-5">
            <p className="mb-2 text-[13px] text-black/55 dark:text-white/55">{t("business.expenses.detail_title", "Saved expense")}</p>
            <h2 id="expense-detail-title" className="min-w-0 break-words font-display text-[25px] font-medium tracking-tight text-black dark:text-white">{title}</h2>
            <p className="cuadrao-amount mt-3 font-display text-[23px] font-medium tabular-nums text-black dark:text-white">{formatMoney(state.expense.amount, state.expense.currency, locale)}</p>
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
            <RecordMarks personal={state.expense.personal} fiscal={recordFiscalMark(state.expense)} markedBy={state.expense.personal_marked_by} className="mt-4" />
            {state.expense.personal && state.expense.fiscal_value ? (
              <p className="mt-2 text-[13px] text-black/65 dark:text-white/65" data-testid="expense-606-state">
                {state.expense.include_606 === true ? t("business.marks.included_606", "Included in the 606") : state.expense.include_606 === false ? t("business.marks.excluded_606", "Not included in the 606") : t("business.marks.pending_606", "Waiting for the accountant")}
              </p>
            ) : null}
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
