import assert from "node:assert/strict";
import { test } from "bun:test";
import { formatRecordActivityDate, previewAmountColumnSize } from "@/components/business-app/transacciones/records-row-preview";
import { defaultRecordsPreferences, moveRecordsColumn, toggleRecordsColumn, visibleRecordsColumns } from "@/components/business-app/transacciones/records-view-preferences";

test("activity dates show a year in the selected language and reject missing or impossible days", () => {
  assert.equal(formatRecordActivityDate("2026-10-25", "es-419"), "25 oct 2026");
  assert.equal(formatRecordActivityDate("2026-10-25", "en"), "Oct 25, 2026");
  for (const invalid of [null, "", "2026-02-30", "2026-13-01", "2026-10-25T00:00:00Z"]) assert.equal(formatRecordActivityDate(invalid, "en"), "-");
});

test("amount and currency are required and adjacent only by default", () => {
  const initial = defaultRecordsPreferences();
  for (const key of ["contraparte", "monto", "moneda"] as const) assert.equal(toggleRecordsColumn(initial, key), initial);
  const keys = visibleRecordsColumns(initial).map(({ key }) => key);
  assert.equal(keys[keys.indexOf("monto") + 1], "moneda");
  assert.ok(keys.includes("notas"));
  const hiddenRequired = { ...initial, hidden: [...initial.hidden, "monto" as const, "moneda" as const] };
  assert.ok(visibleRecordsColumns(hiddenRequired).some(({ key }) => key === "monto"));
  assert.ok(visibleRecordsColumns(hiddenRequired).some(({ key }) => key === "moneda"));
});

test("numeric column sizing uses the exact number without a currency symbol", () => {
  assert.equal(previewAmountColumnSize([{ amount: "-24.00", currency: "USD" }], "en").width, "104px");
  const large = previewAmountColumnSize([{ amount: "-9007199254740993.01", currency: "DOP" }], "en");
  assert.ok(large.units >= 21);
  assert.equal(large.width, `calc(${large.units}ch + 24px)`);
});


test("preview labels exist at their exact EN and ES paths without renaming the overview", async () => {
  const es = (await import("@/public/locales/es-419/common.json")).default.business.transactions;
  const en = (await import("@/public/locales/en/common.json")).default.business.transactions;
  assert.equal(es.columns.moneda, "Moneda"); assert.equal(es.columns.notas, "Notas");
  assert.equal(en.columns.moneda, "Currency"); assert.equal(en.columns.notas, "Notes");
  assert.equal(es.layout.workflow.ready, "Listo"); assert.equal(en.layout.workflow.ready, "Ready");
  assert.equal(es.layout.column_attachment, "Adjunto"); assert.equal(en.layout.column_attachment, "Attachment");
  assert.equal(es.layout.overview.export.title, "Listos para exportar");
});

test("amount and currency move independently and rendered columns keep their chosen order", () => {
  const initial = defaultRecordsPreferences();
  for (const key of ["monto", "moneda"] as const) {
    for (const target of [1, initial.order.indexOf(key), initial.order.indexOf(key) + 1, initial.order.length - 1]) {
      const moved = moveRecordsColumn(initial, key, target);
      assert.equal(moved.order[target], key);
      assert.deepEqual(moved.order.filter((item) => item !== key), initial.order.filter((item) => item !== key));
      assert.deepEqual(visibleRecordsColumns(moved).map(({ key: item }) => item), moved.order.filter((item) => item !== "cuenta"));
    }
    assert.deepEqual(moveRecordsColumn(initial, key, initial.order.indexOf(key)), initial);
  }
});

test("column movement clamps after fixed counterparty and preserves required visibility", () => {
  const initial = defaultRecordsPreferences();
  assert.equal(moveRecordsColumn(initial, "contraparte", initial.order.length - 1), initial);
  for (const key of ["monto", "moneda", "detalle"] as const) {
    const first = moveRecordsColumn(initial, key, -5);
    assert.equal(first.order[0], "contraparte");
    assert.equal(first.order[1], key);
    const last = moveRecordsColumn(initial, key, 999);
    assert.equal(last.order.at(-1), key);
    assert.equal(last.order.length, initial.order.length);
    assert.equal(new Set(last.order).size, initial.order.length);
  }
});
