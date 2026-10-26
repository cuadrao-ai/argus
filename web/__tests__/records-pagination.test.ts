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


test("amount ordering uses exact magnitude across all pages and missing values stay last", () => {
  const item = (id: string, amount: string): RecordRow => ({ ...rows[0], id, money: { amount, currency: "USD" } });
  const items = [item("small", "-9007199254740993.01"), item("large", "9007199254740993.02"), item("missing", ""), item("zero", "0.00")];
  const descending = paginateRecords(items, INITIAL_PAGINATION, { key: "monto", direction: "desc" });
  assert.deepEqual(descending.items.map(({ id }) => id), ["large", "small", "zero", "missing"]);
  assert.deepEqual(paginateRecords(items, INITIAL_PAGINATION, { key: "monto", direction: "asc" }).items.map(({ id }) => id), ["zero", "small", "large", "missing"]);
  const many = Array.from({ length: 30 }, (_, i) => item(String(i), `${i}.00`));
  assert.equal(paginateRecords(many, { ...INITIAL_PAGINATION, page: 2 }, { key: "monto", direction: "desc" }).items[0].id, "4");
});

test("mixed or unavailable currency blocks amount ordering across the whole result set", () => {
  const mixed = [...rows.slice(0, 26), { ...rows[0], id: "dop", money: { amount: "1.00", currency: "DOP" } }];
  const result = paginateRecords(mixed, INITIAL_PAGINATION, { key: "monto", direction: "desc" });
  assert.equal(result.amountSortAvailable, false); assert.equal(result.amountSortBlocked, true);
  assert.deepEqual(result.effectiveSort, { key: "fecha", direction: "desc" });
  assert.deepEqual(result.items, paginateRecords(mixed, INITIAL_PAGINATION).items);
  assert.equal(paginateRecords([{ ...rows[0], money: { amount: "1", currency: "" } }], INITIAL_PAGINATION).amountSortAvailable, false);
  assert.equal(paginateRecords([], INITIAL_PAGINATION).amountSortAvailable, false);
});

test("name sorting is locale-aware, invalid values stay last, and ties use kind and ID", () => {
  const items = [
    { ...rows[0], id: "z", counterparty: "Zebra", occurredOn: "" },
    { ...rows[0], id: "a", counterparty: "Álvaro", occurredOn: "2026-02-30" },
    { ...rows[0], id: "b", counterparty: null },
    { ...rows[0], id: "c", counterparty: "Álvaro", kind: "venta" as const },
  ];
  assert.deepEqual(paginateRecords(items, INITIAL_PAGINATION, { key: "contraparte", direction: "asc" }, "es-419").items.map(({ id }) => id), ["a", "c", "z", "b"]);
  assert.deepEqual(paginateRecords(items, INITIAL_PAGINATION, { key: "contraparte", direction: "desc" }, "es-419").items.map(({ id }) => id), ["z", "a", "c", "b"]);
  const dates = paginateRecords(items, INITIAL_PAGINATION, { key: "fecha", direction: "asc" });
  assert.deepEqual(dates.items.map(({ id }) => id), ["b", "c", "a", "z"]);
  assert.deepEqual(paginateRecords([...items].reverse(), INITIAL_PAGINATION, { key: "fecha", direction: "asc" }).items, dates.items);
});
