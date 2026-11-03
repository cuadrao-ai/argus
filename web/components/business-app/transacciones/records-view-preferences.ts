import type { ColumnKey } from "./TransaccionesTable";
import { DEFAULT_RECORDS_SORT, type RecordsSort } from "./records-pagination";
import type { Density } from "./table-density";

/** The Registros columns: the ledger's, with Categoría's slot given to the 606 tipo de gasto, forma de pago beside it, and Estado, Moneda and Notas added. */
export type RecordsColumnKey = Exclude<ColumnKey, "categoria"> | "tipo_gasto" | "forma_pago" | "estado" | "moneda" | "notas";
type RecordsColumn = { key: RecordsColumnKey; width: number | null; align: "left" | "right"; pin?: "left" | "right" };
export const RECORDS_PREVIEW_COLUMNS: readonly RecordsColumn[] = [
  { key: "contraparte", width: 200, align: "left", pin: "left" },
  { key: "fecha", width: 116, align: "left" },
  { key: "monto", width: 104, align: "right" },
  { key: "moneda", width: 80, align: "left" },
  { key: "detalle", width: 80, align: "left" },
  { key: "tipo_gasto", width: 120, align: "left" },
  { key: "forma_pago", width: 120, align: "left" },
  { key: "estado", width: 200, align: "left" },
  { key: "notas", width: 120, align: "left" },
  { key: "cuenta", width: 176, align: "left" },
  { key: "comprobante", width: 88, align: "right", pin: "right" },
];
/** A column of either table: Registros' own, or the ledger's when bank matching mounts the records beside its movements. */
export type TableColumnKey = RecordsColumnKey | ColumnKey;
/** Tipo de gasto and Forma de pago read the words Bandeja's review form uses, so the two screens never name a 606 field differently. */
export const recordsColumnLabelKey = (key: TableColumnKey) => key === "detalle" ? "business.transactions.layout.column_type" : key === "estado" ? "business.transactions.layout.column_state" : key === "comprobante" ? "business.transactions.layout.column_attachment" : key === "tipo_gasto" ? "business.dossier.placeholder.expense_type" : key === "forma_pago" ? "business.dossier.placeholder.payment_form" : `business.transactions.columns.${key}`;
export type RecordsViewPreferences = { order: RecordsColumnKey[]; hidden: RecordsColumnKey[]; density: Density; sort: RecordsSort };
export const requiredColumn = (key: RecordsColumnKey) => key === "contraparte" || key === "monto" || key === "moneda";
export const defaultRecordsPreferences = (): RecordsViewPreferences => ({ order: RECORDS_PREVIEW_COLUMNS.map(({ key }) => key), hidden: ["cuenta", "forma_pago"], density: "normal", sort: { ...DEFAULT_RECORDS_SORT } });
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
  const keys: RecordsColumnKey[] = ["contraparte" as const, ...value.order.filter((key) => key !== "contraparte" && (requiredColumn(key) || !value.hidden.includes(key)))];
  return keys.map((key, index) => {
    const column = RECORDS_PREVIEW_COLUMNS.find((item) => item.key === key)!;
    return { ...column, pin: key === "contraparte" ? "left" as const : key === "comprobante" && index === keys.length - 1 ? "right" as const : undefined };
  });
}
export function recordsMinimumWidth(columns: readonly { key: TableColumnKey; width: number | null }[], amount: { units: number; width: string }) {
  const other = columns.reduce((sum, column) => sum + (column.key === "monto" ? 0 : column.width ?? 288), 0);
  return amount.units ? `calc(${other + 24}px + ${amount.units}ch)` : `calc(${other}px + ${amount.width})`;
}
