import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import RecordsLoadingPreview from "@/components/business-app/transacciones/RecordsLoadingPreview";
import RecordsOverviewPreview from "@/components/business-app/transacciones/RecordsOverviewPreview";
import { defaultRecordsPreferences, moveRecordsColumn, toggleRecordsColumn, visibleRecordsColumns } from "@/components/business-app/transacciones/records-view-preferences";
import spanish from "@/public/locales/es-419/common.json";

async function render(children: ReactNode) {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  return renderToStaticMarkup(<I18nextProvider i18n={i18n}>{children}</I18nextProvider>);
}

test("pending table follows selected columns, pinned identity, required amounts and density", async () => {
  let preferences = defaultRecordsPreferences();
  preferences = toggleRecordsColumn(preferences, "notas");
  preferences = toggleRecordsColumn(preferences, "monto");
  preferences = toggleRecordsColumn(preferences, "moneda");
  preferences = moveRecordsColumn(preferences, "moneda", 1);
  const html = await render(<RecordsLoadingPreview preferences={preferences} density="compacto" />);
  const columns = [...html.matchAll(/<th\b[^>]*data-col="([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(columns, visibleRecordsColumns(preferences).map(({ key }) => key));
  assert.equal(columns[0], "contraparte");
  assert.equal(columns[1], "moneda");
  assert.ok(columns.includes("monto"));
  assert.ok(!columns.includes("notas"));
  assert.match(html, /data-col="contraparte" data-pinned="left"/);
  assert.equal([...html.matchAll(/<tr style="height:40px"/g)].length, 8);
  assert.match(html, /data-testid="records-loading-pagination"/);
  assert.ok(!html.includes('aria-current="page"'));
  assert.match(html, /role="status" aria-label="Cargando\.\.\."/);
});

test("phone skeleton has the loaded list's two-line layout and the same container breakpoint", async () => {
  const html = await render(<RecordsLoadingPreview preferences={defaultRecordsPreferences()} density="amplio" />);
  assert.equal([...html.matchAll(/<li\b/g)].length, 8);
  assert.match(html, /<ul[^>]*><li[^>]*><div[^>]*><span[^>]*><span/);
  const css = readFileSync(new URL("../components/business-app/transacciones/records-loading-preview.module.css", import.meta.url), "utf8");
  const page = readFileSync(new URL("../components/business-app/transacciones/records-page.module.css", import.meta.url), "utf8");
  const breakpoint = "@container records (max-width:699.98px)";
  assert.ok(css.includes(breakpoint) && page.includes(breakpoint));
  assert.match(css, /\.table \{ display:none; \}/);
  assert.match(css, /\.narrow \{ display:block; \}/);
  assert.match(html, /aria-hidden="true"/);
});

test("unknown overview counts use placeholders only during a pending request", async () => {
  const props = { counts: { review: null, approval: null, export: null }, selected: [], onChoose: () => {} };
  const pending = await render(<RecordsOverviewPreview {...props} loading />);
  const settled = await render(<RecordsOverviewPreview {...props} />);
  assert.match(pending, /visibility:hidden/);
  assert.ok(!settled.includes("visibility:hidden"));
  assert.ok(settled.includes("sin dato") || settled.includes("Sin dato"));
});
