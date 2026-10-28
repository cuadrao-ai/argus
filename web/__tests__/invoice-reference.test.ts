import { afterEach, expect, test } from "bun:test";
import type { TFunction } from "i18next";
import { invoiceReference } from "@/components/business-app/invoicing/invoice-reference";

const originalZone = process.env.TZ;
afterEach(() => { if (originalZone === undefined) delete process.env.TZ; else process.env.TZ = originalZone; });
const t = ((key: string, options?: { date?: string }) => options?.date ? `${key}|${options.date}` : key) as unknown as TFunction;
const draft = (created_at: string) => ({ operation: null, created_at });

test("a draft saved in the evening in Santo Domingo keeps that local calendar day", () => {
  process.env.TZ = "America/Santo_Domingo";
  expect(invoiceReference(draft("2026-10-28T01:30:00Z"), t, "en")).toBe("business.invoicing.draft_reference|Oct 27, 2026");
  expect(invoiceReference(draft("2026-10-28T03:59:00Z"), t, "en")).toBe("business.invoicing.draft_reference|Oct 27, 2026");
  expect(invoiceReference(draft("2026-10-28T04:00:00Z"), t, "en")).toBe("business.invoicing.draft_reference|Oct 28, 2026");
});
test("an issued invoice shows its number and an unreadable date shows the plain draft label", () => {
  expect(invoiceReference({ operation: { number: "E320000000001" } as never, created_at: "2026-10-28T01:30:00Z" }, t, "en")).toBe("E320000000001");
  expect(invoiceReference(draft("not a date"), t, "en")).toBe("business.invoicing.draft_reference_undated");
});
