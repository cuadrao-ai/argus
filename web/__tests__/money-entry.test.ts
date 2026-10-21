import { describe, expect, test } from "bun:test";
import {
  currencyChange,
  currencyDigits,
  currencySymbol,
  displayIndex,
  editMoney,
  fallbackEdit,
  formatMoney,
  group,
  localeUsesCommaDecimal,
  logicalIndex,
  moneyPlaceholder,
  moneyProblemFromServer,
  nextRenderedHistory,
  parsePasted,
  readMoney,
  textForParentValue,
  type MoneyRules,
} from "../lib/money-entry";

const DOP: MoneyRules = { currency: "DOP", allowNegative: false, commaDecimal: false };
const USD: MoneyRules = { ...DOP, currency: "USD" };
const JPY: MoneyRules = { ...DOP, currency: "JPY" };
const COMMA_DEVICE: MoneyRules = { ...DOP, commaDecimal: true };
const SIGNED: MoneyRules = { ...DOP, allowNegative: true };

/** Types each character at the caret, as a keyboard would, and reports what the field shows. */
function typeKeys(keys: string, rules: MoneyRules, start = "") {
  let display = start;
  let caret = start.length;
  let problem: string | null = null;
  for (const key of keys) {
    const edit = editMoney(display, caret, caret, { type: "insert", text: key }, rules);
    if (edit.kind === "accept") {
      display = edit.display;
      caret = edit.caret;
      problem = edit.problem?.code ?? null;
    } else if (edit.kind === "reject") {
      problem = edit.problem.code;
    }
  }
  return { display, caret, problem };
}

describe("currency facts", () => {
  test("precision comes from the currency", () => {
    expect(currencyDigits("DOP")).toBe(2);
    expect(currencyDigits("USD")).toBe(2);
    expect(currencyDigits("JPY")).toBe(0);
    expect(currencyDigits("")).toBe(2);
  });

  test("the prefix names DOP and USD unambiguously", () => {
    expect(currencySymbol("DOP")).toBe("RD$");
    expect(currencySymbol("USD")).toBe("US$");
    expect(currencySymbol("EUR")).toBe("€");
    expect(currencySymbol("")).toBe("");
  });

  test("the placeholder shows the currency's precision", () => {
    expect(moneyPlaceholder("DOP")).toBe("0.00");
    expect(moneyPlaceholder("JPY")).toBe("0");
  });

  test("a comma-decimal device is read from Intl, not guessed", () => {
    expect(localeUsesCommaDecimal("de-DE")).toBe(true);
    expect(localeUsesCommaDecimal("es-ES")).toBe(true);
    expect(localeUsesCommaDecimal("en-US")).toBe(false);
    expect(localeUsesCommaDecimal("es-DO")).toBe(false);
  });
});

describe("grouping and caret mapping", () => {
  test("group inserts commas and keeps the sign and a trailing dot", () => {
    expect(group("1250")).toBe("1,250");
    expect(group("1250000.5")).toBe("1,250,000.5");
    expect(group("12.")).toBe("12.");
    expect(group("-1250")).toBe("-1,250");
    expect(group("")).toBe("");
  });

  test("logical and display indexes skip grouping commas", () => {
    expect(logicalIndex("1,250,000", 6)).toBe(4);
    expect(displayIndex("1,250,000", 4)).toBe(5);
    expect(displayIndex("1,250,000", 1)).toBe(1);
    expect(displayIndex("1,250,000", 0)).toBe(0);
    expect(displayIndex("1,250,000", 7)).toBe(9);
  });
});

