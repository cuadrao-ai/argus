/**
 * Pure rules for typing and pasting a money amount (DESIGN.md §17, "Money entry
 * in the ecosystem sketch"). The canonical value matches the backend's
 * `parse_minor_units`: dot-decimal, no grouping, no rounding, fraction digits
 * from the currency.
 *
 * Three text forms:
 * - display: what the field shows, with grouping commas ("1,250.5").
 * - logical: the display without grouping commas ("1250.5"); may be partial
 *   while typing ("12.", "-", "000").
 * - canonical: the value a parent submits ("1250.5"), or null.
 */

/**
 * A length guard so the field cannot grow without bound. The backend owns the
 * largest amount it records and answers amount_out_of_range past it.
 */
export const MONEY_MAX_INTEGER_DIGITS = 15;

export type MoneyRules = {
  currency: string;
  /** Signed fields accept negatives and zero; positive-only fields accept neither. */
  allowNegative: boolean;
  /** The device locale writes decimals with a comma, so a typed comma is the decimal point. */
  commaDecimal: boolean;
};

export type MoneyProblem =
  | { code: "invalid" }
  | { code: "decimal_twice" }
  | { code: "negative" }
  | { code: "grouping" }
  | { code: "decimal_comma" }
  | { code: "precision"; currency: string; digits: number }
  | { code: "too_long"; digits: number }
  | { code: "out_of_range" }
  | { code: "currency_mismatch"; typed: string; field: string }
  | { code: "ambiguous_currency" }
  | { code: "zero" };

export type MoneyEditInput =
  | { type: "insert"; text: string }
  | { type: "delete"; direction: "backward" | "forward" };

export type MoneyEdit =
  | { kind: "accept"; display: string; caret: number; problem: MoneyProblem | null }
  | { kind: "ignore" }
  | { kind: "reject"; problem: MoneyProblem };

export type MoneyReading = { value: string | null; problem: MoneyProblem | null };

const DIGITS = "0123456789";
const isDigit = (char: string) => char.length === 1 && DIGITS.includes(char);

const SYMBOLS: Record<string, string> = { DOP: "RD$", USD: "US$" };

/**
 * Markers a pasted amount may start with. A bare "$" is not one: in the
 * Dominican Republic it usually means pesos, so it is refused as ambiguous.
 */
const MARKERS: { marker: string; currency: string }[] = [
  { marker: "RD$", currency: "DOP" },
  { marker: "US$", currency: "USD" },
  { marker: "€", currency: "EUR" },
];

export function currencyDigits(currency: string): number {
  if (!currency) return 2;
  try {
    return new Intl.NumberFormat("en", { style: "currency", currency }).resolvedOptions().maximumFractionDigits ?? 2;
  } catch {
    return 2;
  }
}

export function currencySymbol(currency: string): string {
  if (!currency) return "";
  if (SYMBOLS[currency]) return SYMBOLS[currency];
  try {
    const symbol = new Intl.NumberFormat("en", { style: "currency", currency, currencyDisplay: "symbol" })
      .formatToParts(0)
      .find((part) => part.type === "currency")?.value;
    return symbol && symbol !== currency ? symbol : currency;
  } catch {
    return currency;
  }
}

function isCurrencyCode(code: string): boolean {
  try {
    return Intl.supportedValuesOf("currency").includes(code);
  } catch {
    return code === "DOP" || code === "USD";
  }
}

export function localeUsesCommaDecimal(locale: string): boolean {
  try {
    return new Intl.NumberFormat(locale).formatToParts(1.1).find((part) => part.type === "decimal")?.value === ",";
  } catch {
    return false;
  }
}

export function moneyPlaceholder(currency: string): string {
  const digits = currencyDigits(currency);
  return digits > 0 ? `0.${"0".repeat(digits)}` : "0";
}

export function group(logical: string): string {
  const sign = logical.startsWith("-") ? "-" : "";
  const body = logical.slice(sign.length);
  const dot = body.indexOf(".");
  const whole = dot === -1 ? body : body.slice(0, dot);
  let grouped = "";
  for (let index = 0; index < whole.length; index += 1) {
    if (index > 0 && (whole.length - index) % 3 === 0) grouped += ",";
    grouped += whole[index];
  }
  return sign + grouped + (dot === -1 ? "" : body.slice(dot));
}

export function ungroup(display: string): string {
  return display.split(",").join("");
}

