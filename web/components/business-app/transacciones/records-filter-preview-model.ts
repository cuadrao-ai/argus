import { currencyDigits } from "@/lib/money-entry";
import type { Money } from "./transacciones-model";

export const FILTER_GROUPS = ["review", "attachment", "amount", "counterparty", "category", "account", "document", "fiscal"] as const;
export type FilterGroup = typeof FILTER_GROUPS[number];
export type ReviewFilter = "review" | "approval" | "export";
export type PreviewFilters = {
  review: ReviewFilter[];
  attachment: "any" | "with" | "without";
  amount: { currency: "" | "DOP" | "USD" | "EUR"; min: string; max: string };
  counterparty: string[];
  category: string[];
  account: string[];
  document: string[];
  fiscal: string[];
};
export const emptyPreviewFilters = (): PreviewFilters => ({ review: [], attachment: "any", amount: { currency: "", min: "", max: "" }, counterparty: [], category: [], account: [], document: [], fiscal: [] });
export const activeFilterGroups = (filters: PreviewFilters): FilterGroup[] => FILTER_GROUPS.filter((group) => group === "attachment" ? filters.attachment !== "any" : group === "amount" ? Boolean(filters.amount.currency) : filters[group].length > 0);
export const validPreviewAmount = ({ min, max }: PreviewFilters["amount"]): boolean => {
  const valid = (value: string) => !value || /^\d+(\.\d{1,2})?$/.test(value);
  const cents = (value: string) => { const [whole, fraction = ""] = value.split("."); return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0")); };
  return valid(min) && valid(max) && (!min || !max || cents(min) <= cents(max));
};

export function matchesPreviewAmount(money: Money, filter: PreviewFilters["amount"]): boolean {
  if (!filter.currency) return true;
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
