import { describe, expect, test } from "bun:test";

import { demoDates, demoDayKey, localDayKey } from "../lib/demo-date";

describe("demo day", () => {
  test.each([
    ["2026-11-01", "2026-11-15"],
    ["2026-11-15", "2026-11-15"],
    ["2026-11-16", "2026-11-16"],
    ["2027-01-20", "2027-01-20"],
  ])("on %s the scene shows %s", (today, shown) => {
    expect(demoDayKey(today)).toBe(shown);
  });

  test("reads the visitor's own calendar day", () => {
    expect(localDayKey(new Date(2026, 0, 5, 23, 30))).toBe("2026-01-05");
  });
});

describe("demo dates", () => {
  test("the campaign day closes October", () => {
    expect(demoDates("2026-11-15", "es")).toEqual({
      long: "domingo, 15 de noviembre",
      bar: "dom 15 nov",
      short: "15-11-2026",
      month: "Octubre",
      monthLower: "octubre",
    });
  });

  test("the closing month is always the month before", () => {
    expect(demoDates("2026-12-03", "es").month).toBe("Noviembre");
  });

  test("January closes December of the year before", () => {
    expect(demoDates("2027-01-20", "es").monthLower).toBe("diciembre");
  });

  test("English follows the same rule", () => {
    expect(demoDates("2026-12-03", "en")).toMatchObject({ month: "November", short: "03-12-2026" });
  });
});
