"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, Paperclip } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { BusinessExpense } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { formatDay, formatMoney } from "./business-format";
import { expensePanel } from "./business-expense-target";
import { cardClass, LoadingRows, PanelHeading, secondaryButtonClass, useCategoryLabel, RecordMarks } from "./business-ui";
import BusinessPeriodControl from "./BusinessPeriodControl";
import OutsidePeriodNote from "./OutsidePeriodNote";
import { ReceiptPeriodExport } from "./ReceiptDossierReview";

export default function BusinessExpensesPanel() {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const categoryLabel = useCategoryLabel();
  const { source, revision, period, setPeriod, records, panel, openPanel, actions, chosen } = useBusiness();
  const exportEnd = period.to ?? (records.overview?.from === period.from ? records.overview.to : undefined);
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
      {chosen && exportEnd ? <div className="mb-4"><ReceiptPeriodExport
        key={`${chosen.grant_id}:${period.from}:${exportEnd}`}
        scope={{ name: chosen.name, capabilities: chosen.capabilities, grantId: chosen.role === "owner" ? null : chosen.grant_id }}
        start={period.from}
        end={exportEnd}
        available={source.mode === "live"}
      /></div> : null}
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
                  <RecordMarks personal={expense.personal} fiscalValue={expense.fiscal_value} known={expense.fiscal_known === true} markedBy={expense.personal_marked_by} className="mt-1" />
                </span>
                <span className="text-right text-[15px] font-medium tabular-nums text-black dark:text-white">
                  {formatMoney(expense.amount, expense.currency, locale)}
                </span>
              </>
            );
            return (
              <li
                key={expense.id}
                data-expense-id={expense.id}
                aria-current={expense.id === found ? "true" : undefined}
                ref={expense.id === found ? (row) => row?.scrollIntoView({ block: "nearest" }) : undefined}
                className="rounded-[14px] px-3 py-1 aria-[current=true]:bg-black/[0.04] dark:aria-[current=true]:bg-white/[0.06]"
              >
                <button
                  type="button"
                  onClick={() => openPanel(expensePanel(expense))}
                  className="flex min-h-11 w-full items-center gap-3 rounded-[12px] py-2 text-left hover:bg-black/[0.03] focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:hover:bg-white/[0.04] dark:focus-visible:ring-white/30"
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
