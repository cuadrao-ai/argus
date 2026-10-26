import { COLUMNS, type ColumnKey } from "./TransaccionesTable";
import type { Density } from "./table-density";

export type RecordsViewPreferences = { order: ColumnKey[]; hidden: ColumnKey[]; density: Density };
export const requiredColumn = (key: ColumnKey) => key === "contraparte" || key === "monto";
export const defaultRecordsPreferences = (): RecordsViewPreferences => ({ order: COLUMNS.map(({ key }) => key), hidden: [], density: "normal" });
export function moveRecordsColumn(value: RecordsViewPreferences, key: ColumnKey, target: number): RecordsViewPreferences {
  if (key === "contraparte") return value;
  const order = value.order.filter((item) => item !== key);
  order.splice(Math.max(1, Math.min(order.length, target)), 0, key);
  return { ...value, order };
}
export function toggleRecordsColumn(value: RecordsViewPreferences, key: ColumnKey): RecordsViewPreferences {
  if (requiredColumn(key)) return value;
  return { ...value, hidden: value.hidden.includes(key) ? value.hidden.filter((item) => item !== key) : [...value.hidden, key] };
}
export function visibleRecordsColumns(value: RecordsViewPreferences) {
  const keys = ["contraparte" as const, ...value.order.filter((key) => key !== "contraparte" && (requiredColumn(key) || !value.hidden.includes(key)))];
  return keys.map((key, index) => {
    const column = COLUMNS.find((item) => item.key === key)!;
    return { ...column, pin: key === "contraparte" ? "left" as const : key === "comprobante" && index === keys.length - 1 ? "right" as const : undefined };
  });
}
export function recordsMinimumWidth(columns: ReturnType<typeof visibleRecordsColumns>, amount: { units: number; width: string }) {
  const other = columns.reduce((sum, column) => sum + (column.key === "monto" ? 0 : column.width ?? 288), 0);
  return amount.units ? `calc(${other + 24}px + ${amount.units}ch)` : `${other + 136}px`;
}
