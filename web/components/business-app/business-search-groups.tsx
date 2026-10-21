import { createElement, type ReactNode } from "react";
import { AtSign, Banknote, FileText, HandCoins, ImageIcon, Landmark, Mail } from "lucide-react";
import type { TFunction } from "i18next";
import type { WorkspaceSearchGroup, WorkspaceSearchHit, WorkspaceSearchPage } from "@/components/chat/ChatWorkspace";
import type { BusinessAccount, BusinessExpense, ReceiptSummary } from "@/lib/business-api";
import {
  isInvalidSearchCursor,
  isStaleSearchCursor,
  type BusinessSearchEmail,
  type BusinessSearchKind,
  type BusinessSearchResult,
  type BusinessSearchSender,
} from "@/lib/business-search-api";
import type { BusinessDataSource } from "./business-data";
import BusinessSearchDossier, { type BusinessSearchRecord } from "./BusinessSearchDossier";
import { expensePanel } from "./business-expense-target";
import { formatDay, formatMoney, UNKNOWN_VALUE } from "./business-format";
import type { BusinessPanelState } from "./BusinessWorkspace";

type Items = {
  expenses: BusinessExpense;
  ventas: BusinessExpense;
  receipts: ReceiptSummary;
  accounts: BusinessAccount;
  email_deliveries: BusinessSearchEmail;
  email_senders: BusinessSearchSender;
};

export type SearchGroupContext = Readonly<{
  t: TFunction;
  locale: string;
  source: BusinessDataSource;
  accounts: readonly BusinessAccount[];
  openPanel: (panel: BusinessPanelState) => void;
  stateWord: (receipt: ReceiptSummary) => string;
  categoryLabel: (id: string | null) => string;
}>;

const line = (...parts: (string | null | undefined)[]) => parts.filter(Boolean).join(" · ");

/**
 * A group's next page. A stale cursor (the results changed under it) searches
 * again from page 1 without a word; an invalid one can never work, so its
 * retry does the same. Any other failure leaves the rows and keeps this step
 * for a retry.
 */
function pager<K extends BusinessSearchKind>(
  source: BusinessDataSource,
  query: string,
  kind: K,
  cursor: string | null | undefined,
  toHits: (items: Items[K][]) => WorkspaceSearchHit[],
): (() => Promise<WorkspaceSearchPage>) | undefined {
  if (!cursor || !source.searchMore) return undefined;
  const more = source.searchMore;
  let restartNext = false;
  const restart = async (): Promise<WorkspaceSearchPage> => {
    const first = await source.search(query);
    restartNext = false;
    return { restarted: true, hits: toHits(first[kind] as Items[K][]), loadMore: pager(source, query, kind, first.next_cursors[kind], toHits) };
  };
  return async () => {
    if (restartNext) return restart();
    try {
      const page = await more(query, kind, cursor);
      return { hits: toHits(page[kind] as Items[K][]), loadMore: pager(source, query, kind, page.next_cursors[kind], toHits) };
    } catch (error) {
      if (isStaleSearchCursor(error)) return restart();
      if (isInvalidSearchCursor(error)) restartNext = true;
      throw error;
    }
  };
}

