import assert from "node:assert/strict";
import { test } from "bun:test";
import { formatDay } from "@/components/business-app/business-format";

const MONTHS = {
  "es-419": ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sept", "Oct", "Nov", "Dic"],
  en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
};
const iso = (month: number, day: number) => `2026-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;

test.each(MONTHS["es-419"].map((name, index) => [index + 1, name] as const))("month %d reads %s in Spanish, capitalized", (month, name) => {
  assert.equal(formatDay(iso(month, 1), "es-419"), `1 ${name} 2026`);
  assert.equal(formatDay(iso(month, 28), "es-419"), `28 ${name} 2026`);
});

test.each(MONTHS.en.map((name, index) => [index + 1, name] as const))("month %d reads %s in English", (month, name) => {
  assert.equal(formatDay(iso(month, 9), "en"), `${name} 9, 2026`);
});

test("a timestamp reads as its own day, and what is not a date passes through", () => {
  assert.equal(formatDay("2026-11-04T23:30:00Z", "es-419"), "4 Nov 2026");
  assert.equal(formatDay(null, "es-419"), "");
  assert.equal(formatDay("sin fecha", "es-419"), "sin fecha");
});
