import { describe, expect, test } from "bun:test";
import { formatMoney } from "../components/business-app/business-format";

describe("Business saved amount readback", () => {
  test("reads the decimal string back exactly in the currency's precision", () => {
    expect(formatMoney("1.255", "KWD", "en")).toBe("KWD 1.255");
    expect(formatMoney("1250", "JPY", "en")).toBe("¥ 1,250");
    expect(formatMoney("3450", "DOP", "en")).toBe("RD$ 3,450.00");
    expect(formatMoney("24.5", "USD", "en")).toBe("US$ 24.50");
  });

  test("never rounds through a float", () => {
    expect(formatMoney("90071992547409.93", "USD", "en")).toBe("US$ 90,071,992,547,409.93");
    expect(formatMoney("0.105", "DOP", "en")).toBe("RD$ 0.105");
  });

  test("uses the reader's separators", () => {
    expect(formatMoney("1250.5", "DOP", "de-DE")).toBe("RD$ 1.250,50");
  });

  test("text that is not a decimal amount is shown as given", () => {
    expect(formatMoney("abc", "DOP", "en")).toBe("DOP abc");
    expect(formatMoney(null, "DOP", "en")).toBe("");
  });
});
