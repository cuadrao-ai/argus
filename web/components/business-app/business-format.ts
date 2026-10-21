import { currencyDigits, currencySymbol } from "@/lib/money-entry";

const DECIMAL_AMOUNT = /^(-?)(\d+)(?:\.(\d+))?$/;

export function formatBusinessName(name: string | null | undefined, fallback: string): string {
  return !name?.trim() || name === "My business" ? fallback : name;
}

function separators(locale: string): { group: string; decimal: string } {
  try {
    const parts = new Intl.NumberFormat(locale).formatToParts(11111.1);
    return {
      group: parts.find((part) => part.type === "group")?.value ?? ",",
      decimal: parts.find((part) => part.type === "decimal")?.value ?? ".",
    };
  } catch {
    return { group: ",", decimal: "." };
  }
}

function groupDigits(whole: string, group: string): string {
  let grouped = "";
  for (let index = 0; index < whole.length; index += 1) {
    if (index > 0 && (whole.length - index) % 3 === 0) grouped += group;
    grouped += whole[index];
  }
  return grouped;
}

/**
 * The number alone, for a row under a header that already names the currency:
 * padded to the currency's digits and never rounded or passed through a float.
 */
export function formatAmount(amount: string | null, currency: string | null, locale: string): string {
  if (amount === null || currency === null) return "";
  const match = DECIMAL_AMOUNT.exec(amount.trim());
  if (!match) return amount;
  const [, sign, whole, fraction = ""] = match;
  const { group, decimal } = separators(locale);
  const digits = Math.max(currencyDigits(currency), fraction.length);
  const grouped = groupDigits(whole, group);
  return `${sign}${digits > 0 ? `${grouped}${decimal}${fraction.padEnd(digits, "0")}` : grouped}`;
}

/** The saved amount with its currency symbol, which names which dollar it is. */
export function formatMoney(
  amount: string | null,
  currency: string | null,
  locale: string,
): string {
  if (amount === null || currency === null) return "";
  const match = DECIMAL_AMOUNT.exec(amount.trim());
  if (!match) return `${currency} ${amount}`;
  const number = formatAmount(amount, currency, locale);
  const negative = number.startsWith("-");
  return `${negative ? "-" : ""}${currencySymbol(currency)} ${negative ? number.slice(1) : number}`;
}

/** Headline figures shorten from here up; anything smaller reads exactly. */
export const HEADLINE_COMPACT_FROM = BigInt(10_000);

/**
 * Spanish readers say "58.4 mil" and "1.3 M"; `Intl` gives es-419 an English "k".
 * Largest unit first. Billions stay in millions in Spanish, as people say them.
 */
const COMPACT_UNITS: Record<"es" | "en", { size: bigint; label: string; space: boolean }[]> = {
  es: [
    { size: BigInt(1_000_000), label: "M", space: true },
    { size: BigInt(1_000), label: "mil", space: true },
  ],
  en: [
    { size: BigInt(1_000_000_000), label: "B", space: false },
    { size: BigInt(1_000_000), label: "M", space: false },
    { size: BigInt(1_000), label: "K", space: false },
  ],
};

/**
 * A big summary figure: one decimal and a unit from 10,000 up ("RD$ 58.4 mil"),
 * the exact amount below it. Rounds half up from the decimal text, never a float.
 * `row` holds every figure shown beside this one: the largest picks the unit for
 * all of them, so a row never mixes "58.4 mil" with "9,600.00".
 * `exact` is what the tooltip and the accessible name read.
 */
export function formatHeadlineMoney(amount: string, currency: string, locale: string, row: readonly string[] = [amount]): { short: string; exact: string } {
  const exact = formatMoney(amount, currency, locale);
  const match = DECIMAL_AMOUNT.exec(amount.trim());
  const parsed = row.map((value) => DECIMAL_AMOUNT.exec(value.trim())).filter((found) => found !== null);
  if (!match || parsed.length === 0) return { short: exact, exact };
  const largest = parsed.reduce((top, found) => (BigInt(found[2]) > BigInt(top[2]) ? found : top));
  if (BigInt(largest[2]) < HEADLINE_COMPACT_FROM) return { short: exact, exact };
  const units = COMPACT_UNITS[locale.toLowerCase().startsWith("es") ? "es" : "en"];
  const ten = BigInt(10);
  const tenthsIn = ([, , whole, fraction = ""]: RegExpExecArray, size: bigint) => {
    const scaled = BigInt(`${whole}${fraction}`);
    const scale = ten ** BigInt(fraction.length);
    return (scaled * ten * BigInt(2) + size * scale) / (size * scale * BigInt(2));
  };
  let index = units.findIndex((unit) => BigInt(largest[2]) >= unit.size);
  // 999,960 rounds to "1,000.0 mil"; the next unit up says it as "1 M".
  if (index > 0 && tenthsIn(largest, units[index].size) >= BigInt(10_000)) index -= 1;
  const unit = units[index];
  const tenths = tenthsIn(match, unit.size);
  const { group, decimal } = separators(locale);
  const tenth = tenths % ten;
  const number = `${groupDigits((tenths / ten).toString(), group)}${tenth === BigInt(0) ? "" : `${decimal}${tenth}`}`;
  if (tenths === BigInt(0)) return { short: `${currencySymbol(currency)} 0`, exact };
  return { short: `${match[1]}${currencySymbol(currency)} ${number}${unit.space ? " " : ""}${unit.label}`, exact };
}

