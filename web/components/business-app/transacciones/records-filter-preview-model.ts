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
