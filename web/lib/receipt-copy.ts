import enCommon from "@/public/locales/en/common.json";
import esCommon from "@/public/locales/es-419/common.json";
import { createInstance } from "i18next";
import type { ArgusLanguage } from "./language-features";

/**
 * Server-side copy for the public receipt route.
 *
 * The receipt is a standalone public page opened by people who are not signed
 * in, so there is no stored language preference to honour and no client i18n
 * provider to wait for. Language comes from the request, the page renders in one
 * pass, and the strings still live in the shared locale files so they translate
 * with everything else.
 */
export type ReceiptCopy = typeof enCommon.receipt;

const COPY: Record<ArgusLanguage, ReceiptCopy> = {
  en: enCommon.receipt,
  "es-419": esCommon.receipt as ReceiptCopy,
};

export function receiptLanguageFromAcceptLanguage(
  header: string | null | undefined,
): ArgusLanguage {
  if (!header) return "en";
  const preferred = header
    .split(",")
    .map((entry) => {
      const [tag, ...parameters] = entry.trim().split(";");
      const quality = parameters
        .map((parameter) => parameter.trim())
        .find((parameter) => parameter.startsWith("q="));
      const weight = quality ? Number.parseFloat(quality.slice(2)) : 1;
      return { tag: tag.trim().toLowerCase(), weight: Number.isNaN(weight) ? 0 : weight };
    })
    .filter((entry) => entry.tag && entry.weight > 0)
    .sort((left, right) => right.weight - left.weight);
  for (const entry of preferred) {
    if (entry.tag.startsWith("es")) return "es-419";
    if (entry.tag.startsWith("en")) return "en";
  }
  return "en";
}

export function receiptCopy(language: ArgusLanguage): ReceiptCopy {
  return COPY[language] ?? COPY.en;
}

// The card's display owners need the same catalog translator on the standalone
// SSR page and inside the owner's preview, without a browser i18n provider.
const receiptI18n = createInstance();
void receiptI18n.init({
  initAsync: false, fallbackLng: "en", interpolation: { escapeValue: false },
  resources: { en: { translation: enCommon }, "es-419": { translation: esCommon } },
});
export const receiptTranslator = (language: ArgusLanguage) => receiptI18n.getFixedT(language);

export function formatReceiptDate(
  value: string | null | undefined,
  language: ArgusLanguage,
): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat(language === "es-419" ? "es-419" : "en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

const DATE_LOCALE: Record<ArgusLanguage, string> = {
  en: "en-US",
  "es-419": "es-419",
};

/**
 * One frozen calendar date, spoken in the viewer's language.
 *
 * UTC on purpose: the payload froze a calendar day, not an instant, so reading it
 * in the viewer's zone would slide the tested window by a day for anyone west of
 * Greenwich.
 */
export function formatReceiptDay(
  value: string | null | undefined,
  language: ArgusLanguage,
): string | null {
  if (!value) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat(DATE_LOCALE[language] ?? DATE_LOCALE.en, {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

/** The tested window. Nothing is rendered when either end will not parse. */
export function formatReceiptDateRange(
  range: { start: string; end: string } | null | undefined,
  copy: ReceiptCopy,
  language: ArgusLanguage,
): string | null {
  const start = formatReceiptDay(range?.start, language);
  const end = formatReceiptDay(range?.end, language);
  if (!start || !end) return null;
  return interpolate(copy.date_range, { start, end });
}

/** A frozen bare number, given the viewer's own grouping and decimal marks. */
export function formatReceiptNumber(
  value: string | null | undefined,
  language: ArgusLanguage,
): string | null {
  if (!value) return null;
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) return null;
  return new Intl.NumberFormat(DATE_LOCALE[language] ?? DATE_LOCALE.en, {
    maximumFractionDigits: 2,
  }).format(parsed);
}

export function interpolate(
  template: string,
  values: Record<string, string | number>,
): string {
  return template.replace(/\{\{\s*(\w+)\s*\}\}/g, (match, key: string) =>
    key in values ? String(values[key]) : match,
  );
}
