"use client";

import { createElement, useMemo } from "react";
import { Banknote, FileText, ImageIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { WorkspaceSearch } from "@/components/chat/ChatWorkspace";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessDataSource } from "./business-data";
import BusinessSearchDossier, { type BusinessSearchRecord } from "./BusinessSearchDossier";
import { formatDay, formatMoney, periodContaining, type Period } from "./business-format";
import { useCategoryLabel, useStatusLabel } from "./business-ui";
import type { BusinessPanelState } from "./BusinessWorkspace";

/**
 * Business expenses, receipts and notes in the shared omnisearch. Hovering or
 * focusing a hit previews its record beside the results; opening it shows the
 * panel that holds it: an expense's receipt, with its original, the expense in
 * its period's list when it has no receipt, or a note's draft.
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
  const categoryLabel = useCategoryLabel();
  const locale = i18n.resolvedLanguage ?? "en";

  return useMemo<WorkspaceSearch>(() => {
    const nickname = new Map(accounts.map((account) => [account.id, account.nickname]));
    const line = (...parts: (string | null | undefined)[]) => parts.filter(Boolean).join(" · ");
    const preview = (record: BusinessSearchRecord) => createElement(BusinessSearchDossier, { record, source, accounts });
    return {
      previewAvailable: true,
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
        const [records, captures] = await Promise.allSettled([source.search(query), source.captures(query)]);
        if (records.status === "rejected") throw records.reason;
        const found = records.value;
        return [
          {
            id: "expenses",
            label: t("business.expenses.title", "Expenses"),
            hits: found.expenses.map((expense) => ({
              id: expense.id,
              icon: Banknote,
              title: expense.merchant ?? t("business.expenses.no_merchant", "Expense"),
              detail: line(formatDay(expense.occurred_on, locale), categoryLabel(expense.category_id), expense.funding === "owner_funds" ? t("business.dossier.owner_funds", "Owner's money") : expense.account_id ? nickname.get(expense.account_id) : null),
              amount: formatMoney(expense.amount, expense.currency, locale),
              preview: preview({ kind: "expense", expense }),
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
            hits: found.receipts.filter((receipt) => !receipt.email_original).map((receipt) => ({
              id: receipt.id,
              icon: receipt.media_type === "application/pdf" ? FileText : ImageIcon,
              title: receipt.merchant ?? receipt.filename ?? t("business.receipt.untitled", "Receipt"),
              detail: line(statusLabel(receipt.status), formatDay(receipt.occurred_on ?? receipt.received_at, locale)),
              amount: formatMoney(receipt.amount, receipt.currency, locale) || null,
              preview: preview({ kind: "receipt", receipt }),
              open: () => openPanel({ kind: "receipt", receiptId: receipt.id }),
            })),
          },
          {
            id: "captures",
            label: t("business.capture.notes", "Original notes"),
            ...(captures.status === "rejected" ? { error: t("business.capture.search_failed", "Notes are unavailable. Other record results are shown below.") } : {}),
            hits: captures.status === "fulfilled" ? captures.value.map((note) => ({
              id: note.source_id,
              icon: FileText,
              title: note.text,
              detail: line(t("business.capture.saved_note", "Saved original note"), formatDay(note.received_at, locale), t("business.dossier.revision", "Revision {{version}}", { version: note.revision }), t(`business.dossier.state.${note.review_state}`, note.review_state)),
              amount: null,
              preview: preview({ kind: "note", note }),
              open: () => openPanel({ kind: "draft", draftId: note.draft_id }),
            })) : [],
          },
        ];
      },
    };
  }, [accounts, categoryLabel, chatAvailable, locale, openPanel, setPeriod, source, statusLabel, t]);
}
