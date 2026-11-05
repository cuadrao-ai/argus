"use client";

import { useEffect, useSyncExternalStore } from "react";

/**
 * Sheets never stack. Every open sheet or side drawer registers here in the
 * order it opened; only the newest one is drawn, and it shows a back arrow
 * that closes it and reveals the one beneath. Alerts are not sheets and do not
 * register: a full stop may sit over a sheet.
 */
let open: readonly string[] = [];
const listeners = new Set<() => void>();

function publish(next: readonly string[]) {
  open = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

const snapshot = () => open;

/** Where this sheet stands: drawn when it is the newest, with a back arrow when another waits beneath. */
export function useSheetStack(id: string, isOpen: boolean): { drawn: boolean; hasBelow: boolean } {
  useEffect(() => {
    if (!isOpen) return undefined;
    publish([...open.filter((item) => item !== id), id]);
    return () => publish(open.filter((item) => item !== id));
  }, [id, isOpen]);
  const stack = useSyncExternalStore(subscribe, snapshot, snapshot);
  const index = stack.indexOf(id);
  if (index < 0) return { drawn: isOpen, hasBelow: false };
  return { drawn: index === stack.length - 1, hasBelow: index > 0 };
}