export function logicalIndex(display: string, index: number): number {
  return ungroup(display.slice(0, index)).length;
}

/** The display position right after the `logical`-th non-comma character, as iOS places the caret. */
export function displayIndex(display: string, logical: number): number {
  let location = 0;
  let count = 0;
  for (const char of display) {
    if (count >= logical) break;
    location += 1;
    if (char !== ",") count += 1;
  }
  return location;
}

function split(logical: string) {
  const negative = logical.startsWith("-");
  const body = negative ? logical.slice(1) : logical;
  const dot = body.indexOf(".");
  return {
    negative,
    whole: dot === -1 ? body : body.slice(0, dot),
    fraction: dot === -1 ? "" : body.slice(dot + 1),
    hasDot: dot !== -1,
  };
}

function limitProblem(logical: string, currency: string): MoneyProblem | null {
  const { whole, fraction, hasDot } = split(logical);
  const digits = currencyDigits(currency);
  if ((digits === 0 && hasDot) || fraction.length > digits) return { code: "precision", currency, digits };
  if (whole.replace(/^0+/, "").length > MONEY_MAX_INTEGER_DIGITS) {
    return { code: "too_long", digits: MONEY_MAX_INTEGER_DIGITS };
  }
  return null;
}

/** "." becomes "0." and, when asked, leading zeros collapse, moving the caret with the text. */
function normalize(logical: string, caret: number, collapseZeros: boolean): { logical: string; caret: number } {
  const start = logical.startsWith("-") ? 1 : 0;
  let text = logical;
  let position = caret;
  if (text[start] === ".") {
    text = `${text.slice(0, start)}0${text.slice(start)}`;
    if (position > start) position += 1;
  }
  if (collapseZeros) {
    while (text[start] === "0" && isDigit(text[start + 1] ?? "")) {
      text = text.slice(0, start) + text.slice(start + 1);
      if (position > start) position -= 1;
    }
  }
  return { logical: text, caret: position };
}

function canonical(logical: string): string | null {
  const { negative, whole, fraction, hasDot } = split(logical);
  if (!whole && !hasDot) return null;
  const trimmedWhole = whole.replace(/^0+(?=\d)/, "") || "0";
  const value = fraction ? `${trimmedWhole}.${fraction}` : trimmedWhole;
  const zero = !/[1-9]/.test(value);
  return negative && !zero ? `-${value}` : value;
}

export function readMoney(display: string, rules: MoneyRules): MoneyReading {
  const logical = ungroup(display);
  if (!logical) return { value: null, problem: null };
  const value = canonical(logical);
  if (value === null) return { value: null, problem: { code: "invalid" } };
  const problem = limitProblem(logical, rules.currency);
  if (problem) return { value: null, problem };
  if (!rules.allowNegative && !/[1-9]/.test(value)) return { value: null, problem: { code: "zero" } };
  return { value, problem: null };
}

/** The blur readback: grouped and padded to the currency's precision. Invalid text stays as typed. */
export function formatMoney(display: string, rules: MoneyRules): string {
  const reading = readMoney(display, rules);
  if (reading.value === null) return display;
  const { negative, whole, fraction } = split(reading.value);
  const digits = currencyDigits(rules.currency);
  const padded = digits > 0 ? `${whole}.${fraction.padEnd(digits, "0")}` : whole;
  return group(negative ? `-${padded}` : padded);
}

