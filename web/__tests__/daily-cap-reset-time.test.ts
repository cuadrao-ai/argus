import { describe, expect, test } from "bun:test";
import { dailyCapResetAtMs, formatDailyCapResetTime } from "../lib/daily-cap-reset-time";

const receivedAt = Date.parse("2026-09-26T18:00:00.700Z");
const midnight = Date.parse("2026-09-27T00:00:00Z");

describe("daily cap reset time", () => {
  test.each([
    ["en", "8:00\u00a0PM"],
    ["es-419", "8:00\u00a0PM"],
  ])("shows UTC midnight locally in the DR in %s", (language, expected) => {
    const resetAt = dailyCapResetAtMs("21600", receivedAt);
    expect(resetAt).toBe(midnight);
    expect(formatDailyCapResetTime(resetAt, language, "America/Santo_Domingo")).toBe(expected);
  });

  test("UTC+ zones retain the next local date and 12-hour time", () => {
    const resetAt = dailyCapResetAtMs("21600", receivedAt);
    const date = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(resetAt);
    expect(date).toBe("2026-09-27");
    for (const language of ["en", "es-419"]) {
      expect(formatDailyCapResetTime(resetAt, language, "Asia/Tokyo")).toBe("9:00\u00a0AM");
    }
  });

  test.each([
    ["2026-01-15T00:00:00Z", "7:00\u00a0PM"],
    ["2026-07-15T00:00:00Z", "8:00\u00a0PM"],
  ])("uses the browser zone's daylight-saving offset at %s", (resetAt, expected) => {
    for (const language of ["en", "es-419"]) {
      expect(formatDailyCapResetTime(Date.parse(resetAt), language, "America/New_York")).toBe(expected);
    }
  });

  test.each([undefined, null, "", "soon", "-5", "1.5", "99999999999999999999999"])(
    "missing or invalid header %s uses the next client-clock UTC midnight",
    (header) => expect(dailyCapResetAtMs(header, receivedAt)).toBe(midnight),
  );

  test.each([
    "Sun, 27 Sep 2026 00:00:00 GMT",
    "Sunday, 27-Sep-26 00:00:00 GMT",
    "Sun Sep 27 00:00:00 2026",
  ])("reuses HTTP-date parsing for %s without the 503 clamp", (header) => {
    expect(dailyCapResetAtMs(header, receivedAt)).toBe(midnight);
  });

  test("rounds subsecond receipt delays to the nearest minute", () => {
    expect(dailyCapResetAtMs("1", midnight - 100)).toBe(midnight);
  });

  test("fallback at UTC midnight means the following midnight", () => {
    expect(dailyCapResetAtMs(null, midnight)).toBe(midnight + 86_400_000);
  });
});
