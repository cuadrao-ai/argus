import { describe, expect, test } from "bun:test";
import i18next from "i18next";
import spanish from "../public/locales/es-419/common.json";
import { formatAmount, formatLateness, formatMoney, formatRelativeDay, formatRelativeTime, formatShortDay, UNKNOWN_VALUE } from "../components/business-app/business-format";

const now = new Date(2026, 9, 20, 12, 0, 0);
const ago = (ms: number) => new Date(now.getTime() - ms).toISOString();
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

describe("unknown values", () => {
  test("an unknown value is a plain short dash, which a negative amount's minus sign never becomes", () => {
    expect(UNKNOWN_VALUE).toBe("-");
    expect(UNKNOWN_VALUE).not.toBe("\u2014");
    expect(formatMoney(null, "DOP", "es-419")).toBe("");
    expect(formatMoney("-12.50", "DOP", "es-419")).toBe("-RD$ 12.50");
  });
});

describe("column amounts", () => {
  test("a row under a currency header is the number alone, exact and padded", () => {
    expect(formatAmount("58400", "DOP", "es-419")).toBe("58,400.00");
    expect(formatAmount("-12.5", "DOP", "es-419")).toBe("-12.50");
    expect(formatMoney("50.00", "USD", "es-419")).toBe("US$ 50.00");
  });
});

describe("whole units", () => {
  test("an overview total rounds half up from the decimal text to whole units", () => {
    expect(formatMoney("1444210.49", "DOP", "es-419", { decimals: 0 })).toBe("RD$ 1,444,210");
    expect(formatMoney("41829.50", "DOP", "es-419", { decimals: 0 })).toBe("RD$ 41,830");
    expect(formatMoney("999999.50", "DOP", "es-419", { decimals: 0 })).toBe("RD$ 1,000,000");
    expect(formatMoney("-41829.50", "DOP", "es-419", { decimals: 0 })).toBe("-RD$ 41,830");
    expect(formatMoney("-0.40", "DOP", "es-419", { decimals: 0 })).toBe("RD$ 0");
    expect(formatMoney("12345678901234567.50", "DOP", "es-419", { decimals: 0 })).toBe("RD$ 12,345,678,901,234,568", "beyond a float's exact range");
  });

  test("without decimals an amount keeps its exact cents", () => {
    expect(formatMoney("41829.50", "DOP", "es-419")).toBe("RD$ 41,829.50");
    expect(formatAmount("1.2345", "USD", "en")).toBe("1.2345");
    expect(formatAmount("41829.5", "DOP", "es-419", { decimals: 2 })).toBe("41,829.50");
  });
});

describe("relative time", () => {
  test("under seven days it is relative", () => {
    expect(formatRelativeTime(ago(15 * MINUTE), "es-419", now)).toBe("hace 15 minutos");
    expect(formatRelativeTime(ago(5 * HOUR), "es-419", now)).toBe("hace 5 horas");
    expect(formatRelativeTime(ago(30 * HOUR), "es-419", now)).toBe("ayer");
    expect(formatRelativeTime(ago(3 * DAY), "es-419", now)).toBe("hace 3 días");
    expect(formatRelativeTime(ago(7 * DAY - 1), "es-419", now)).toBe("hace 6 días");
  });

  test("from seven days on it is a short date, with the year only when it is not this year", () => {
    expect(formatRelativeTime(ago(7 * DAY), "es-419", now)).toBe("13 oct");
    expect(formatRelativeTime(new Date(2025, 11, 24, 9).toISOString(), "es-419", now)).toBe("24 dic 2025");
    expect(formatRelativeTime(null, "es-419", now)).toBe("");
  });

  test("a calendar day follows the same seven-day rule", () => {
    expect(formatRelativeDay("2026-10-20", "2026-10-20", "es-419")).toBe("hoy");
    expect(formatRelativeDay("2026-10-19", "2026-10-20", "es-419")).toBe("ayer");
    expect(formatRelativeDay("2026-10-14", "2026-10-20", "es-419")).toBe("hace 6 días");
    expect(formatRelativeDay("2026-10-13", "2026-10-20", "es-419")).toBe("13 oct");
    expect(formatRelativeDay("2026-10-27", "2026-10-20", "es-419")).toBe("27 oct");
    expect(formatShortDay("2025-10-02", "es-419", now)).toBe("2 oct 2025");
  });
});

describe("lateness chip", () => {
  const i18n = i18next.createInstance();
  void i18n.init({ lng: "es-419", initImmediate: false, resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const t = (key: string, options: { count?: number; defaultValue: string }) => i18n.t(key, options);
  const today = "2026-10-20";
  const late = (due: string) => formatLateness(due, today, t);

  test("calendar days on both sides of today, at 0, 1, 7 and 30", () => {
    expect(late("2026-10-20")).toEqual({ tone: "today", text: "vence hoy" });
    expect(late("2026-10-21")).toEqual({ tone: "upcoming", text: "vence en 1 día" });
    expect(late("2026-10-27")).toEqual({ tone: "upcoming", text: "vence en 7 días" });
    expect(late("2026-11-19")).toEqual({ tone: "upcoming", text: "vence en 30 días" });
    expect(late("2026-10-19")).toEqual({ tone: "overdue", text: "1 día tarde" });
    expect(late("2026-10-13")).toEqual({ tone: "overdue", text: "7 días tarde" });
    expect(late("2026-09-20")).toEqual({ tone: "overdue", text: "30 días tarde" });
  });

  test("a day that is not a calendar day has no chip", () => {
    expect(late("pronto")).toBe(null);
  });
});
