import assert from "node:assert/strict";
import { test } from "bun:test";
import { formatRecordActivityDate, previewAmountColumnSize } from "@/components/business-app/transacciones/records-row-preview";
import { defaultRecordsPreferences, moveRecordsColumn, toggleRecordsColumn, visibleRecordsColumns } from "@/components/business-app/transacciones/records-view-preferences";

test("activity dates show a year in the selected language and reject missing or impossible days", () => {
  assert.equal(formatRecordActivityDate("2026-10-25", "es-419"), "25 oct 2026");
  assert.equal(formatRecordActivityDate("2026-10-25", "en"), "Oct 25, 2026");
  for (const invalid of [null, "", "2026-02-30", "2026-13-01", "2026-10-25T00:00:00Z"]) assert.equal(formatRecordActivityDate(invalid, "en"), "-");
});

test("currency stays visible beside amount when columns move or hide", () => {
  const initial = defaultRecordsPreferences();
  assert.equal(toggleRecordsColumn(initial, "moneda"), initial);
  const moved = moveRecordsColumn(initial, "monto", initial.order.length - 1);
  const keys = visibleRecordsColumns(moved).map(({ key }) => key);
  assert.equal(keys[keys.indexOf("monto") + 1], "moneda");
  const down = moveRecordsColumn(initial, "monto", initial.order.indexOf("monto") + 1);
  assert.ok(down.order.indexOf("monto") > initial.order.indexOf("monto"), "one arrow moves the linked pair past the next column");
  assert.ok(visibleRecordsColumns(initial).some(({ key }) => key === "notas"));
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

test("columns cross the amount/currency pair as a unit and counterparty stays fixed", () => {
  const initial = defaultRecordsPreferences();
  const expected = ["contraparte", "fecha", "detalle", "monto", "moneda", "categoria", "estado", "notas", "cuenta", "comprobante"];
  assert.deepEqual(moveRecordsColumn(initial, "detalle", initial.order.indexOf("detalle") - 1).order, expected);
  assert.deepEqual(moveRecordsColumn(initial, "monto", initial.order.indexOf("monto") + 1).order, expected);
  assert.equal(moveRecordsColumn(initial, "contraparte", initial.order.length - 1), initial);
});


test("currency handle moves the linked pair in both directions and clamps after counterparty", () => {
  const initial = defaultRecordsPreferences();
  const position = initial.order.indexOf("moneda");
  assert.deepEqual(moveRecordsColumn(initial, "moneda", position), initial);
  for (const target of [position - 1, position + 1, initial.order.length - 1, 0]) {
    const moved = moveRecordsColumn(initial, "moneda", target);
    assert.deepEqual(moved.order, moveRecordsColumn(initial, "monto", target - 1).order);
    assert.equal(moved.order[0], "contraparte");
    assert.equal(moved.order[moved.order.indexOf("monto") + 1], "moneda");
    assert.ok(!moved.hidden.includes("moneda"));
  }
  assert.equal(moveRecordsColumn(initial, "moneda", position - 1).order.indexOf("monto"), 1);
  assert.equal(moveRecordsColumn(initial, "moneda", position + 1).order.indexOf("monto"), 3);
});
