import type { RecordRow } from "./transacciones-model";

export type RecordsSort = "desc" | "asc";
export type PaginationState = { page: number; pageSize: 25 | 50 | 100; sort: RecordsSort };
export const INITIAL_PAGINATION: PaginationState = { page: 1, pageSize: 25, sort: "desc" };
export function paginateRecords(records: readonly RecordRow[], state: PaginationState) {
  const ordered = [...records].sort((a, b) => {
    const byDate = a.occurredOn.localeCompare(b.occurredOn);
    return (state.sort === "desc" ? -byDate : byDate) || `${a.kind}:${a.id}`.localeCompare(`${b.kind}:${b.id}`);
  });
  const count = ordered.length;
  const pages = Math.max(1, Math.ceil(count / state.pageSize));
  const page = Math.max(1, Math.min(state.page, pages));
  const offset = (page - 1) * state.pageSize;
  return { count, pages, page, from: count ? offset + 1 : 0, to: Math.min(offset + state.pageSize, count), items: ordered.slice(offset, offset + state.pageSize) };
}
export function pageLinks(page: number, pages: number): (number | "gap")[] {
  const shown = [...new Set([1, pages, ...Array.from({ length: 5 }, (_, index) => page + index - 2)])].filter((value) => value >= 1 && value <= pages).sort((a, b) => a - b);
  return shown.flatMap((value, index): (number | "gap")[] => index > 0 && value - shown[index - 1] > 1 ? ["gap", value] : [value]);
}
