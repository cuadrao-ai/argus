import type { ReportColumn, ReportColumnKey } from "@/lib/business-reports-api";
import { type RecordsSort } from "./records-pagination";
import type { Density } from "./table-density";

type Layout = { width: number | null; align: "left" | "right"; endPin?: true };
/** How each server column draws. The server says which columns the table offers and their names. Attachment pins right while it is last. */
export const RECORDS_COLUMN_LAYOUT: Record<ReportColumnKey, Layout> = {
  counterparty_id: { width: 128, align: "left" },
  counterparty: { width: 192, align: "left" },
  date: { width: 112, align: "left" },
  expense_type: { width: 160, align: "left" },
  net_amount: { width: 136, align: "right" },
  itbis_amount: { width: 124, align: "right" },
  gross_amount: { width: 104, align: "right" },
  stage: { width: 168, align: "left" },
  fiscal_number: { width: 136, align: "left" },
  note: { width: 120, align: "left" },
  attachment: { width: 80, align: "right", endPin: true },
  payment_form: { width: 160, align: "left" },
  funding: { width: 176, align: "left" },
};
/** The DGII's hyphens: an RNC reads 1-01-00157-7, a cédula 001-0000000-1. */
export function taxpayerIdText(digits: string): string {
  if (digits.length === 9) return `${digits[0]}-${digits.slice(1, 3)}-${digits.slice(3, 8)}-${digits[8]}`;
  if (digits.length === 11) return `${digits.slice(0, 3)}-${digits.slice(3, 10)}-${digits[10]}`;
  return digits;
}
/** Bandeja sizes its Moneda column from this entry until it owns that width (#2081). */
export const RECORDS_PREVIEW_COLUMNS: readonly { key: "moneda"; width: number | null }[] = [{ key: "moneda", width: 80 }];

/** The server's offered columns and the person's layout, in server keys. */
export type RecordsViewPreferences = { columns: readonly ReportColumn[]; order: string[]; hidden: string[]; density: Density; sort: RecordsSort };
export type RecordsTableColumn = ReportColumn & { width: number | null; align: "left" | "right"; pin?: "left" | "right" };

/** The offered columns in the person's order, each shown unless the layout hides it. */
export function recordsColumnSettings(value: RecordsViewPreferences): ReportColumn[] {
  return value.order.flatMap((key) => value.columns.filter((column) => column.key === key).map((column) => ({ ...column, shown: !value.hidden.includes(key) })));
}
export function moveRecordsColumn(value: RecordsViewPreferences, key: string, target: number): RecordsViewPreferences {
  const order = value.order.filter((item) => item !== key);
  order.splice(Math.max(0, Math.min(order.length, target)), 0, key);
  return { ...value, order };
}
/** A shown column stays when hiding it would leave some family's table with none: the server refuses that layout. Each column's `families` is the server's. */
export function isLastShownColumn(value: RecordsViewPreferences, key: string): boolean {
  const columns = recordsColumnSettings(value);
  const kept = columns.filter((column) => column.shown && column.key !== key);
  return kept.length < columns.filter((column) => column.shown).length
    && columns.flatMap((column) => column.families).some((family) => !kept.some((column) => column.families.includes(family)));
}
export function toggleRecordsColumn(value: RecordsViewPreferences, key: string): RecordsViewPreferences {
  if (isLastShownColumn(value, key)) return value;
  return { ...value, hidden: value.hidden.includes(key) ? value.hidden.filter((item) => item !== key) : [...value.hidden, key] };
}
/** The first column shown freezes on the left, whatever it is. */
export function visibleRecordsColumns(value: RecordsViewPreferences): RecordsTableColumn[] {
  const shown = recordsColumnSettings(value).filter((column) => column.shown);
  return shown.map((column, index) => {
    const { width, align, endPin } = RECORDS_COLUMN_LAYOUT[column.key];
    return { ...column, width, align, pin: index === 0 ? "left" as const : endPin && index === shown.length - 1 ? "right" as const : undefined };
  });
}
export function recordsMinimumWidth(columns: readonly { key: string; width: number | null }[], amount: { units: number; width: string }) {
  const other = columns.reduce((sum, column) => sum + (column.key === "gross_amount" ? 0 : column.width ?? 288), 0);
  return amount.units ? `calc(${other + 24}px + ${amount.units}ch)` : `calc(${other}px + ${amount.width})`;
}
