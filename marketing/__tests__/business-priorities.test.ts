import { describe, expect, test } from "bun:test";
import { sampleInvoiceStory } from "../components/sample-data";
import { priorityAmount, priorityName, sampleExpenseStory, samplePriorities } from "../components/sample-priorities";

describe("illustrative business priorities", () => {
  test("connects collections to the same invoice shown in the replay", () => {
    const collection = samplePriorities.find((priority) => priority.kind === "collection");
    if (!collection || collection.kind !== "collection") throw new Error("Missing collection example");
    expect(collection.story).toBe(sampleInvoiceStory);
    expect(priorityAmount(collection)).toBe(sampleInvoiceStory.invoice.amount - sampleInvoiceStory.payment);
    expect(priorityName(collection, "es")).toBe(sampleInvoiceStory.customerName);
  });

  test("keeps payable and document priorities distinct from receivables", () => {
    expect(samplePriorities.map((priority) => priority.kind)).toEqual(["collection", "payable", "document"]);
    expect(new Set(samplePriorities.map((priority) => priority.id)).size).toBe(samplePriorities.length);
    for (const priority of samplePriorities) {
      expect(priorityAmount(priority)).toBeGreaterThan(0);
      if (priority.kind !== "collection") expect(priorityAmount(priority)).toBe(priority.amount);
    }
  });

  test("attaches the receipt to the existing expense instead of creating a second expense", () => {
    const expense = samplePriorities.find((priority) => priority.id === sampleExpenseStory.expense.id);
    expect(expense).toBe(sampleExpenseStory.expense);
    expect(samplePriorities.filter((priority) => priority.kind === "document")).toHaveLength(1);
    expect(priorityAmount(sampleExpenseStory.expense)).toBe(2800);
  });

  test.each(["es", "en"] as const)("has a display name for every %s priority", (locale) => {
    for (const priority of samplePriorities) expect(priorityName(priority, locale).length).toBeGreaterThan(0);
  });
});
