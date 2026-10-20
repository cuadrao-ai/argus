"use client";

import { useSyncExternalStore } from "react";
import { readStored, writeStored } from "@/lib/browser-storage";

/**
 * Ocultar montos: one switch, kept per browser, that blurs every amount
 * marked `cuadrao-amount` through a flag on the document root. The numbers
 * stay in the page; only their look changes, so nothing reflows.
 */
const KEY = "cuadrao:hide_amounts";
const listeners = new Set<() => void>();
let hidden: boolean | null = null;

function read(): boolean {
  if (hidden === null) hidden = readStored(KEY) === "true";
  return hidden;
}

function apply(next: boolean) {
  if (typeof document !== "undefined") {
    if (next) document.documentElement.dataset.amountsHidden = "true";
    else delete document.documentElement.dataset.amountsHidden;
  }
}

export function setAmountsHidden(next: boolean) {
  hidden = next;
  writeStored(KEY, next ? "true" : "false");
  apply(next);
  listeners.forEach((listener) => listener());
}

export function useAmountsHidden(): boolean {
  const value = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      apply(read());
      return () => listeners.delete(listener);
    },
    read,
    () => false,
  );
  return value;
}