/** Parses a whole pasted, dropped or programmatic string. Never strips characters it does not understand. */
export function parsePasted(text: string, rules: MoneyRules): { logical: string } | { problem: MoneyProblem } {
  let rest = text.trim();
  const upper = rest.toUpperCase();
  const code = upper.slice(0, 3);
  const marker =
    MARKERS.find((item) => upper.startsWith(item.marker)) ??
    (/^[A-Z]{3}(?![A-Z])/.test(upper) && isCurrencyCode(code) ? { marker: code, currency: code } : null);
  if (!marker && upper.startsWith("$")) return { problem: { code: "ambiguous_currency" } };
  if (marker) {
    if (!rules.currency) return { problem: { code: "invalid" } };
    if (marker.currency !== rules.currency) {
      return { problem: { code: "currency_mismatch", typed: marker.currency, field: rules.currency } };
    }
    rest = rest.slice(marker.marker.length).trim();
  }
  let sign = "";
  if (rest.startsWith("-")) {
    if (!rules.allowNegative) return { problem: { code: "negative" } };
    sign = "-";
    rest = rest.slice(1);
  }
  for (const char of rest) {
    if (!isDigit(char) && char !== "," && char !== ".") return { problem: { code: "invalid" } };
  }
  const dots = rest.split(".").length - 1;
  if (dots > 1) return { problem: { code: "decimal_twice" } };
  const dot = rest.indexOf(".");
  const whole = dot === -1 ? rest : rest.slice(0, dot);
  const fraction = dot === -1 ? "" : rest.slice(dot + 1);
  if (fraction.includes(",")) return { problem: { code: "decimal_comma" } };
  if (whole.includes(",")) {
    const groups = whole.split(",");
    const tail = groups[groups.length - 1];
    if (groups.length === 2 && dot === -1 && tail.length >= 1 && tail.length <= 2) return { problem: { code: "decimal_comma" } };
    const wellFormed =
      groups[0].length >= 1 && groups[0].length <= 3 && groups.slice(1).every((part) => part.length === 3);
    if (!wellFormed) return { problem: { code: "grouping" } };
  }
  const logical = sign + ungroup(whole) + (dot === -1 ? "" : `.${fraction}`);
  if (!ungroup(whole) && !fraction) return { problem: { code: "invalid" } };
  const problem = limitProblem(logical, rules.currency);
  if (problem) return { problem };
  return { logical: normalize(logical, 0, true).logical };
}

/**
 * Applies one edit to the display at selection [start, end). A single typed
 * character follows the typing rules; anything longer is validated whole.
 */
export function editMoney(
  display: string,
  start: number,
  end: number,
  input: MoneyEditInput,
  rules: MoneyRules,
): MoneyEdit {
  const before = ungroup(display.slice(0, start));
  const after = ungroup(display.slice(end));

  if (input.type === "delete") {
    let from = start;
    let to = end;
    if (from === to) {
      if (input.direction === "backward") {
        if (from === 0) return { kind: "ignore" };
        from -= display[from - 1] === "," && from > 1 ? 2 : 1;
      } else {
        if (to >= display.length) return { kind: "ignore" };
        to += display[to] === "," ? 2 : 1;
      }
    }
    const kept = ungroup(display.slice(0, from));
    const next = normalize(kept + ungroup(display.slice(to)), kept.length, false);
    const problem = limitProblem(next.logical, rules.currency);
    if (problem?.code === "too_long") return { kind: "reject", problem };
    return accept(next.logical, next.caret, problem);
  }

  if (!input.text) return { kind: "ignore" };
  if (input.text.length > 1) {
    // On a comma-decimal device a typed "1,25" is 1.25, so a pasted "1,250"
    // cannot be read as grouping without contradicting typing.
    if (rules.commaDecimal && input.text.includes(",")) return { kind: "reject", problem: { code: "decimal_comma" } };
    const parsed = parsePasted(before + input.text + after, rules);
    if ("problem" in parsed) return { kind: "reject", problem: parsed.problem };
    return accept(parsed.logical, Math.max(0, parsed.logical.length - after.length), null);
  }

  let char = input.text;
  if (char === ",") {
    if (!rules.commaDecimal) return { kind: "ignore" };
    char = ".";
  }
  if (char === "-") {
    if (!rules.allowNegative) return { kind: "reject", problem: { code: "negative" } };
    if (before.length > 0 || after.startsWith("-")) return { kind: "reject", problem: { code: "invalid" } };
  } else if (char === ".") {
    if ((before + after).includes(".")) return { kind: "reject", problem: { code: "decimal_twice" } };
  } else if (!isDigit(char)) {
    return { kind: "reject", problem: { code: "invalid" } };
  }
  const next = normalize(before + char + after, before.length + 1, true);
  const problem = limitProblem(next.logical, rules.currency);
  if (problem) return { kind: "reject", problem };
  return accept(next.logical, next.caret, null);
}

function accept(logical: string, caret: number, problem: MoneyProblem | null): MoneyEdit {
  const display = group(logical);
  return { kind: "accept", display, caret: displayIndex(display, caret), problem };
}

/** The display for a canonical value a parent sets. */
export function displayForValue(value: string | null, rules: MoneyRules): string {
  if (!value) return "";
  const parsed = parsePasted(value, rules);
  return "logical" in parsed ? formatMoney(group(parsed.logical), rules) : value;
}

