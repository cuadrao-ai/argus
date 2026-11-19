import type { RecordRow } from "./transacciones-model";

import { exactMinor } from "./records-results-preview";
import { formatRecordActivityDate, recordRowKey } from "./records-row-preview";

export type RecordsSort = { key: "date" | "gross_amount" | "counterparty"; direction: "desc" | "asc" };
export const DEFAULT_RECORDS_SORT: RecordsSort = { key: "date", direction: "desc" };
export const RECORDS_SORT_OPTIONS: readonly (RecordsSort & { label: string })[] = [
  { key: "date", direction: "desc", label: "newest" },
  { key: "date", direction: "asc", label: "oldest" },
  { key: "gross_amount", direction: "desc", label: "amount_largest" },
  { key: "gross_amount", direction: "asc", label: "amount_smallest" },
  { key: "counterparty", direction: "asc", label: "name_ascending" },
  { key: "counterparty", direction: "desc", label: "name_descending" },
];
export const PAGE_SIZES = [25, 50, 100] as const;
export type PaginationState = { page: number; pageSize: (typeof PAGE_SIZES)[number] };
export const INITIAL_PAGINATION: PaginationState = { page: 1, pageSize: 25 };
export function paginateRecords(records: readonly RecordRow[], state: PaginationState, sort: RecordsSort = DEFAULT_RECORDS_SORT, locale = "es-419") {
  const currencies = new Set(records.map((row) => row.money.currency));
  const amountSortAvailable = currencies.size === 1 && !currencies.has("");
  const amountSortBlocked = sort.key === "gross_amount" && !amountSortAvailable;
  const effectiveSort = amountSortBlocked ? DEFAULT_RECORDS_SORT : sort;
  const collator = new Intl.Collator(locale, { sensitivity: "base", numeric: true });
  const value = (row: RecordRow): string | bigint | null => {
    if (effectiveSort.key === "counterparty") return row.counterparty?.trim() || null;
    if (effectiveSort.key === "date") return formatRecordActivityDate(row.occurredOn, locale) === "-" ? null : row.occurredOn;
    const minor = exactMinor(row.money);
    return minor === null ? null : minor < BigInt(0) ? -minor : minor;
  };
  const ordered = records.map((row) => ({ row, value: value(row) })).sort((a, b) => {
    if (a.value === null && b.value !== null) return 1;
    if (b.value === null && a.value !== null) return -1;
    const compared = a.value === null || b.value === null ? 0 : effectiveSort.key === "counterparty"
      ? collator.compare(String(a.value), String(b.value)) : a.value < b.value ? -1 : a.value > b.value ? 1 : 0;
    const left = recordRowKey(a.row), right = recordRowKey(b.row);
    return compared * (effectiveSort.direction === "desc" ? -1 : 1) || (left < right ? -1 : left > right ? 1 : 0);
  }).map(({ row }) => row);
  const count = ordered.length;
  const pages = Math.max(1, Math.ceil(count / state.pageSize));
  const page = Math.max(1, Math.min(state.page, pages));
  const offset = (page - 1) * state.pageSize;
  return { count, pages, page, effectiveSort, amountSortAvailable, amountSortBlocked, from: count ? offset + 1 : 0, to: Math.min(offset + state.pageSize, count), items: ordered.slice(offset, offset + state.pageSize) };
}
export function pageLinks(page: number, pages: number): (number | "gap")[] {
  const shown = [...new Set([1, pages, ...Array.from({ length: 5 }, (_, index) => page + index - 2)])].filter((value) => value >= 1 && value <= pages).sort((a, b) => a - b);
  return shown.flatMap((value, index): (number | "gap")[] => index > 0 && value - shown[index - 1] > 1 ? ["gap", value] : [value]);
}
