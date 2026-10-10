"use client";

import { useMemo } from "react";
import { Banknote, FileText, ImageIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { WorkspaceSearch } from "@/components/chat/ChatWorkspace";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessDataSource } from "./business-data";
import { formatDay, formatMoney, periodContaining, type Period } from "./business-format";
import { useStatusLabel } from "./business-ui";
import type { BusinessPanelState } from "./BusinessWorkspace";

/**
 * Business expenses and receipts in the shared omnisearch. Selecting a hit
 * opens the panel that holds it: an expense's receipt, with its original, or
 * the expense in its period's list when it has no receipt.
 */
export function useBusinessSearch({
  source,
  chatAvailable,
  accounts,
  openPanel,
  setPeriod,
}: {
  source: BusinessDataSource;
  chatAvailable: boolean;
  accounts: readonly BusinessAccount[];
  openPanel: (panel: BusinessPanelState) => void;
  setPeriod: (key: Period["key"]) => void;
}): WorkspaceSearch {
  const { t, i18n } = useTranslation();
  const statusLabel = useStatusLabel();
  const locale = i18n.resolvedLanguage ?? "en";

  return useMemo<WorkspaceSearch>(() => {
    const nickname = new Map(accounts.map((account) => [account.id, account.nickname]));
    const line = (...parts: (string | null | undefined)[]) => parts.filter(Boolean).join(" · ");
    return {
      copy: {
        placeholder: chatAvailable
          ? t("business.search.placeholder", "Search expenses, receipts and chats")
          : t("business.search.placeholder_records", "Search expenses and receipts"),
        noResultsHint: t("business.search.no_results_hint", "Try a merchant or a file name."),
        region: t("business.search.region", "Business records"),
        loading: t("business.search.loading", "Searching your business"),
        failed: t("business.search.failed", "We couldn't search your business."),
        retry: t("command_palette.retry_search", "Try searching again"),
      },
      find: async (query) => {
        const found = await source.search(query);
        return [
          {
            id: "expenses",
            label: t("business.expenses.title", "Expenses"),
            hits: found.expenses.map((expense) => ({
              id: expense.id,
              icon: Banknote,
              title: expense.merchant ?? t("business.expenses.no_merchant", "Expense"),
              detail: line(formatDay(expense.occurred_on, locale), expense.account_id ? nickname.get(expense.account_id) : null),
              amount: formatMoney(expense.amount, expense.currency, locale),
              open: () => {
                if (expense.receipt_id) {
                  openPanel({ kind: "receipt", receiptId: expense.receipt_id });
                  return;
                }
                const key = periodContaining(expense.occurred_on);
                if (key) setPeriod(key);
                openPanel({ kind: "expenses", expenseId: expense.id });
              },
            })),
          },
          {
            id: "receipts",
            label: t("business.search.receipts", "Receipts"),
            hits: found.receipts.map((receipt) => ({
              id: receipt.id,
              icon: receipt.media_type === "application/pdf" ? FileText : ImageIcon,
              title: receipt.merchant ?? receipt.filename ?? t("business.receipt.untitled", "Receipt"),
              detail: line(statusLabel(receipt.status), formatDay(receipt.occurred_on ?? receipt.received_at, locale)),
              amount: formatMoney(receipt.amount, receipt.currency, locale) || null,
              open: () => openPanel({ kind: "receipt", receiptId: receipt.id }),
            })),
          },
        ];
      },
    };
  }, [accounts, chatAvailable, locale, openPanel, setPeriod, source, statusLabel, t]);
}
