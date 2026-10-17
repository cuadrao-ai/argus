import { describe, expect, test } from "bun:test";
import {
  formatSampleMoney,
  getSampleSummary,
  sampleMonths,
} from "../components/sample-data";

describe("illustrative business money", () => {
  test("keeps receivables separate from cash received", () => {
    const summary = getSampleSummary();
    expect(summary).toEqual({
      income: 245000,
      expenses: 168500,
      difference: 76500,
      receivables: 105500,
    });
    expect(sampleMonths[4].expenses).toBe(summary.expenses);
  });
  test.each(["es", "en"] as const)(
    "shows the original Dominican currency in %s",
    (locale) => {
      expect(formatSampleMoney(76500, locale)).toBe("RD$ 76,500");
    },
  );
});
