/**
 * The one Inicio count: receipts waiting for a person to review.
 * Still-reading and unreadable receipts are other lines. They never add to this number.
 */

export type ReviewCountItem = {
  status?: string | null;
  attention?: string | null;
  activity?: { state?: string | null } | null;
};

export type ReviewBucket = "por_revisar" | "reading" | "unreadable";

/** One row, one line. Reading wins, then a receipt that cannot be read, then one waiting for review. */
export function reviewBucket(item: ReviewCountItem): ReviewBucket | null {
  if (item.activity?.state === "reading") return "reading";
  if (item.attention === "unreadable" || item.status === "needs_attention") return "unreadable";
  if (item.status === "review_ready") return "por_revisar";
  return null;
}

export function countPorRevisar(items: readonly ReviewCountItem[]): number {
  return items.reduce((count, item) => count + (reviewBucket(item) === "por_revisar" ? 1 : 0), 0);
}

export function countReviewBucket(items: readonly ReviewCountItem[], bucket: Exclude<ReviewBucket, "por_revisar">): number {
  return items.reduce((count, item) => count + (reviewBucket(item) === bucket ? 1 : 0), 0);
}