export function formatDay(day: string | null, locale: string): string {
  if (!day) return "";
  const date = new Date(`${day.slice(0, 10)}T12:00:00`);
  if (Number.isNaN(date.getTime())) return day;
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric" }).format(date);
}

export function formatTimestamp(iso: string, locale: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" }).format(date);
}

/** Relative wording ("hace 3 días") holds under this many days; after it a date reads better. */
export const RELATIVE_WINDOW_DAYS = 7;
const DAY_MS = 86_400_000;

/** "12 oct", with the year only when it is not this year. */
function shortDate(date: Date, locale: string, now: Date): string {
  const year = date.getFullYear() === now.getFullYear() ? {} : { year: "numeric" as const };
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", ...year }).format(date);
}

/** A `YYYY-MM-DD` day as "12 oct", with the year only when it is not this year. */
export function formatShortDay(day: string, locale: string, now = new Date()): string {
  const date = new Date(`${day.slice(0, 10)}T12:00:00`);
  if (Number.isNaN(date.getTime())) return day;
  return shortDate(date, locale, now);
}

/** "hace 15 minutos", "ayer", "hace 3 días" under seven days; "12 oct" from then on. */
export function formatRelativeTime(iso: string | null, locale: string, now = new Date()): string {
  if (!iso) return "";
  const date = new Date(iso);
  const then = date.getTime();
  if (Number.isNaN(then)) return "";
  const elapsed = then - now.getTime();
  if (Math.abs(elapsed) >= RELATIVE_WINDOW_DAYS * DAY_MS) return shortDate(date, locale, now);
  const minutes = Math.round(elapsed / 60_000);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  if (Math.abs(minutes) < 60) return rtf.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return rtf.format(hours, "hour");
  return rtf.format(Math.trunc(elapsed / DAY_MS), "day");
}

/** A calendar day against today: "hoy", "ayer", "hace 3 días", "en 2 días" under seven days; "12 oct" from then on. */
export function formatRelativeDay(day: string, today: string, locale: string): string {
  const at = (value: string) => Date.UTC(Number(value.slice(0, 4)), Number(value.slice(5, 7)) - 1, Number(value.slice(8, 10)));
  const days = Math.round((at(day) - at(today)) / DAY_MS);
  if (Number.isNaN(days)) return day;
  if (Math.abs(days) >= RELATIVE_WINDOW_DAYS) return formatShortDay(day, locale, new Date(`${today}T12:00:00`));
  return new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(days, "day");
}

export type PeriodKey = "this_month" | "last_month" | "last_30_days" | "all" | "custom";
/** `to` null means "through today by the server's clock": the API fills it. */
export type Period = { key: PeriodKey; from: string; to: string | null };
export const PERIOD_PRESETS: PeriodKey[] = ["this_month", "last_month", "last_30_days", "all"];
/** "All" starts before any receipt this product can hold. */
export const ALL_FROM = "2000-01-01";

function isoDay(date: Date): string {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

export function todayIso(now = new Date()): string {
  return isoDay(now);
}

export function periodRange(key: PeriodKey, now = new Date()): Period {
  if (key === "all") return { key, from: ALL_FROM, to: null };
  if (key === "custom") return { key, from: isoDay(new Date(now.getFullYear(), now.getMonth(), 1)), to: isoDay(now) };
  if (key === "last_month") {
    const first = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const last = new Date(now.getFullYear(), now.getMonth(), 0);
    return { key, from: isoDay(first), to: isoDay(last) };
  }
  if (key === "last_30_days") {
    const start = new Date(now);
    start.setDate(start.getDate() - 29);
    return { key, from: isoDay(start), to: null };
  }
  return { key, from: isoDay(new Date(now.getFullYear(), now.getMonth(), 1)), to: null };
}

export const RECEIPT_CATEGORY_IDS = [
  "other",
  "groceries",
  "dining",
  "transport",
  "housing",
  "health",
  "shopping",
  "interest_fees",
] as const;

/** A range the person typed; both days are required and in order. */
export function customPeriod(from: string, to: string): Period | null {
  const day = /^\d{4}-\d{2}-\d{2}$/;
  if (!day.test(from) || !day.test(to) || from > to) return null;
  return { key: "custom", from, to };
}

/** The first period filter whose range holds `day`, if any does. */
export function periodContaining(day: string, now = new Date()): PeriodKey | null {
  const keys: PeriodKey[] = ["this_month", "last_month", "last_30_days"];
  return (
    keys.find((key) => {
      const { from, to } = periodRange(key, now);
      return from <= day && day <= (to ?? isoDay(now));
    }) ?? null
  );
}
