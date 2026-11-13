import type { ReportColumn, ReportColumnKey } from "@/lib/business-reports-api";
import { type RecordsSort } from "./records-pagination";
import type { Density } from "./table-density";

type Layout = { width: number | null; align: "left" | "right"; endPin?: true };
/** How each server column draws. The server says which columns the table offers, their names and their rules. Attachment pins right while it is last. */
export const RECORDS_COLUMN_LAYOUT: Record<ReportColumnKey, Layout> = {
  counterparty: { width: 200, align: "left" },
  fiscal_number: { width: 176, align: "left" },
  date: { width: 116, align: "left" },
  net_amount: { width: 160, align: "right" },
  itbis_amount: { width: 160, align: "right" },
  gross_amount: { width: 104, align: "right" },
  stage: { width: 200, align: "left" },
  note: { width: 120, align: "left" },
  attachment: { width: 88, align: "right", endPin: true },
  expense_type: { width: 120, align: "left" },
  payment_form: { width: 120, align: "left" },
  funding: { width: 176, align: "left" },
};
/** Bandeja sizes its Moneda column from this entry until it owns that width (#2081). */
export const RECORDS_PREVIEW_COLUMNS: readonly { key: "moneda"; width: number | null }[] = [{ key: "moneda", width: 80 }];

/** The server's offered columns and the person's layout, in server keys. */
export type RecordsViewPreferences = { columns: readonly ReportColumn[]; order: string[]; hidden: string[]; density: Density; sort: RecordsSort };
export type RecordsTableColumn = ReportColumn & { width: number | null; align: "left" | "right"; pin?: "left" | "right" };

/** The offered columns in the person's order, each shown unless the layout hides it. The server's required columns always show. */
export function recordsColumnSettings(value: RecordsViewPreferences): ReportColumn[] {
  return value.order.flatMap((key) => value.columns.filter((column) => column.key === key).map((column) => ({ ...column, shown: column.required || !value.hidden.includes(key) })));
}
/** The server's pinned columns lead and do not move. */
export function moveRecordsColumn(value: RecordsViewPreferences, key: string, target: number): RecordsViewPreferences {
  const pinned = value.columns.filter((column) => column.pinned).length;
  if (value.columns.some((column) => column.key === key && column.pinned)) return value;
  const order = value.order.filter((item) => item !== key);
  order.splice(Math.max(pinned, Math.min(order.length, target)), 0, key);
  return { ...value, order };
}
export function toggleRecordsColumn(value: RecordsViewPreferences, key: string): RecordsViewPreferences {
  if (value.columns.some((column) => column.key === key && column.required)) return value;
  return { ...value, hidden: value.hidden.includes(key) ? value.hidden.filter((item) => item !== key) : [...value.hidden, key] };
}
export function visibleRecordsColumns(value: RecordsViewPreferences): RecordsTableColumn[] {
  const shown = recordsColumnSettings(value).filter((column) => column.shown);
  return shown.map((column, index) => {
    const { width, align, endPin } = RECORDS_COLUMN_LAYOUT[column.key];
    return { ...column, width, align, pin: column.pinned ? "left" as const : endPin && index === shown.length - 1 ? "right" as const : undefined };
  });
}
export function recordsMinimumWidth(columns: readonly { key: string; width: number | null }[], amount: { units: number; width: string }) {
  const other = columns.reduce((sum, column) => sum + (column.key === "gross_amount" ? 0 : column.width ?? 288), 0);
  return amount.units ? `calc(${other + 24}px + ${amount.units}ch)` : `calc(${other}px + ${amount.width})`;
}
