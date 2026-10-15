import type { ReceiptActivityCounts } from "@/lib/business-api";

/**
 * The Bandeja's number for the Resumen card and the sidebar badge, exactly as
 * the server counts it: every row the Bandeja lists, receipts awaiting review
 * and notes no receipt carries. Unread is a different count (the badge's dot).
 * Null until the server answers, because an unknown count is not zero.
 */
export function inboxCount(records: { receiptActivity?: ReceiptActivityCounts | null }): number | null {
  return records.receiptActivity?.pending_review_count ?? null;
}
