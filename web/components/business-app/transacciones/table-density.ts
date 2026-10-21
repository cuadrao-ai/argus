"use client";

import { useSyncExternalStore } from "react";
import { readStored, writeStored } from "@/lib/browser-storage";

/** Row heights in px (Lucas, October 21, 2026). Type stays 14px in every mode. */
export const DENSITY_ROW_PX = { compacto: 40, normal: 48, amplio: 56 } as const;
export type Density = keyof typeof DENSITY_ROW_PX;
export const DENSITIES = Object.keys(DENSITY_ROW_PX) as Density[];
export const DEFAULT_DENSITY: Density = "normal";

const KEY = "cuadrao:table_density";
const isDensity = (value: string | null): value is Density => value !== null && value in DENSITY_ROW_PX;

/**
 * The one owner of the person's table density. The browser keeps it until the
 * profile serves a preference; then only `read` and `write` change. Storage
 * that throws or is blocked reads as the default and writes nowhere.
 */
export const densityPreference = {
  read(): Density {
    const stored = readStored(KEY);
    return isDensity(stored) ? stored : DEFAULT_DENSITY;
  },
  write(next: Density): void {
    writeStored(KEY, next);
  },
};

const listeners = new Set<() => void>();
let current: Density | null = null;

function snapshot(): Density {
  if (current === null) current = densityPreference.read();
  return current;
}

export function setTableDensity(next: Density) {
  current = next;
  densityPreference.write(next);
  listeners.forEach((listener) => listener());
}

/** For tests: forget the value read, so the next read goes to storage again. */
export function resetTableDensity() {
  current = null;
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export function useTableDensity(): Density {
  return useSyncExternalStore(subscribe, snapshot, () => DEFAULT_DENSITY);
}
