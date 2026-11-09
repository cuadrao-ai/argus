"use client";

import { useSyncExternalStore } from "react";

/**
 * Exportar registros asked for from outside Registros (the search command).
 * Registros opens its export dialog once its table is ready, then clears it.
 */
let requested = false;
const listeners = new Set<() => void>();

function publish(next: boolean) {
  if (requested === next) return;
  requested = next;
  listeners.forEach((listener) => listener());
}

export const clearRecordsExportRequest = () => publish(false);

/** The search command: Registros, then its export dialog. */
export function openRecordsExport(openPanel: (panel: { kind: "transactions" }) => void) {
  publish(true);
  openPanel({ kind: "transactions" });
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
};
const snapshot = () => requested;

export function useRecordsExportRequested(): boolean {
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}
