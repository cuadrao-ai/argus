import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { RECEIPT_ATTENTIONS } from "@/lib/business-api";
import en from "../public/locales/en/common.json";
import es419 from "../public/locales/es-419/common.json";

/** The `attention` enum the checked OpenAPI artifact declares for ReceiptSummary. */
function openApiAttentions(): string[] {
  const lines = readFileSync(join(import.meta.dir, "../../docs/api/openapi.yaml"), "utf8").split("\n");
  const start = lines.findIndex((line) => line === "    ReceiptSummary:");
  const field = lines.findIndex((line, index) => index > start && line === "        attention:");
  const values: string[] = [];
  for (const line of lines.slice(field + 1)) {
    const value = line.match(/^ {12}- ([a-z_]+)$/);
    if (value) values.push(value[1]);
    else if (values.length) break;
  }
  return values;
}

describe("Business receipt attention", () => {
  test("the web knows exactly the categories the API declares", () => {
    expect([...RECEIPT_ATTENTIONS].sort()).toEqual(openApiAttentions().sort());
  });

  test("every category has owner copy in es-419 and English, without em dashes", () => {
    for (const locale of [es419, en]) {
      const copy = locale.business.attention as Record<string, string>;
      expect(Object.keys(copy).sort()).toEqual([...RECEIPT_ATTENTIONS].sort());
      for (const text of Object.values(copy)) expect(text).not.toContain("—");
    }
  });

  test("the preview retries an unknown outcome and enters an ambiguous receipt by hand", async () => {
    const source = createFixtureBusinessDataSource();
    const unknown = await source.receipt("rcpt-unknown");
    expect([unknown.attention, unknown.preparable, unknown.enterable]).toEqual(["outcome_unknown", true, true]);
    const queued = await source.prepareReceipt("rcpt-unknown");
    expect([queued.status, queued.preparable]).toEqual(["queued", false]);

    const ambiguous = await source.receipt("rcpt-ambiguous");
    expect([ambiguous.attention, ambiguous.preparable, ambiguous.enterable]).toEqual(["several_purchases", false, true]);
    const entered = await source.saveReview("rcpt-ambiguous", 0, { amount: "706.10" });
    expect([entered.status, entered.attention, entered.enterable, entered.evidence?.total]).toEqual([
      "review_ready",
      null,
      false,
      "706.10",
    ]);
  });
});
