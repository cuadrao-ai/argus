"use client";

import { useSyncExternalStore } from "react";
import { readStored, writeStored } from "@/lib/browser-storage";

/**
 * Interruptores con palabras: whether every switch rail shows its Sí and No.
 * On unless the person turned it off. It lives in this browser until the
 * account keeps it (`switch_labels` on `/me`); only this file changes then.
 */
const KEY = "cuadrao:switch_labels";
const listeners = new Set<() => void>();
let shown: boolean | null = null;

function read(): boolean {
  if (shown === null) shown = readStored(KEY) !== "false";
  return shown;
}

export function setSwitchLabelsShown(next: boolean) {
  shown = next;
  writeStored(KEY, next ? "true" : "false");
  listeners.forEach((listener) => listener());
}

export function useSwitchLabelsShown(): boolean {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    read,
    () => true,
  );
}
