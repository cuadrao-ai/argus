import { useSyncExternalStore } from "react";
import { readStored, writeStored } from "@/lib/browser-storage";
import { isLastShownColumn, recordsColumnSettings, type ColumnLayout, type LayoutColumn } from "../transacciones/records-view-preferences";
import { DENSITIES, type Density } from "../transacciones/table-density";
import type { ReceptionView } from "./reception-model";

const KEYS = ["document", "file", "source", "sender", "amount", "currency", "status", "arrival"] as const;
export type ReceptionColumnKey = typeof KEYS[number];
type ReceptionColumn = LayoutColumn & { key: ReceptionColumnKey };
/** The tabs that draw these columns. Eliminados has its own. Listos never draws Estado: every row there is the same. */
const TABS = ["all", "attention", "listos"] as const;
const word = (key: string) => `business.reception_preview.${key}`;
/** Every row on Necesitan atención needs attention, so there the state column names why. */
export const statusColumnWord = (view: ReceptionView) => view === "attention" ? "status_reason" : "status";

/**
 * The columns Bandeja offers. This list is the web's: Bandeja joins receipts, notes and emails on the screen, so no
 * server report names its columns. The row's box and its actions are not here: they hold the first and last place.
 */
const receptionColumns = (view: ReceptionView): ReceptionColumn[] => KEYS.map(key => ({
  key,
  label_key: key === "currency" ? "business.transactions.columns.moneda" : word(key === "status" ? statusColumnWord(view) : key),
  families: key === "status" ? TABS.filter(tab => tab !== "listos") : TABS,
}));

/** The person's layout of Bandeja, kept on this device. */
export type ReceptionPreferences = { order: string[]; hidden: string[]; density: Density };
export const defaultReceptionPreferences = (): ReceptionPreferences => ({ order: [...KEYS], hidden: ["sender", "amount", "currency"], density: "amplio" });

/** The layout as the shared column menu and its rule read it. */
export const receptionLayout = (preferences: ReceptionPreferences, view: ReceptionView): ColumnLayout<ReceptionColumn> => ({ ...preferences, columns: receptionColumns(view) });

/** The shown columns, left to right. `status` is false on a tab that does not draw Estado. */
export function shownReceptionColumns(preferences: ReceptionPreferences, { status }: { status: boolean }): ReceptionColumnKey[] {
  return recordsColumnSettings(receptionLayout(preferences, "all")).filter(column => column.shown && (status || column.key !== "status")).map(column => column.key);
}

const STORAGE_KEY = "cuadrao:bandeja_columns:v1";
/** What the device kept, when it is still a layout of today's columns that the rule allows. Anything else reads as the default. */
function parseReceptionPreferences(stored: string | null): ReceptionPreferences {
  const initial = defaultReceptionPreferences();
  try {
    const kept: unknown = JSON.parse(stored ?? "null");
    if (!kept || typeof kept !== "object") return initial;
    const { order, hidden, density } = kept as Record<string, unknown>;
    const known = (value: unknown): value is string[] => Array.isArray(value) && new Set(value).size === value.length && value.every(key => (KEYS as readonly unknown[]).includes(key));
    if (!known(order) || order.length !== KEYS.length || !known(hidden) || !DENSITIES.includes(density as Density)) return initial;
    const layout = receptionLayout({ order, hidden: [], density: density as Density }, "all");
    // Hiding one at a time through the rule drops a hidden list that would leave a tab with no column.
    const allowed = hidden.reduce((value, key) => isLastShownColumn(value, key) ? value : { ...value, hidden: [...value.hidden, key] }, layout);
    return allowed.hidden.length === hidden.length ? { order, hidden, density: density as Density } : initial;
  } catch { return initial; }
}

const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
let read: { stored: string | null; value: ReceptionPreferences } | null = null;
function snapshot(): ReceptionPreferences {
  const stored = readStored(STORAGE_KEY);
  if (read?.stored !== stored) read = { stored, value: parseReceptionPreferences(stored) };
  return read.value;
}
const SERVER = defaultReceptionPreferences();
/** Bandeja's layout and its setter. The device's storage is the one copy, so a reload and a change of Business keep it. */
export function useReceptionPreferences(): [ReceptionPreferences, (next: ReceptionPreferences) => void] {
  return [useSyncExternalStore(subscribe, snapshot, () => SERVER), saveReceptionPreferences];
}
function saveReceptionPreferences({ order, hidden, density }: ReceptionPreferences): void {
  writeStored(STORAGE_KEY, JSON.stringify({ order, hidden, density }));
  listeners.forEach(listener => listener());
}
