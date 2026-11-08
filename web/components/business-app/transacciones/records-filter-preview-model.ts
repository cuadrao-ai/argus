import { currencyDigits, MONEY_MAX_INTEGER_DIGITS } from "@/lib/money-entry";
import type { RecordsCurrency, ReportStage } from "@/lib/business-reports-api";
import type { Money } from "./transacciones-model";

export const FILTER_GROUPS = ["review", "attachment", "amount", "counterparty", "expense_type", "account", "document", "fiscal"] as const;
export type FilterGroup = typeof FILTER_GROUPS[number];
export const STAGE_FILTERS = [
  { key: "fiscal", stage: "needs_fiscal_data", card: true },
  { key: "export", stage: "ready_for_export", card: false },
  { key: "exported", stage: "exported", card: false },
  { key: "review", stage: "needs_review", card: false },
] as const satisfies readonly { key: string; stage: ReportStage; card: boolean }[];
export type ReviewFilter = typeof STAGE_FILTERS[number]["key"];
export type CardFilter = Extract<typeof STAGE_FILTERS[number], { card: true }>["key"];
export const REVIEW_FILTERS: readonly ReviewFilter[] = STAGE_FILTERS.map((entry) => entry.key);
export const STAGE_OF: Readonly<Record<ReviewFilter, ReportStage>> = Object.fromEntries(STAGE_FILTERS.map((entry) => [entry.key, entry.stage])) as Record<ReviewFilter, ReportStage>;
export const FILTER_OF_STAGE: Readonly<Record<ReportStage, ReviewFilter>> = Object.fromEntries(STAGE_FILTERS.map((entry) => [entry.stage, entry.key])) as Record<ReportStage, ReviewFilter>;
export type PreviewFilters = {
  review: ReviewFilter[];
  attachment: "any" | "with" | "without";
  amount: { currency: RecordsCurrency; min: string; max: string };
  counterparty: string[];
  /** 606 tipo de gasto codes, or `missing` for a purchase that still needs one. */
  expense_type: string[];
  account: string[];
  document: string[];
  fiscal: string[];
};
export const emptyPreviewFilters = (currency: RecordsCurrency): PreviewFilters => ({ review: [], attachment: "any", amount: { currency, min: "", max: "" }, counterparty: [], expense_type: [], account: [], document: [], fiscal: [] });
export const activeFilterGroups = (filters: PreviewFilters): FilterGroup[] => FILTER_GROUPS.filter((group) => group === "attachment" ? filters.attachment !== "any" : group === "amount" ? Boolean(filters.amount.min || filters.amount.max) : filters[group].length > 0);
export const validPreviewAmount = ({ min, max, currency }: PreviewFilters["amount"]): boolean => {
  const digits = currencyDigits(currency);
  const valid = (value: string) => !value || /^\d+(?:\.\d+)?$/.test(value) && (value.split(".")[1]?.length ?? 0) <= digits && value.split(".")[0].replace(/^0+/, "").length <= MONEY_MAX_INTEGER_DIGITS;
  const minor = (value: string) => { const [whole, fraction = ""] = value.split("."); return BigInt(whole) * BigInt(10) ** BigInt(digits) + BigInt(fraction.padEnd(digits, "0") || "0"); };
  return valid(min) && valid(max) && (!min || !max || minor(min) <= minor(max));
};

export function matchesPreviewAttachment(hasProof: boolean | null, filter: PreviewFilters["attachment"]): boolean {
  return filter === "any" || hasProof === (filter === "with");
}

export function matchesPreviewAmount(money: Money, filter: PreviewFilters["amount"]): boolean {
  if (money.currency !== filter.currency) return false;
  if (!filter.min && !filter.max) return true;
  if (!validPreviewAmount(filter)) return false;
  const digits = currencyDigits(money.currency);
  const minor = (value: string): bigint | null => {
    const match = /^[+-]?(\d+)(?:\.(\d+))?$/.exec(value);
    return !match || (match[2]?.length ?? 0) > digits ? null : BigInt(match[1] + (match[2] ?? "").padEnd(digits, "0"));
  };
  const amount = minor(money.amount);
  const min = filter.min ? minor(filter.min) : null;
  const max = filter.max ? minor(filter.max) : null;
  return amount !== null && (!filter.min || (min !== null && amount >= min)) && (!filter.max || (max !== null && amount <= max));
}
