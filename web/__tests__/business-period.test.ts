import { test } from "bun:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";
import { ALL_FROM, customPeriod, periodRange } from "@/components/business-app/business-format";
import OutsidePeriodNote from "@/components/business-app/OutsidePeriodNote";

test("the period presets include everything and a typed range must be two days in order", () => {
  const now = new Date(2026, 9, 12);
  assert.deepEqual(periodRange("all", now), { key: "all", from: ALL_FROM, to: "2026-10-12" });
  assert.deepEqual(periodRange("this_month", now), { key: "this_month", from: "2026-10-01", to: "2026-10-12" });
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
