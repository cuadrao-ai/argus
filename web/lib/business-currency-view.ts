"use client";

import { useSyncExternalStore } from "react";

/**
 * The currency a person chose for a Business's figures: Inicio's month card and the Registros table read and set this
 * one choice, per Business, for the session (a reload starts from the Business's own currency again). A screen shows
 * the choice whenever its month or period holds that currency and the Business's own currency otherwise
 * (`currencyShown`); moving to another month never changes the choice, so it comes back once a month holds it again.
 */
const listeners = new Set<() => void>();
let views: Readonly<Record<string, string>> = {};

export function setCurrencyView(business: string, currency: string) {
  views = { ...views, [business]: currency };
  listeners.forEach((listener) => listener());
}

/** Tests start from no choice. */
export function resetCurrencyViews() {
  views = {};
  listeners.forEach((listener) => listener());
}

/** The chosen currency for this Business, or null when the person has not chosen one this session. */
export function useCurrencyView(business: string | null): string | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => (business === null ? null : views[business] ?? null),
    () => null,
  );
}