describe("typing", () => {
  test("digits group live", () => {
    expect(typeKeys("1250", DOP)).toEqual({ display: "1,250", caret: 5, problem: null });
    expect(typeKeys("1250000.5", DOP)).toEqual({ display: "1,250,000.5", caret: 11, problem: null });
  });

  test("letters, symbols, exponent and plus are refused and leave the text", () => {
    expect(typeKeys("wfrwedfw", DOP)).toEqual({ display: "", caret: 0, problem: "invalid" });
    expect(typeKeys("12e", DOP)).toEqual({ display: "12", caret: 2, problem: "invalid" });
    expect(typeKeys("12E", DOP)).toEqual({ display: "12", caret: 2, problem: "invalid" });
    expect(typeKeys("+", DOP)).toEqual({ display: "", caret: 0, problem: "invalid" });
    expect(typeKeys("$", DOP)).toEqual({ display: "", caret: 0, problem: "invalid" });
  });

  test("the iOS reproduction keeps only the digits that fit", () => {
    expect(typeKeys("wfrwedfw3e12w", DOP)).toEqual({ display: "312", caret: 3, problem: "invalid" });
  });

  test("the next valid keystroke clears the message", () => {
    expect(typeKeys("1a2", DOP)).toEqual({ display: "12", caret: 2, problem: null });
  });

  test("a second decimal point is refused", () => {
    expect(typeKeys("1.2.", DOP)).toEqual({ display: "1.2", caret: 3, problem: "decimal_twice" });
  });

  test("a typed grouping comma is ignored on a dot-decimal device", () => {
    expect(typeKeys("1,250", DOP)).toEqual({ display: "1,250", caret: 5, problem: null });
    expect(typeKeys("12,50", DOP)).toEqual({ display: "1,250", caret: 5, problem: null });
  });

  test("on a comma-decimal device a typed comma is the decimal point", () => {
    expect(typeKeys("12,50", COMMA_DEVICE)).toEqual({ display: "12.50", caret: 5, problem: null });
    expect(typeKeys("12,5,", COMMA_DEVICE)).toEqual({ display: "12.5", caret: 4, problem: "decimal_twice" });
    expect(typeKeys("1,250", COMMA_DEVICE)).toEqual({ display: "1.25", caret: 4, problem: "precision" });
  });

  test("minus is refused on a positive-only field and allowed once at the start when signed", () => {
    expect(typeKeys("-5", DOP)).toEqual({ display: "5", caret: 1, problem: null });
    expect(typeKeys("-", DOP).problem).toBe("negative");
    expect(typeKeys("-1250", SIGNED)).toEqual({ display: "-1,250", caret: 6, problem: null });
    expect(typeKeys("5-", SIGNED)).toEqual({ display: "5", caret: 1, problem: "invalid" });
  });

  test("precision follows the currency", () => {
    expect(typeKeys("12.505", DOP)).toEqual({ display: "12.50", caret: 5, problem: "precision" });
    expect(typeKeys("12.5", JPY)).toEqual({ display: "125", caret: 3, problem: null });
    expect(typeKeys(".", JPY)).toEqual({ display: "", caret: 0, problem: "precision" });
  });

  test("no UI maximum; only a 15-digit length guard before the point", () => {
    expect(typeKeys("10000000.99", DOP)).toEqual({ display: "10,000,000.99", caret: 13, problem: null });
    expect(typeKeys("1234567890123456", DOP)).toEqual({
      display: "123,456,789,012,345",
      caret: 19,
      problem: "too_long",
    });
  });

  test('"." becomes "0." and leading zeros collapse while typing', () => {
    expect(typeKeys(".5", DOP)).toEqual({ display: "0.5", caret: 3, problem: null });
    expect(typeKeys("007", DOP)).toEqual({ display: "7", caret: 1, problem: null });
    expect(typeKeys("0.05", DOP)).toEqual({ display: "0.05", caret: 4, problem: null });
    expect(typeKeys("-.5", SIGNED)).toEqual({ display: "-0.5", caret: 4, problem: null });
  });

  test("a digit typed mid-number keeps the caret after it across a new comma", () => {
    const edit = editMoney("1,250", 4, 4, { type: "insert", text: "9" }, DOP);
    expect(edit).toEqual({ kind: "accept", display: "12,590", caret: 5, problem: null });
  });

  test("a digit typed at the start shifts the grouping", () => {
    const edit = editMoney("250", 0, 0, { type: "insert", text: "1" }, DOP);
    expect(edit).toEqual({ kind: "accept", display: "1,250", caret: 1, problem: null });
  });

  test("typing over a selection replaces it", () => {
    const edit = editMoney("3,450.00", 0, 8, { type: "insert", text: "7" }, DOP);
    expect(edit).toEqual({ kind: "accept", display: "7", caret: 1, problem: null });
  });
});

