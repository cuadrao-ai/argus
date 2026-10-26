import { COLUMNS, type ColumnKey } from "./TransaccionesTable";
import type { Density } from "./table-density";

export type RecordsColumnKey = ColumnKey | "estado" | "moneda" | "notas";
type RecordsColumn = { key: RecordsColumnKey; width: number | null; align: "left" | "right"; pin?: "left" | "right" };
export const RECORDS_PREVIEW_COLUMNS: readonly RecordsColumn[] = COLUMNS.flatMap<RecordsColumn>((column) => {
  if (column.key === "monto") return [{ ...column, width: 104 }, { key: "moneda", width: 80, align: "left" }];
  if (column.key === "categoria") return [{ ...column, width: 120 }, { key: "estado", width: 136, align: "left" }, { key: "notas", width: 160, align: "left" }];
  const widths: Partial<Record<ColumnKey, number>> = { contraparte: 200, fecha: 126, detalle: 80, comprobante: 88 };
  const width = widths[column.key];
  return [{ ...column, width: width ?? column.width }];
});
export const recordsColumnLabelKey = (key: RecordsColumnKey) => key === "detalle" ? "business.transactions.layout.column_type" : key === "estado" ? "business.transactions.layout.column_state" : key === "comprobante" ? "business.transactions.layout.column_attachment" : `business.transactions.columns.${key}`;
export type RecordsViewPreferences = { order: RecordsColumnKey[]; hidden: RecordsColumnKey[]; density: Density; summary: boolean };
export const requiredColumn = (key: RecordsColumnKey) => key === "contraparte" || key === "monto" || key === "moneda";
export const defaultRecordsPreferences = (): RecordsViewPreferences => ({ order: RECORDS_PREVIEW_COLUMNS.map(({ key }) => key), hidden: ["cuenta"], density: "normal", summary: true });
export function moveRecordsColumn(value: RecordsViewPreferences, key: RecordsColumnKey, target: number): RecordsViewPreferences {
  if (key === "contraparte" || key === "moneda") return value;
  const moving: RecordsColumnKey[] = key === "monto" ? ["monto", "moneda"] : [key];
  const order = value.order.filter((item) => !moving.includes(item));
  const destination = key !== "monto" && target < value.order.indexOf(key) && order[target] === "moneda" ? target - 1 : target;
  order.splice(Math.max(1, Math.min(order.length, destination)), 0, ...moving);
  const linked: RecordsColumnKey[] = order.filter((item) => item !== "moneda");
  linked.splice(linked.indexOf("monto") + 1, 0, "moneda");
  return { ...value, order: linked };
}
export function toggleRecordsColumn(value: RecordsViewPreferences, key: RecordsColumnKey): RecordsViewPreferences {
  if (requiredColumn(key)) return value;
  return { ...value, hidden: value.hidden.includes(key) ? value.hidden.filter((item) => item !== key) : [...value.hidden, key] };
}
export function visibleRecordsColumns(value: RecordsViewPreferences) {
  const keys: RecordsColumnKey[] = ["contraparte" as const, ...value.order.filter((key) => key !== "contraparte" && key !== "moneda" && (requiredColumn(key) || !value.hidden.includes(key)))];
  keys.splice(keys.indexOf("monto") + 1, 0, "moneda");
  return keys.map((key, index) => {
    const column = RECORDS_PREVIEW_COLUMNS.find((item) => item.key === key)!;
    return { ...column, pin: key === "contraparte" ? "left" as const : key === "comprobante" && index === keys.length - 1 ? "right" as const : undefined };
  });
}
export function recordsMinimumWidth(columns: readonly { key: RecordsColumnKey; width: number | null }[], amount: { units: number; width: string }) {
  const other = columns.reduce((sum, column) => sum + (column.key === "monto" ? 0 : column.width ?? 288), 0);
  return amount.units ? `calc(${other + 24}px + ${amount.units}ch)` : `calc(${other}px + ${amount.width})`;
}
