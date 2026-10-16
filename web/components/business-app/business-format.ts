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

/**
 * Reads back a saved amount from its decimal string: padded to the currency's
 * digits and never rounded or passed through a float. The symbol names which
 * dollar it is.
 */
export function formatMoney(
  amount: string | null,
  currency: string | null,
  locale: string,
): string {
  if (amount === null || currency === null) return "";
  const match = DECIMAL_AMOUNT.exec(amount.trim());
  if (!match) return `${currency} ${amount}`;
  const [, sign, whole, fraction = ""] = match;
  const { group, decimal } = separators(locale);
  const digits = Math.max(currencyDigits(currency), fraction.length);
  let grouped = "";
  for (let index = 0; index < whole.length; index += 1) {
    if (index > 0 && (whole.length - index) % 3 === 0) grouped += group;
    grouped += whole[index];
  }
  const number = digits > 0 ? `${grouped}${decimal}${fraction.padEnd(digits, "0")}` : grouped;
  return `${sign}${currencySymbol(currency)} ${number}`;
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

export function formatRelativeTime(iso: string | null, locale: string): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const minutes = Math.round((then - Date.now()) / 60_000);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  if (Math.abs(minutes) < 60) return rtf.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return rtf.format(hours, "hour");
  return rtf.format(Math.round(hours / 24), "day");
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