describe("deleting", () => {
  test("backspace after a comma removes the digit before it", () => {
    expect(editMoney("1,250", 2, 2, { type: "delete", direction: "backward" }, DOP)).toEqual({
      kind: "accept",
      display: "250",
      caret: 0,
      problem: null,
    });
  });

  test("forward delete before a comma removes the digit after it", () => {
    expect(editMoney("1,250", 1, 1, { type: "delete", direction: "forward" }, DOP)).toEqual({
      kind: "accept",
      display: "150",
      caret: 1,
      problem: null,
    });
  });

  test("deleting the leading digit keeps the zeros the user typed", () => {
    expect(editMoney("1,000", 1, 1, { type: "delete", direction: "backward" }, DOP)).toEqual({
      kind: "accept",
      display: "000",
      caret: 0,
      problem: null,
    });
  });

  test("deleting the decimal point cannot push past the length guard", () => {
    expect(editMoney("999,999,999,999,999.99", 20, 20, { type: "delete", direction: "backward" }, DOP)).toEqual({
      kind: "reject",
      problem: { code: "too_long", digits: 15 },
    });
  });

  test("deleting toward a valid precision stays allowed and keeps the message until it fits", () => {
    expect(editMoney("12.50", 5, 5, { type: "delete", direction: "backward" }, JPY)).toEqual({
      kind: "accept",
      display: "12.5",
      caret: 4,
      problem: { code: "precision", currency: "JPY", digits: 0 },
    });
    expect(editMoney("12.", 3, 3, { type: "delete", direction: "backward" }, JPY)).toEqual({
      kind: "accept",
      display: "12",
      caret: 2,
      problem: null,
    });
  });

  test("backspace at the start does nothing", () => {
    expect(editMoney("12", 0, 0, { type: "delete", direction: "backward" }, DOP)).toEqual({ kind: "ignore" });
  });
});

