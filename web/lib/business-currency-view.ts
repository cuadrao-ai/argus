"use client";

import { useSyncExternalStore } from "react";
import { readStored, writeStored } from "@/lib/browser-storage";

/**
 * The currency a person chose for a Business's Inicio figures, per Business.
 * It lives in this browser until the server keeps `currency_view` per person
 * per Business; only this file changes then.
 */
const KEY = "cuadrao:business_currency_view:v1";
const CURRENCY = /^[A-Z]{3}$/;
const listeners = new Set<() => void>();
let views: Readonly<Record<string, string>> | null = null;

function read(): Readonly<Record<string, string>> {
  if (views !== null) return views;
  try {
    const parsed: unknown = JSON.parse(readStored(KEY) ?? "{}");
    views = parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? Object.fromEntries(Object.entries(parsed).filter((entry): entry is [string, string] => typeof entry[1] === "string" && CURRENCY.test(entry[1])))
      : {};
  } catch {
    views = {};
  }
  return views;
}

export function setCurrencyView(business: string, currency: string) {
  views = { ...read(), [business]: currency };
  writeStored(KEY, JSON.stringify(views));
  listeners.forEach((listener) => listener());
}

/** The remembered currency for this Business, or null when the person has not chosen one. */
export function useCurrencyView(business: string | null): string | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => (business === null ? null : read()[business] ?? null),
    () => null,
  );
}
