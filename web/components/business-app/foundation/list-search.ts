"use client";

import { useLayoutEffect, useSyncExternalStore } from "react";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { businessSearchEntryEnabled, omnisearchEnabled } from "@/lib/private-alpha-flags";

/**
 * A list keeps owning its text query: Registros' lives in its report request and URL, Bandeja's in its return
 * position, each Facturación section's in that section. While the list is on screen it lends the query and its setter
 * here, and the top bar's search button and the search window read and write through the loan. No loan, no scope.
 */
export type SearchableList = "inbox" | "transactions" | "invoices" | "customers" | "schedules";

/**
 * Each list's screen (the panel it sits on), the locale key that names it in "En <lista>", and the search results
 * and actions its scoped window keeps. Facturación's sections are three lists on one screen, one on show at a time;
 * the Business search finds none of their records, so their scope offers only "Filtrar <lista> por …".
 */
export const SEARCHABLE_LISTS: Readonly<Record<SearchableList, { screen: string; place: string; groups: readonly string[]; actions: readonly string[] }>> = {
  inbox: { screen: "inbox", place: "business.nav.inbox", groups: ["receipts", "email_deliveries", "email_senders"], actions: ["add", "copy_forward"] },
  transactions: { screen: "transactions", place: "business.nav.transactions", groups: ["expenses", "ventas", "captures"], actions: ["add", "export"] },
  invoices: { screen: "invoicing", place: "business.invoicing_preview.invoices_tab", groups: [], actions: [] },
  customers: { screen: "invoicing", place: "business.invoicing_preview.customers_tab", groups: [], actions: [] },
  schedules: { screen: "invoicing", place: "business.invoicing_preview.schedules_tab", groups: [], actions: [] },
};

/**
 * Whether the top bar can search a Business at all: the shell's own rule (omnisearch and Business Buscar). When it
 * cannot, a list keeps its own search field instead of lending its query to a bar that has no search.
 */
export const barSearchAvailable = omnisearchEnabled && businessSearchEntryEnabled("business");

/** Whether a list's search lives in the top bar now: a wide screen with bar search. A phone keeps the list's field. */
export function useSearchInBar(): boolean {
  return !useResponsiveLayout().isBelowTablet && barSearchAvailable;
}

type Loan = { query: string; setQuery: (query: string) => void; maxLength?: number };

const loans = new Map<SearchableList, Loan>();
const listeners = new Set<() => void>();
const emit = () => { for (const listener of listeners) listener(); };
function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** Writes `query` through the list's current setter: the search window's "filter this list" row. */
export function applyListSearch(list: SearchableList, query: string) {
  const loan = loans.get(list);
  loan?.setQuery(loan.maxLength ? query.slice(0, loan.maxLength) : query);
}

/** Called by the list on every render; `loan` is null while the list keeps its own search field. */
export function useLendListSearch(list: SearchableList, loan: Loan | null) {
  const query = loan?.query;
  const setQuery = loan?.setQuery;
  const maxLength = loan?.maxLength;
  useLayoutEffect(() => {
    if (query === undefined || setQuery === undefined) {
      if (loans.delete(list)) emit();
      return;
    }
    // A list hands a fresh setter every render; only a new query, cap or loan is news to the readers.
    const current = loans.get(list);
    if (current && current.query === query && current.maxLength === maxLength) { current.setQuery = setQuery; return; }
    loans.set(list, { query, setQuery, maxLength });
    emit();
  }, [list, query, setQuery, maxLength]);
  useLayoutEffect(() => () => { if (loans.delete(list)) emit(); }, [list]);
}

function lendingOn(screen: string | undefined): SearchableList | null {
  for (const list of loans.keys()) if (SEARCHABLE_LISTS[list].screen === screen) return list;
  return null;
}

/** The list on `screen` that lends its query now; re-renders only when that changes, not on every keystroke. */
export function useLendingList(screen: string | undefined): SearchableList | null {
  return useSyncExternalStore(subscribe, () => lendingOn(screen), () => null);
}

/** The bar's side: the lent query of `list`, or null when that list is not lending one. */
export function useListSearchLoan(list: SearchableList | null): Loan | null {
  return useSyncExternalStore(subscribe, () => (list ? loans.get(list) ?? null : null), () => null);
}