describe("paste and drop", () => {
  const paste = (text: string, rules: MoneyRules = DOP, display = "") =>
    editMoney(display, 0, display.length, { type: "insert", text }, rules);

  test("grouped and plain amounts are accepted", () => {
    expect(paste("1,250.50")).toEqual({ kind: "accept", display: "1,250.50", caret: 8, problem: null });
    expect(paste("1250.5")).toEqual({ kind: "accept", display: "1,250.5", caret: 7, problem: null });
    expect(paste("1,250")).toEqual({ kind: "accept", display: "1,250", caret: 5, problem: null });
  });

  test("surrounding whitespace is trimmed", () => {
    expect(paste("  1250.5 \n")).toEqual({ kind: "accept", display: "1,250.5", caret: 7, problem: null });
  });

  test("a leading marker that matches the field's currency is accepted", () => {
    expect(paste("RD$1,250.50")).toEqual({ kind: "accept", display: "1,250.50", caret: 8, problem: null });
    expect(paste("DOP 1,250.50")).toEqual({ kind: "accept", display: "1,250.50", caret: 8, problem: null });
    expect(paste("US$ 12.50", USD)).toEqual({ kind: "accept", display: "12.50", caret: 5, problem: null });
    expect(paste("USD12.50", USD)).toEqual({ kind: "accept", display: "12.50", caret: 5, problem: null });
  });

  test("a bare $ is ambiguous between RD$ and US$ in any field", () => {
    expect(paste("$12.50")).toEqual({ kind: "reject", problem: { code: "ambiguous_currency" } });
    expect(paste("$12.50", USD)).toEqual({ kind: "reject", problem: { code: "ambiguous_currency" } });
    expect(paste("$ 1,250")).toEqual({ kind: "reject", problem: { code: "ambiguous_currency" } });
  });

  test("a mismatched marker names both currencies", () => {
    expect(paste("US$12.50")).toEqual({
      kind: "reject",
      problem: { code: "currency_mismatch", typed: "USD", field: "DOP" },
    });
    expect(paste("RD$12.50", USD)).toEqual({
      kind: "reject",
      problem: { code: "currency_mismatch", typed: "DOP", field: "USD" },
    });
    expect(paste("EUR 12.50")).toEqual({
      kind: "reject",
      problem: { code: "currency_mismatch", typed: "EUR", field: "DOP" },
    });
  });

  test("malformed grouping is refused", () => {
    expect(paste("1,25,0")).toEqual({ kind: "reject", problem: { code: "grouping" } });
    expect(paste("12,5000")).toEqual({ kind: "reject", problem: { code: "grouping" } });
    expect(paste("1234,567")).toEqual({ kind: "reject", problem: { code: "grouping" } });
  });

  test("a decimal comma is refused, not guessed", () => {
    expect(paste("1.250,50")).toEqual({ kind: "reject", problem: { code: "decimal_comma" } });
    expect(paste("12,50")).toEqual({ kind: "reject", problem: { code: "decimal_comma" } });
    expect(paste("12,50", COMMA_DEVICE)).toEqual({ kind: "reject", problem: { code: "decimal_comma" } });
  });

  test("a comma-decimal device refuses any pasted comma, since typing it means decimals", () => {
    expect(paste("1,250", COMMA_DEVICE)).toEqual({ kind: "reject", problem: { code: "decimal_comma" } });
    expect(paste("1,250.50", COMMA_DEVICE)).toEqual({ kind: "reject", problem: { code: "decimal_comma" } });
    expect(paste("1250.50", COMMA_DEVICE)).toEqual({ kind: "accept", display: "1,250.50", caret: 8, problem: null });
    expect(typeKeys("1,25", COMMA_DEVICE)).toEqual({ display: "1.25", caret: 4, problem: null });
  });

  test("excess precision is refused, never rounded", () => {
    expect(paste("1.250")).toEqual({
      kind: "reject",
      problem: { code: "precision", currency: "DOP", digits: 2 },
    });
    expect(paste("1250.5", JPY)).toEqual({
      kind: "reject",
      problem: { code: "precision", currency: "JPY", digits: 0 },
    });
    expect(paste("1.250", { ...DOP, currency: "KWD" })).toEqual({ kind: "accept", display: "1.250", caret: 5, problem: null });
  });

  test("exponent notation, letters, a sign and a second point are refused", () => {
    expect(paste("1e5")).toEqual({ kind: "reject", problem: { code: "invalid" } });
    expect(paste("1.2E3")).toEqual({ kind: "reject", problem: { code: "invalid" } });
    expect(paste("wfrwedfw3e12w")).toEqual({ kind: "reject", problem: { code: "invalid" } });
    expect(paste("abc12")).toEqual({ kind: "reject", problem: { code: "invalid" } });
    expect(paste("12 50")).toEqual({ kind: "reject", problem: { code: "invalid" } });
    expect(paste("+12")).toEqual({ kind: "reject", problem: { code: "invalid" } });
    expect(paste("-12")).toEqual({ kind: "reject", problem: { code: "negative" } });
    expect(paste("1.2.3")).toEqual({ kind: "reject", problem: { code: "decimal_twice" } });
    expect(paste(" . ")).toEqual({ kind: "reject", problem: { code: "invalid" } });
  });

  test("a signed field accepts a pasted negative", () => {
    expect(paste("-1,250.50", SIGNED)).toEqual({ kind: "accept", display: "-1,250.50", caret: 9, problem: null });
  });

  test("a large amount is the backend's to judge; only the length guard applies", () => {
    expect(paste("10,000,000")).toEqual({ kind: "accept", display: "10,000,000", caret: 10, problem: null });
    expect(paste("1234567890123456")).toEqual({ kind: "reject", problem: { code: "too_long", digits: 15 } });
  });

  test("leading zeros and a bare point normalize", () => {
    expect(paste("007.5")).toEqual({ kind: "accept", display: "7.5", caret: 3, problem: null });
    expect(paste(".5")).toEqual({ kind: "accept", display: "0.5", caret: 3, problem: null });
  });

  test("a paste mid-number is validated with the text around it and leaves the caret after it", () => {
    expect(editMoney("1,250", 1, 1, { type: "insert", text: "00" }, DOP)).toEqual({
      kind: "accept",
      display: "100,250",
      caret: 3,
      problem: null,
    });
    expect(editMoney("1,250", 5, 5, { type: "insert", text: "RD$5" }, DOP)).toEqual({
      kind: "reject",
      problem: { code: "invalid" },
    });
  });

  test("parsePasted returns the logical text", () => {
    expect(parsePasted("RD$ 1,250.50", DOP)).toEqual({ logical: "1250.50" });
  });
});