/** The six record groups of one answer, in the order the owner reads them. */
export function searchKindGroups(ctx: SearchGroupContext, query: string, found: BusinessSearchResult): Record<BusinessSearchKind, WorkspaceSearchGroup> {
  const { t, locale, source, accounts, openPanel, stateWord, categoryLabel } = ctx;
  const nickname = new Map(accounts.map((account) => [account.id, account.nickname]));
  const preview = (record: BusinessSearchRecord): ReactNode => createElement(BusinessSearchDossier, { record, source, accounts });
  // Opening a result tells the backend, so it ranks first next time; a miss never reaches the person.
  const opened = (kind: BusinessSearchKind, id: string, open: () => void) => () => {
    open();
    void source.recordSearchOpen?.(kind, id)?.catch(() => undefined);
  };
  const group = <K extends BusinessSearchKind>(kind: K, label: string, toHits: (items: Items[K][]) => WorkspaceSearchHit[]): WorkspaceSearchGroup => {
    const loadMore = pager(source, query, kind, found.next_cursors[kind], toHits);
    return { id: kind, label, hits: toHits(found[kind] as Items[K][]), ...(loadMore ? { loadMore } : {}) };
  };
  const money = (amount: string | null, currency: string | null) => formatMoney(amount, currency, locale) || UNKNOWN_VALUE;

  const expenseHit = (kind: "expenses" | "ventas") => (expense: BusinessExpense): WorkspaceSearchHit => {
    const sale = kind === "ventas";
    return {
      id: expense.id,
      icon: sale ? HandCoins : Banknote,
      title: expense.merchant ?? (sale ? UNKNOWN_VALUE : t("business.expenses.no_merchant", "Expense")),
      detail: line(expense.occurred_on ? formatDay(expense.occurred_on, locale) : UNKNOWN_VALUE, sale && !expense.category_id ? null : categoryLabel(expense.category_id), expense.funding === "owner_funds" ? t("business.dossier.owner_funds", "Owner's money") : expense.account_id ? nickname.get(expense.account_id) : null),
      amount: money(expense.amount, expense.currency),
      badge: sale ? t("business.search.badge_venta", "Sale") : t("business.search.badge_expense", "Expense"),
      preview: preview({ kind: "expense", expense }),
      open: opened(kind, expense.id, () => openPanel(expensePanel(expense))),
    };
  };

  return {
    expenses: group("expenses", t("business.expenses.title", "Expenses"), (items) => items.map(expenseHit("expenses"))),
    ventas: group("ventas", t("business.search.ventas", "Sales"), (items) => items.map(expenseHit("ventas"))),
    receipts: group("receipts", t("business.search.receipts", "Receipts"), (items) =>
      items.filter((receipt) => !receipt.email_original).map((receipt) => ({
        id: receipt.id,
        icon: receipt.media_type === "application/pdf" ? FileText : ImageIcon,
        title: receipt.merchant ?? receipt.filename ?? t("business.receipt.untitled", "Receipt"),
        detail: line(stateWord(receipt), formatDay(receipt.occurred_on ?? receipt.received_at, locale)),
        amount: money(receipt.amount, receipt.currency),
        badge: t("business.search.badge_receipt", "Receipt"),
        preview: preview({ kind: "receipt", receipt }),
        open: opened("receipts", receipt.id, () => openPanel({ kind: "receipt", receiptId: receipt.id, list: "inbox" })),
      })),
    ),
    // An account has no screen of its own, so its row only shows it.
    accounts: group("accounts", t("business.search.accounts", "Accounts"), (items) =>
      items.map((account) => ({
        id: account.id,
        icon: Landmark,
        title: account.nickname ?? t("business.search.badge_account", "Account"),
        detail: account.currency,
        amount: null,
        badge: t("business.search.badge_account", "Account"),
      })),
    ),
    email_deliveries: group("email_deliveries", t("business.search.emails", "Emails"), (items) =>
      items.map((email) => ({
        id: email.id,
        icon: Mail,
        title: email.subject ?? UNKNOWN_VALUE,
        detail: line(email.sender ?? UNKNOWN_VALUE, email.received_at ? formatDay(email.received_at, locale) : UNKNOWN_VALUE, t(`business.email.state.${email.state}`, email.state)),
        amount: null,
        badge: t("business.search.badge_email", "Email"),
        preview: preview({ kind: "email", email }),
        open: opened("email_deliveries", email.id, () => openPanel({ kind: "email", emailId: email.id })),
      })),
    ),
    email_senders: group("email_senders", t("business.search.senders", "Senders"), (items) =>
      items.map((sender) => ({
        id: sender.id,
        icon: AtSign,
        title: sender.value || UNKNOWN_VALUE,
        detail: line(t(`business.search.sender_kind.${sender.kind}`, sender.kind), t(`business.search.sender_status.${sender.status}`, sender.status)),
        amount: null,
        badge: t("business.search.badge_sender", "Sender"),
        preview: preview({ kind: "sender", sender }),
        open: opened("email_senders", sender.id, () => openPanel({ kind: "business", tab: "correo" })),
      })),
    ),
  };
}
