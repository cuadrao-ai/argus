"use client";

import { useEffect, useSyncExternalStore } from "react";

/**
 * One primary per screen. Agregar is the primary of every screen with no main
 * action of its own. A screen whose main action is its own (Transacciones:
 * Igualar sugerencias) claims the primary while that action shows, and the
 * top bar's Agregar steps down to secondary until the claim ends.
 */
let claims = 0;
const listeners = new Set<() => void>();
const publish = () => listeners.forEach((listener) => listener());

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};
const snapshot = () => claims > 0;

/** True while a screen holds the primary. */
export function useScreenPrimaryClaimed(): boolean {
  return useSyncExternalStore(subscribe, snapshot, () => false);
}

/** Hold the primary while `active`; released on unmount. */
export function useClaimScreenPrimary(active: boolean) {
  useEffect(() => {
    if (!active) return undefined;
    claims += 1;
    publish();
    return () => {
      claims -= 1;
      publish();
    };
  }, [active]);
}