describe("reading the value", () => {
  test("the value is canonical dot-decimal without grouping", () => {
    expect(readMoney("1,250.5", DOP)).toEqual({ value: "1250.5", problem: null });
    expect(readMoney("1,250.", DOP)).toEqual({ value: "1250", problem: null });
    expect(readMoney("000", SIGNED)).toEqual({ value: "0", problem: null });
    expect(readMoney("-1,250.50", SIGNED)).toEqual({ value: "-1250.50", problem: null });
  });

  test("empty means unknown, never zero", () => {
    expect(readMoney("", DOP)).toEqual({ value: null, problem: null });
  });

  test("zero is invalid for a positive-only amount", () => {
    expect(readMoney("0", DOP)).toEqual({ value: null, problem: { code: "zero" } });
    expect(readMoney("0.00", DOP)).toEqual({ value: null, problem: { code: "zero" } });
  });

  test("a lone minus is incomplete", () => {
    expect(readMoney("-", SIGNED)).toEqual({ value: null, problem: { code: "invalid" } });
  });

  test("a currency change revalidates the same digits without conversion", () => {
    expect(readMoney("12.50", DOP)).toEqual({ value: "12.50", problem: null });
    expect(readMoney("12.50", JPY)).toEqual({
      value: null,
      problem: { code: "precision", currency: "JPY", digits: 0 },
    });
    expect(readMoney("1,250", JPY)).toEqual({ value: "1250", problem: null });
  });
});

describe("blur readback", () => {
  test("groups and pads to the currency's precision", () => {
    expect(formatMoney("1250.5", DOP)).toBe("1,250.50");
    expect(formatMoney("1,250.", DOP)).toBe("1,250.00");
    expect(formatMoney("0.5", USD)).toBe("0.50");
    expect(formatMoney("1,250", JPY)).toBe("1,250");
    expect(formatMoney("000", SIGNED)).toBe("0.00");
    expect(formatMoney("-12.5", SIGNED)).toBe("-12.50");
  });

  test("empty and invalid text stay as typed", () => {
    expect(formatMoney("", DOP)).toBe("");
    expect(formatMoney("0", DOP)).toBe("0");
    expect(formatMoney("12.50", JPY)).toBe("12.50");
  });
});

describe("backend errors", () => {
  test("map to the same inline problems", () => {
    expect(moneyProblemFromServer("amount_invalid", "DOP")).toEqual({ code: "invalid" });
    expect(moneyProblemFromServer("amount_precision", "DOP")).toEqual({ code: "precision", currency: "DOP", digits: 2 });
    expect(moneyProblemFromServer("amount_out_of_range", "JPY")).toEqual({ code: "out_of_range" });
    expect(moneyProblemFromServer("stale_version", "DOP")).toBe(null);
  });
});

