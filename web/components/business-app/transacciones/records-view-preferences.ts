import { COLUMNS, type ColumnKey } from "./TransaccionesTable";
import { DEFAULT_SUMMARY_METRICS, type SummaryMetric } from "./records-results-preview";
import type { Density } from "./table-density";

export type RecordsColumnKey = ColumnKey | "estado";
type RecordsColumn = { key: RecordsColumnKey; width: number | null; align: "left" | "right"; pin?: "left" | "right" };
export const RECORDS_PREVIEW_COLUMNS: readonly RecordsColumn[] = COLUMNS.flatMap<RecordsColumn>((column) => column.key === "categoria" ? [column, { key: "estado", width: 176, align: "left" }] : [{ ...column, width: column.key === "detalle" ? 104 : column.width }]);
export const recordsColumnLabelKey = (key: RecordsColumnKey) => key === "detalle" ? "business.transactions.layout.column_type" : key === "estado" ? "business.transactions.layout.column_state" : `business.transactions.columns.${key}`;
export type RecordsViewPreferences = { order: RecordsColumnKey[]; hidden: RecordsColumnKey[]; density: Density; summary: SummaryMetric[] };
export const requiredColumn = (key: RecordsColumnKey) => key === "contraparte" || key === "monto";
export const defaultRecordsPreferences = (): RecordsViewPreferences => ({ order: RECORDS_PREVIEW_COLUMNS.map(({ key }) => key), hidden: ["cuenta"], density: "normal", summary: [...DEFAULT_SUMMARY_METRICS] });
export function moveRecordsColumn(value: RecordsViewPreferences, key: RecordsColumnKey, target: number): RecordsViewPreferences {
  if (key === "contraparte") return value;
  const order = value.order.filter((item) => item !== key);
  order.splice(Math.max(1, Math.min(order.length, target)), 0, key);
  return { ...value, order };
}
export function toggleRecordsColumn(value: RecordsViewPreferences, key: RecordsColumnKey): RecordsViewPreferences {
  if (requiredColumn(key)) return value;
  return { ...value, hidden: value.hidden.includes(key) ? value.hidden.filter((item) => item !== key) : [...value.hidden, key] };
}
export function visibleRecordsColumns(value: RecordsViewPreferences) {
  const keys = ["contraparte" as const, ...value.order.filter((key) => key !== "contraparte" && (requiredColumn(key) || !value.hidden.includes(key)))];
  return keys.map((key, index) => {
    const column = RECORDS_PREVIEW_COLUMNS.find((item) => item.key === key)!;
    return { ...column, pin: key === "contraparte" ? "left" as const : key === "comprobante" && index === keys.length - 1 ? "right" as const : undefined };
  });
}
export function recordsMinimumWidth(columns: readonly { key: RecordsColumnKey; width: number | null }[], amount: { units: number; width: string }) {
  const other = columns.reduce((sum, column) => sum + (column.key === "monto" ? 0 : column.width ?? 288), 0);
  return amount.units ? `calc(${other + 24}px + ${amount.units}ch)` : `${other + 136}px`;
}
