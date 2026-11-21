import { useSyncExternalStore } from "react";
import { readStored, writeStored } from "@/lib/browser-storage";
import { isLastShownColumn, recordsColumnSettings, type ColumnLayout, type LayoutColumn } from "../transacciones/records-view-preferences";
import { DENSITIES, type Density } from "../transacciones/table-density";

const KEYS = ["file", "source", "sender", "amount", "currency", "status", "arrival"] as const;
export type ReceptionColumnKey = typeof KEYS[number];
type ReceptionColumn = LayoutColumn & { key: ReceptionColumnKey };
/** The tabs that draw these columns. Eliminados has its own. */
const TABS = ["all", "attention", "listos"] as const;
const word = (key: string) => `business.reception_preview.${key}`;

/**
 * The columns Bandeja offers. This list is the web's: Bandeja joins receipts, notes and emails on the screen, so no
 * server report names its columns. The row's box, Contenido and its actions are not here: Contenido is the row's
 * identity, so the box and Contenido hold the first places and the actions the last, by position.
 */
const receptionColumns: ReceptionColumn[] = KEYS.map(key => ({
  key,
  label_key: key === "currency" ? "business.transactions.columns.moneda" : word(key),
  families: TABS,
}));

/** The person's layout of Bandeja, kept on this device. */
export type ReceptionPreferences = { order: string[]; hidden: string[]; density: Density };
export const defaultReceptionPreferences = (): ReceptionPreferences => ({ order: [...KEYS], hidden: ["sender", "amount", "currency"], density: "amplio" });

/** The layout as the shared column menu and its rule read it. */
export const receptionLayout = (preferences: ReceptionPreferences): ColumnLayout<ReceptionColumn> => ({ ...preferences, columns: receptionColumns });

/** The shown columns, left to right. */
export function shownReceptionColumns(preferences: ReceptionPreferences): ReceptionColumnKey[] {
  return recordsColumnSettings(receptionLayout(preferences)).filter(column => column.shown).map(column => column.key);
}

const STORAGE_KEY = "cuadrao:bandeja_columns:v1";
/** What the device kept, when it is still a layout of today's columns that the rule allows. Anything else reads as the default. */
function parseReceptionPreferences(stored: string | null): ReceptionPreferences {
  const initial = defaultReceptionPreferences();
  try {
    const kept: unknown = JSON.parse(stored ?? "null");
    if (!kept || typeof kept !== "object") return initial;
    // Contenido was a column of this layout before it held its place, so a kept layout may still name it.
    const withoutContent = (value: unknown) => Array.isArray(value) ? value.filter(key => key !== "document") : value;
    const { order: keptOrder, hidden: keptHidden, density } = kept as Record<string, unknown>;
    const order = withoutContent(keptOrder), hidden = withoutContent(keptHidden);
    const known = (value: unknown): value is string[] => Array.isArray(value) && new Set(value).size === value.length && value.every(key => (KEYS as readonly unknown[]).includes(key));
    if (!known(order) || order.length !== KEYS.length || !known(hidden) || !DENSITIES.includes(density as Density)) return initial;
    const layout = receptionLayout({ order, hidden: [], density: density as Density });
    // Hiding one at a time through the rule drops a hidden list that would leave a tab with no column.
    const allowed = hidden.reduce((value, key) => isLastShownColumn(value, key) ? value : { ...value, hidden: [...value.hidden, key] }, layout);
    return allowed.hidden.length === hidden.length ? { order, hidden, density: density as Density } : initial;
  } catch { return initial; }
}

const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
/**
 * The layout this tab draws, with the stored text it matches. A change lands here even when the device refuses to keep
 * it, so storage only carries the layout to the next visit. Stored text that changes under it, from another tab, wins.
 */
let shown: { stored: string | null; value: ReceptionPreferences } | null = null;
function snapshot(): ReceptionPreferences {
  const stored = readStored(STORAGE_KEY);
  if (shown?.stored !== stored) shown = { stored, value: parseReceptionPreferences(stored) };
  return shown.value;
}
const SERVER = defaultReceptionPreferences();
/** Bandeja's layout and its setter. A reload and a change of Business keep it when the device's storage allows. */
export function useReceptionPreferences(): [ReceptionPreferences, (next: ReceptionPreferences) => void] {
  return [useSyncExternalStore(subscribe, snapshot, () => SERVER), saveReceptionPreferences];
}
function saveReceptionPreferences({ order, hidden, density }: ReceptionPreferences): void {
  writeStored(STORAGE_KEY, JSON.stringify({ order, hidden, density }));
  shown = { stored: readStored(STORAGE_KEY), value: { order, hidden, density } };
  listeners.forEach(listener => listener());
}