/**
 * A value set by the parent (a reload, a server correction) replaces the text,
 * unless the text already reads as that value, as our own emits do.
 */
export function textForParentValue(text: string, value: string | null, rules: MoneyRules): string | null {
  return value === readMoney(text, rules).value ? null : displayForValue(value, rules);
}

const FIELD_GROUPED = /^-?(0|[1-9]\d{0,2}(,\d{3})*)(\.\d*)?$/;
const TYPED_DECIMAL_COMMA = /^-?\d*,\d{0,2}$/;

/**
 * An edit the browser did not announce as cancellable (word deletion, undo, an
 * IME commit, autofill) arrives as the whole new value, read by one rule:
 * (a) no commas: plain digits and one optional point;
 * (b) grouped in the field's own format (first group nonzero): the commas are
 *     grouping. On a comma-decimal device a typed comma is the decimal point,
 *     so this holds only for an exact text the field itself already rendered
 *     (`shown`, as undo and redo restore); any other grouped-looking value
 *     there is refused as decimal_comma rather than guessed;
 * (c) on a comma-decimal device, one comma with no point and at most two
 *     digits after it is the decimal point, as when typed;
 * (d) anything else is refused with the paste rule's message for that shape.
 */
export function fallbackEdit(
  raw: string,
  caret: number,
  rules: MoneyRules,
  shown: readonly string[] = [],
): MoneyEdit {
  const text = raw.trim();
  if (!text) return { kind: "accept", display: "", caret: 0, problem: null };
  const grouped = FIELD_GROUPED.test(text);
  let logical: string;
  let logicalCaret: number;
  if (!text.includes(",") || (grouped && (!rules.commaDecimal || shown.includes(text)))) {
    logical = ungroup(raw);
    logicalCaret = logicalIndex(raw, caret);
  } else if (rules.commaDecimal && TYPED_DECIMAL_COMMA.test(text)) {
    logical = raw.replace(",", ".");
    logicalCaret = caret;
  } else if (rules.commaDecimal && grouped) {
    return { kind: "reject", problem: { code: "decimal_comma" } };
  } else {
    const refused = parsePasted(raw, rules);
    return { kind: "reject", problem: "problem" in refused ? refused.problem : { code: "grouping" } };
  }
  const parsed = parsePasted(logical, rules);
  if ("problem" in parsed) return { kind: "reject", problem: parsed.problem };
  const mapped = normalize(logical.trim(), logicalCaret - (logical.length - logical.trimStart().length), true);
  return accept(parsed.logical, mapped.logical === parsed.logical ? mapped.caret : parsed.logical.length, null);
}

export const RENDERED_HISTORY_LIMIT = 20;

/**
 * The texts the field has rendered, newest last, for `fallbackEdit`'s `shown`.
 * An empty field or a text the parent replaced starts the history over, so no
 * earlier rendering can vouch for a later value.
 */
export function nextRenderedHistory(history: readonly string[], text: string, parentReplaced: boolean): string[] {
  if (!text) return [];
  const kept = parentReplaced ? [] : history.filter((item) => item !== text);
  return [...kept, text].slice(-RENDERED_HISTORY_LIMIT);
}

/**
 * A currency change keeps the digits and revalidates them; nothing converts.
 * `note` says so whenever an amount was already there under another currency.
 */
export function currencyChange(
  text: string,
  previousCurrency: string,
  rules: MoneyRules,
): { value: string | null; invalid: boolean; problem: MoneyProblem | null; note: boolean } {
  const reading = readMoney(text, rules);
  return {
    value: reading.value,
    invalid: reading.problem !== null,
    problem: reading.problem?.code === "precision" ? reading.problem : null,
    note: Boolean(previousCurrency && rules.currency && ungroup(text).trim()),
  };
}

const SERVER_PROBLEMS: Record<string, (currency: string) => MoneyProblem> = {
  amount_invalid: () => ({ code: "invalid" }),
  amount_precision: (currency) => ({ code: "precision", currency, digits: currencyDigits(currency) }),
  amount_out_of_range: () => ({ code: "out_of_range" }),
};

export function moneyProblemFromServer(code: string | null | undefined, currency: string): MoneyProblem | null {
  return code && SERVER_PROBLEMS[code] ? SERVER_PROBLEMS[code](currency) : null;
}