describe("MoneyInput decisions", () => {
  test("a parent value the text does not read as replaces the text", () => {
    expect(textForParentValue("1,250.50", "980.5", DOP)).toBe("980.50");
    expect(textForParentValue("1,250.50", null, DOP)).toBe("");
    expect(textForParentValue("", "3450.00", DOP)).toBe("3,450.00");
  });

  test("an echo of the field's own value keeps the text as typed", () => {
    expect(textForParentValue("1,250.5", "1250.5", DOP)).toBe(null);
    expect(textForParentValue("", null, DOP)).toBe(null);
  });

  test("a currency change revalidates the same digits and notes no conversion", () => {
    expect(currencyChange("1,250.50", "DOP", USD)).toEqual({ value: "1250.50", invalid: false, problem: null, note: true });
    expect(currencyChange("1,250.50", "DOP", JPY)).toEqual({
      value: null,
      invalid: true,
      problem: { code: "precision", currency: "JPY", digits: 0 },
      note: true,
    });
    expect(currencyChange("", "DOP", USD).note).toBe(false);
    expect(currencyChange("12", "", DOP).note).toBe(false);
  });

  test("the onChange fallback reads the whole new value", () => {
    // A non-cancellable insert of "0" after "1,250" arrives as "1,2500".
    expect(fallbackEdit("1,2500", 6, DOP)).toEqual({ kind: "reject", problem: { code: "grouping" } });
    expect(fallbackEdit("12500", 5, DOP)).toEqual({ kind: "accept", display: "12,500", caret: 6, problem: null });
    expect(fallbackEdit("1,250.", 6, DOP)).toEqual({ kind: "accept", display: "1,250.", caret: 6, problem: null });
    expect(fallbackEdit("", 0, DOP)).toEqual({ kind: "accept", display: "", caret: 0, problem: null });
    expect(fallbackEdit("1,25x", 5, DOP)).toEqual({ kind: "reject", problem: { code: "invalid" } });
    expect(fallbackEdit("1,250.505", 9, DOP)).toEqual({
      kind: "reject",
      problem: { code: "precision", currency: "DOP", digits: 2 },
    });
  });

  test("a value grouped in the field's own format is accepted whole", () => {
    // Undo from "234,567", autofill over "1,234", an edit of "250,000".
    expect(fallbackEdit("1,234,567", 9, DOP)).toEqual({ kind: "accept", display: "1,234,567", caret: 9, problem: null });
    expect(fallbackEdit("1,500,000", 9, DOP)).toEqual({ kind: "accept", display: "1,500,000", caret: 9, problem: null });
    expect(fallbackEdit("1,250,000", 1, DOP)).toEqual({ kind: "accept", display: "1,250,000", caret: 1, problem: null });
  });

  test("a comma that is neither grouping nor a typed decimal is refused", () => {
    // A comma inserted mid-number: "1,250" becomes "1,2,550".
    expect(fallbackEdit("1,2,550", 3, DOP)).toEqual({ kind: "reject", problem: { code: "grouping" } });
    expect(fallbackEdit("12,5", 4, DOP)).toEqual({ kind: "reject", problem: { code: "decimal_comma" } });
    expect(fallbackEdit("1,2,3,4", 7, DOP)).toEqual({ kind: "reject", problem: { code: "grouping" } });
    expect(fallbackEdit("1,2,3,4", 7, COMMA_DEVICE)).toEqual({ kind: "reject", problem: { code: "grouping" } });
  });

  test("on a comma-decimal device one comma with up to two digits after it is the decimal point", () => {
    expect(fallbackEdit("1,5", 3, COMMA_DEVICE)).toEqual({ kind: "accept", display: "1.5", caret: 3, problem: null });
    expect(fallbackEdit("12,", 3, COMMA_DEVICE)).toEqual({ kind: "accept", display: "12.", caret: 3, problem: null });
  });

  test("on a comma-decimal device a grouped value is grouping only when the field rendered it", () => {
    // Undo back to the field's previous "1,234".
    expect(fallbackEdit("1,234", 5, COMMA_DEVICE, ["1,234", "12,345"])).toEqual({
      kind: "accept",
      display: "1,234",
      caret: 5,
      problem: null,
    });
    // Autofill of a "1,234" the field never showed is not guessed.
    expect(fallbackEdit("1,234", 5, COMMA_DEVICE, ["12,345"])).toEqual({ kind: "reject", problem: { code: "decimal_comma" } });
    expect(fallbackEdit("123,456", 7, COMMA_DEVICE)).toEqual({ kind: "reject", problem: { code: "decimal_comma" } });
    // A dot device keeps reading its own grouping without history.
    expect(fallbackEdit("123,456", 7, DOP)).toEqual({ kind: "accept", display: "123,456", caret: 7, problem: null });
  });

  test("a leading-zero group is never the field's grouping", () => {
    expect(fallbackEdit("01,234", 6, DOP)).toEqual({ kind: "reject", problem: { code: "grouping" } });
    expect(fallbackEdit("01,234", 6, COMMA_DEVICE, ["01,234"])).toEqual({ kind: "reject", problem: { code: "grouping" } });
    expect(fallbackEdit("0.5", 3, DOP)).toEqual({ kind: "accept", display: "0.5", caret: 3, problem: null });
  });

  test("the fallback caret follows normalization", () => {
    expect(fallbackEdit(".5", 1, DOP)).toEqual({ kind: "accept", display: "0.5", caret: 2, problem: null });
    expect(fallbackEdit("007", 3, DOP)).toEqual({ kind: "accept", display: "7", caret: 1, problem: null });
  });
});

describe("rendered history", () => {
  test("keeps the newest 20 renderings", () => {
    let history: string[] = [];
    for (let index = 1; index <= 25; index += 1) history = nextRenderedHistory(history, String(index), false);
    expect(history).toEqual(Array.from({ length: 20 }, (_, index) => String(index + 6)));
  });

  test("a repeated rendering moves to the end once", () => {
    expect(nextRenderedHistory(["1", "1,234", "12"], "1,234", false)).toEqual(["1", "12", "1,234"]);
  });

  test("an empty field clears the history", () => {
    expect(nextRenderedHistory(["1", "1,234"], "", false)).toEqual([]);
  });

  test("a parent replacement starts over with the new text", () => {
    expect(nextRenderedHistory(["1", "1,234"], "980.50", true)).toEqual(["980.50"]);
    expect(nextRenderedHistory(["1", "1,234"], "", true)).toEqual([]);
  });
});
