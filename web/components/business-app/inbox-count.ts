import { countPorRevisar, type ReviewCountItem } from "@/lib/business-review-count";

export function inboxCount(records: { inbox?: readonly ReviewCountItem[] | null }): number | null {
  if (!records.inbox) return null;
  return countPorRevisar(records.inbox);
}
