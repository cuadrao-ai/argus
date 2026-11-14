import assert from "node:assert/strict";
import { test } from "bun:test";
import { formatRecordActivityDate, previewAmountColumnSize } from "@/components/business-app/transacciones/records-row-preview";
import { sampleRecordsPreferences } from "@/components/business-app/transacciones/sample-records-preferences";
import { moveRecordsColumn, toggleRecordsColumn, visibleRecordsColumns } from "@/components/business-app/transacciones/records-view-preferences";

test("activity dates show a year in the selected language and reject missing or impossible days", () => {
  assert.equal(formatRecordActivityDate("2026-10-25", "es-419"), "25 oct 2026");
  assert.equal(formatRecordActivityDate("2026-10-25", "en"), "Oct 25, 2026");
  for (const invalid of [null, "", "2026-02-30", "2026-13-01", "2026-10-25T00:00:00Z"]) assert.equal(formatRecordActivityDate(invalid, "en"), "-");
});

test("the table shows only the server's columns: no Moneda or Detalle of the ledger", () => {
  const keys: string[] = visibleRecordsColumns(sampleRecordsPreferences()).map(({ key }) => key);
  assert.equal(keys.includes("moneda"), false);
  assert.equal(keys.includes("detalle"), false);
  assert.ok(keys.includes("gross_amount"));
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

test("visible columns move independently and rendered columns keep their chosen order", () => {
  const initial = sampleRecordsPreferences();
  for (const key of ["gross_amount", "date"] as const) {
    for (const target of [1, initial.order.indexOf(key), initial.order.indexOf(key) + 1, initial.order.length - 1]) {
      const moved = moveRecordsColumn(initial, key, target);
      assert.equal(moved.order[target], key);
      assert.deepEqual(moved.order.filter((item) => item !== key), initial.order.filter((item) => item !== key));
      assert.deepEqual(visibleRecordsColumns(moved).map(({ key: item }) => item), moved.order.filter((item) => !initial.hidden.includes(item)));
    }
    assert.deepEqual(moveRecordsColumn(initial, key, initial.order.indexOf(key)), initial);
  }
});

test("column movement clamps to the ends and keeps every column once", () => {
  const initial = sampleRecordsPreferences();
  for (const key of ["counterparty_id", "gross_amount", "date", "note"] as const) {
    assert.equal(moveRecordsColumn(initial, key, -5).order[0], key);
    const last = moveRecordsColumn(initial, key, 999);
    assert.equal(last.order.at(-1), key);
    assert.equal(last.order.length, initial.order.length);
    assert.equal(new Set(last.order).size, initial.order.length);
  }
});
