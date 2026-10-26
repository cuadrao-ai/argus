import assert from "node:assert/strict";
import { test } from "bun:test";
import { INITIAL_PAGINATION, paginateRecords, pageLinks } from "@/components/business-app/transacciones/records-pagination";
import type { RecordRow } from "@/components/business-app/transacciones/transacciones-model";
const rows: RecordRow[] = Array.from({ length: 65 }, (_, index) => ({ id: `record-${String(index).padStart(2, "0")}`, kind: "gasto", occurredOn: `2026-10-${String(index % 28 + 1).padStart(2, "0")}`, counterparty: "Sample", money: { amount: "24.00", currency: "USD" }, categoryId: null, account: null, hasProof: false, marks: { personal: false, fiscal: null, markedBy: null }, opens: null }));
test("sorts all loaded records before slicing stable pages", () => {
  const first = paginateRecords(rows, INITIAL_PAGINATION);
  const second = paginateRecords(rows, { ...INITIAL_PAGINATION, page: 2 });
  assert.equal(first.count, 65); assert.equal(first.items.length, 25); assert.equal(second.from, 26); assert.equal(second.to, 50);
  assert.ok(first.items.at(-1)!.occurredOn >= second.items[0].occurredOn);
  assert.equal(new Set([...first.items, ...second.items].map((row) => row.id)).size, 50);
  const reverse = paginateRecords([...rows].reverse(), INITIAL_PAGINATION);
  assert.deepEqual(reverse.items.map((row) => row.id), first.items.map((row) => row.id));
});
test("handles zero, last page, size changes and shrinking data without invented counts", () => {
  const last = paginateRecords(rows, { ...INITIAL_PAGINATION, page: 3 });
  assert.equal(last.from, 51); assert.equal(last.to, 65); assert.equal(last.items.length, 15);
  assert.equal(paginateRecords(rows.slice(0, 6), { ...INITIAL_PAGINATION, page: 3 }).page, 1);
  assert.equal(paginateRecords(rows, { ...INITIAL_PAGINATION, pageSize: 50 }).items.length, 50);
  const empty = paginateRecords([], INITIAL_PAGINATION); assert.equal(empty.from, 0); assert.equal(empty.to, 0); assert.equal(empty.count, 0);
  assert.deepEqual(pageLinks(8, 20), [1, "gap", 6, 7, 8, 9, 10, "gap", 20]);
});
