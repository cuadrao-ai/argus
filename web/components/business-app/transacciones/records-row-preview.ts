import { formatAmount, UNKNOWN_VALUE } from "../business-format";
import { magnitude, type Money, type RecordRow } from "./transacciones-model";

export const recordRowKey = (row: RecordRow) => row.report?.row_id ?? `${row.kind}:${row.id}`;

export function formatRecordActivityDate(day: string | null, locale: string): string {
  if (!day || !/^\d{4}-\d{2}-\d{2}$/.test(day)) return UNKNOWN_VALUE;
  const date = new Date(`${day}T12:00:00Z`);
  if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== day) return UNKNOWN_VALUE;
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(date);
}

export function previewAmountColumnSize(values: readonly Money[], locale: string) {
  const longest = values.reduce((width, money) => Math.max(width, formatAmount(magnitude(money).amount, money.currency, locale).length), 0);
  const units = longest > 10 ? longest : 0;
  return { units, width: units ? `calc(${units}ch + 24px)` : "104px" };
}
