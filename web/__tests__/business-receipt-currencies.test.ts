import { describe, expect, test } from "bun:test";
import { receiptCurrencyOptions } from "@/components/business-app/receipt-currencies";
import type { BusinessAccount } from "@/lib/business-api";

const account = (currency: string): BusinessAccount => ({ id: `acct-${currency}`, nickname: null, type: "checking", currency });

describe("the currencies a receipt can be in", () => {
  test("offers the workspace currencies plus the receipt's own, once each", () => {
    expect(receiptCurrencyOptions({ currencies: ["DOP", "USD"] }, [account("DOP")], "EUR")).toEqual(["DOP", "USD", "EUR"]);
    expect(receiptCurrencyOptions({ currencies: ["DOP", "USD"] }, [account("DOP")], "USD")).toEqual(["DOP", "USD"]);
  });

  test("ignores the accounts once the workspace has said which currencies it works in", () => {
    expect(receiptCurrencyOptions({ currencies: ["DOP"] }, [account("USD")], null)).toEqual(["DOP"]);
  });

  test("falls back to the record's accounts while the workspace has not loaded", () => {
    expect(receiptCurrencyOptions(null, [account("DOP"), account("USD"), account("DOP")], null)).toEqual(["DOP", "USD"]);
  });

  test("a receipt with no known currency adds nothing", () => {
    expect(receiptCurrencyOptions({ currencies: ["DOP"] }, [], null)).toEqual(["DOP"]);
    expect(receiptCurrencyOptions({ currencies: ["DOP"] }, [], "")).toEqual(["DOP"]);
  });
});
