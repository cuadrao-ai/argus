import assert from "node:assert/strict";
import { test } from "bun:test";
import { formatDate, formatDay, formatDaySpan, formatMonthYear, formatRelativeDay, formatRelativeTime, formatShortDay, formatTimestamp } from "@/components/business-app/business-format";

const SHORT = {
  "es-419": ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sept", "Oct", "Nov", "Dic"],
  en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
};
const LONG = {
  "es-419": ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"],
  en: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
};
const iso = (month: number, day: number, year = 2026) => `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
const months = (locale: keyof typeof SHORT) => SHORT[locale].map((short, index) => [index + 1, short, LONG[locale][index]] as const);
const NOW = new Date(2027, 5, 15, 9);

test.each(months("es-419"))("month %d reads %s in Spanish in every Business date", (month, short, long) => {
  assert.equal(formatDay(iso(month, 1), "es-419"), `1 ${short} 2026`);
  assert.equal(formatDay(iso(month, 28), "es-419"), `28 ${short} 2026`);
  assert.match(formatTimestamp(new Date(2026, month - 1, 22, 10, 12).toISOString(), "es-419"), new RegExp(`^22 ${short} 2026, 10:12\\sa\\.\\s?m\\.$`));
  assert.equal(formatShortDay(iso(month, 12), "es-419", NOW), `12 ${short} 2026`);
  assert.equal(formatShortDay(iso(month, 12, 2027), "es-419", NOW), `12 ${short}`);
  assert.equal(formatRelativeTime(new Date(2026, month - 1, 12, 9).toISOString(), "es-419", NOW), `12 ${short} 2026`);
  assert.equal(formatRelativeDay(iso(month, 12), "2027-06-15", "es-419"), `12 ${short} 2026`);
  assert.deepEqual(formatDaySpan(iso(month, 1), iso(month, 28), "es-419"), month === 2 ? { from: "Feb 2026", to: null } : { from: short, to: `28 ${short} 2026` });
  assert.deepEqual(formatDaySpan(iso(month, 2, 2025), iso(month, 3), "es-419"), { from: `2 ${short} 2025`, to: `3 ${short} 2026` });
  assert.equal(formatMonthYear(iso(month, 9), "es-419"), `${long} de 2026`);
});

test.each(months("en"))("month %d reads %s in English, as before", (month, short, long) => {
  assert.equal(formatDay(iso(month, 9), "en"), `${short} 9, 2026`);
  assert.match(formatTimestamp(new Date(2026, month - 1, 22, 10, 12).toISOString(), "en"), new RegExp(`^${short} 22, 2026(,| at) 10:12\\sAM$`));
  assert.equal(formatShortDay(iso(month, 12), "en", NOW), `${short} 12, 2026`);
  assert.equal(formatShortDay(iso(month, 12, 2027), "en", NOW), `${short} 12`);
  assert.equal(formatRelativeTime(new Date(2026, month - 1, 12, 9).toISOString(), "en", NOW), `${short} 12, 2026`);
  assert.equal(formatRelativeDay(iso(month, 12), "2027-06-15", "en"), `${short} 12, 2026`);
  assert.deepEqual(formatDaySpan(iso(month, 2, 2025), iso(month, 3), "en"), { from: `${short} 2, 2025`, to: `${short} 3, 2026` });
  assert.equal(formatMonthYear(iso(month, 9), "en"), `${long} 2026`);
});

test("English dates are what the platform prints, untouched", () => {
  const date = new Date(2026, 10, 22, 10, 12);
  for (const options of [{ day: "numeric", month: "short", year: "numeric" }, { dateStyle: "medium", timeStyle: "short" }, { month: "long", year: "numeric" }] as Intl.DateTimeFormatOptions[]) {
    assert.equal(formatDate(date, "en", options), new Intl.DateTimeFormat("en", options).format(date));
  }
});

test("a medium date carries the same capital month", () => {
  assert.match(formatDate(new Date(2026, 10, 22, 10, 12), "es-419", { dateStyle: "medium", timeStyle: "short" }), /^22 Nov 2026, 10:12\sa\.\s?m\.$/);
});

test("a timestamp reads as its own day, and what is not a date passes through", () => {
  assert.equal(formatDay("2026-11-04T23:30:00Z", "es-419"), "4 Nov 2026");
  assert.equal(formatDay(null, "es-419"), "");
  assert.equal(formatDay("sin fecha", "es-419"), "sin fecha");
  assert.equal(formatTimestamp("sin fecha", "es-419"), "sin fecha");
  assert.equal(formatShortDay("sin fecha", "es-419"), "sin fecha");
});
