import { test } from "bun:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";
import english from "@/public/locales/en/common.json";
import { ALL_FROM, customPeriod, formatDaySpan, namedPeriod, periodRange, wholePeriod, wholePeriodKeyOf } from "@/components/business-app/business-format";
import OutsidePeriodNote from "@/components/business-app/OutsidePeriodNote";

test("the period presets include everything and a typed range must be two days in order", () => {
  const now = new Date(2026, 9, 12);
  // An open end is the server's today, so the browser clock never decides it.
  assert.deepEqual(periodRange("all", now), { key: "all", from: ALL_FROM, to: null });
  assert.deepEqual(periodRange("this_month", now), { key: "this_month", from: "2026-10-01", to: "2026-10-31" });
  assert.deepEqual(periodRange("this_year", now), { key: "this_year", from: "2026-01-01", to: "2026-12-31" });
  assert.deepEqual(periodRange("last_month", now), { key: "last_month", from: "2026-09-01", to: "2026-09-30" });
  assert.deepEqual(customPeriod("2026-08-01", "2026-08-31"), { key: "custom", from: "2026-08-01", to: "2026-08-31" });
  assert.equal(customPeriod("2026-08-31", "2026-08-01"), null);
  assert.equal(customPeriod("agosto", "2026-08-31"), null);
  assert.equal(customPeriod("", "2026-08-31"), null);
});

test("a saved expense outside the period is named with its date and a way to show it, in Spanish first", async () => {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const render = (count: number, latestOn: string | null) =>
    renderToStaticMarkup(createElement(I18nextProvider, { i18n }, createElement(OutsidePeriodNote, { count, latestOn, onShowAll: () => undefined })));
  const one = render(1, "2026-08-26");
  assert.match(one, /1 gasto guardado fuera de este período, el 26 ago 2026\./);
  assert.match(one, /Ver todos/);
  const three = render(3, "2026-08-26");
  assert.match(three, /3 gastos guardados fuera de este período, el último el 26 ago 2026\./);
  assert.equal(render(0, null), "");
});

test("the note reads in English too and never renders for a missing count", async () => {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "en", resources: { en: { translation: english } } });
  const render = (count: number, latestOn: string | null) =>
    renderToStaticMarkup(createElement(I18nextProvider, { i18n }, createElement(OutsidePeriodNote, { count, latestOn, onShowAll: () => undefined })));
  assert.match(render(1, "2026-08-26"), /1 expense saved outside this period, on Aug 26, 2026\./);
  assert.match(render(2, "2026-08-26"), /2 expenses saved outside this period, the latest on Aug 26, 2026\./);
  assert.match(render(2, "2026-08-26"), /Show all/);
  assert.equal(render(undefined as unknown as number, null), "");
  assert.equal(render(Number.NaN, null), "");
});

test("each whole period has one definition: the days the server resolves", () => {
  assert.deepEqual(wholePeriod("this_month", "2026-11-03"), { from: "2026-11-01", to: "2026-11-30" });
  assert.deepEqual(wholePeriod("last_month", "2026-03-31"), { from: "2026-02-01", to: "2026-02-28" });
  assert.deepEqual(wholePeriod("last_month", "2026-01-15"), { from: "2025-12-01", to: "2025-12-31" });
  assert.deepEqual(wholePeriod("this_year", "2028-06-10"), { from: "2028-01-01", to: "2028-12-31" });
  for (const key of ["this_month", "last_month", "this_year"] as const) {
    const { from, to } = periodRange(key, new Date(2026, 10, 3));
    assert.deepEqual({ from, to }, wholePeriod(key, "2026-11-03"));
  }
});

test("a range that is exactly a whole period is named by it, anything else is custom", () => {
  const today = "2026-11-03";
  assert.equal(wholePeriodKeyOf({ from: "2026-11-01", to: "2026-11-30" }, today), "this_month");
  assert.equal(wholePeriodKeyOf({ from: "2026-10-01", to: "2026-10-31" }, today), "last_month");
  assert.equal(wholePeriodKeyOf({ from: "2026-01-01", to: "2026-12-31" }, today), "this_year");
  assert.equal(wholePeriodKeyOf({ from: "2026-11-01", to: "2026-11-03" }, today), null);
  assert.deepEqual(namedPeriod({ from: "2026-11-01", to: "2026-11-30" }, today), { key: "this_month", from: "2026-11-01", to: "2026-11-30" });
  assert.deepEqual(namedPeriod({ from: "2026-11-01", to: "2026-11-03" }, today), { key: "custom", from: "2026-11-01", to: "2026-11-03" });
});

test("a span of days reads as months where it covers them whole, with the year once", () => {
  const span = (from: string, to: string, locale = "es-419") => formatDaySpan(from, to, locale);
  assert.deepEqual(span("2025-01-01", "2025-12-31"), { from: "ene", to: "dic 2025" });
  assert.deepEqual(span("2026-01-01", "2026-10-21"), { from: "ene", to: "21 oct 2026" });
  assert.deepEqual(span("2024-02-29", "2025-02-28"), { from: "29 feb 2024", to: "feb 2025" });
  assert.deepEqual(span("2025-03-01", "2025-03-31"), { from: "mar 2025", to: null });
  assert.deepEqual(span("2026-10-21", "2026-10-21"), { from: "21 oct 2026", to: null });
  assert.deepEqual(span("2025-01-01", "2025-12-31", "en"), { from: "Jan", to: "Dec 2025" });
  assert.deepEqual(span("not-a-day", "2025-12-31"), { from: "not-a-day", to: "2025-12-31" });
});
