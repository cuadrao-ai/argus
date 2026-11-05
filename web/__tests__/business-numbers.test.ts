import { describe, expect, test } from "bun:test";
import i18next from "i18next";
import spanish from "../public/locales/es-419/common.json";
import { formatAmount, formatHeadlineMoney, formatLateness, formatMoney, formatRelativeDay, formatRelativeTime, formatShortDay, UNKNOWN_VALUE } from "../components/business-app/business-format";

const now = new Date(2026, 9, 20, 12, 0, 0);
const ago = (ms: number) => new Date(now.getTime() - ms).toISOString();
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

describe("headline figures", () => {
  test("below 10,000 a headline is exact", () => {
    expect(formatHeadlineMoney("9999.99", "DOP", "es-419")).toEqual({ short: "RD$ 9,999.99", exact: "RD$ 9,999.99" });
  });

  test("the row's largest figure picks one unit for every figure beside it", () => {
    const row = ["58400.00", "9600.00", "-7902.00", "0.00"];
    expect(formatHeadlineMoney("9600.00", "DOP", "es-419", row)).toEqual({ short: "RD$ 9.6 mil", exact: "RD$ 9,600.00" });
    expect(formatHeadlineMoney("-7902.00", "DOP", "es-419", row).short).toBe("-RD$ 7.9 mil");
    expect(formatHeadlineMoney("0.00", "DOP", "es-419", row).short).toBe("RD$ 0.00", "a figure that would read 0 in the row's unit shows its real amount");
    expect(formatHeadlineMoney("40.00", "DOP", "es-419", ["58000.00", "40.00"]).short).toBe("RD$ 40.00");
    expect(formatHeadlineMoney("9600.00", "DOP", "es-419", ["9600.00", "944.00"]).short).toBe("RD$ 9,600.00");
    expect(formatHeadlineMoney("58400.00", "DOP", "es-419", ["58400.00", "1300000.00"]).short).toBe("RD$ 0.1 M");
  });

  test("from 10,000 up Spanish reads mil and M, never k, with the exact amount beside it", () => {
    expect(formatHeadlineMoney("10000.00", "DOP", "es-419")).toEqual({ short: "RD$ 10 mil", exact: "RD$ 10,000.00" });
    expect(formatHeadlineMoney("58400.00", "DOP", "es-419")).toEqual({ short: "RD$ 58.4 mil", exact: "RD$ 58,400.00" });
    expect(formatHeadlineMoney("1300000.00", "DOP", "es-419").short).toBe("RD$ 1.3 M");
    expect(formatHeadlineMoney("58400.00", "DOP", "en").short).toBe("RD$ 58.4K");
  });

  test("rounding is half up from the decimal text and moves to the next unit at 1,000", () => {
    expect(formatHeadlineMoney("58449.99", "DOP", "es-419").short).toBe("RD$ 58.4 mil");
    expect(formatHeadlineMoney("58450.00", "DOP", "es-419").short).toBe("RD$ 58.5 mil");
    expect(formatHeadlineMoney("999960.00", "DOP", "es-419").short).toBe("RD$ 1 M");
    expect(formatHeadlineMoney("-58400.00", "DOP", "es-419")).toEqual({ short: "-RD$ 58.4 mil", exact: "-RD$ 58,400.00" });
  });
});

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
