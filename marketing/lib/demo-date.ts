import type { BusinessLocale } from "./site-routes";

// The scene stays on the e-CF deadline until it passes, then follows today.
export const CAMPAIGN_DAY = "2026-11-15";

export type DemoDates = {
  long: string;
  bar: string;
  short: string;
  month: string;
  monthLower: string;
};

const LOCALE_TAG: Record<BusinessLocale, string> = { es: "es-DO", en: "en-US" };

function day(key: string): Date {
  const [year, month, date] = key.split("-").map(Number);
  return new Date(year, month - 1, date);
}

export function localDayKey(today: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
}

export function demoDayKey(todayKey: string): string {
  return todayKey > CAMPAIGN_DAY ? todayKey : CAMPAIGN_DAY;
}

export function demoDates(key: string, locale: BusinessLocale): DemoDates {
  const shown = day(key);
  const closing = new Date(shown.getFullYear(), shown.getMonth() - 1, 1);
  const tag = LOCALE_TAG[locale];
  const format = (date: Date, options: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat(tag, options).format(date);
  const month = format(closing, { month: "long" });
  const weekday = format(shown, { weekday: "short" }).replace(".", "");
  const shortMonth = format(shown, { month: "short" }).replace(".", "");
  const [year, monthNumber, date] = key.split("-");
  return {
    long: format(shown, { weekday: "long", day: "numeric", month: "long" }),
    bar: `${weekday} ${shown.getDate()} ${shortMonth}`,
    short: `${date}-${monthNumber}-${year}`,
    month: month.charAt(0).toUpperCase() + month.slice(1),
    monthLower: month,
  };
}
