"use client";

import { useLayoutEffect, useSyncExternalStore } from "react";

/**
 * A list (Bandeja, Registros) keeps owning its text query: Registros' lives in its report request and URL,
 * Bandeja's in its return position. While the list is on screen it lends the query and its setter here, and the
 * top bar's search button and the search window read and write through the loan. No loan, no scope.
 */
export type SearchableList = "inbox" | "transactions";
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

/** Whether `list` lends its query now; re-renders only when that changes, not on every keystroke. */
export function useListLending(list: SearchableList | null): boolean {
  return useSyncExternalStore(subscribe, () => (list ? loans.has(list) : false), () => false);
}

/** The bar's side: the lent query of `list`, or null when that list is not lending one. */
export function useListSearchLoan(list: SearchableList | null): Loan | null {
  return useSyncExternalStore(subscribe, () => (list ? loans.get(list) ?? null : null), () => null);
}
