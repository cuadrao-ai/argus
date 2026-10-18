/**
 * The one Bandeja count: receipts a person can review.
 * Still-reading and unreadable receipts are other lines, never this number.
 * An email's own document is not a Bandeja row.
 */

export type ReviewCountItem = {
  status?: string;
  attention?: string | null;
  activity?: { state?: string | null } | null;
  read_pending?: boolean;
  email_original?: boolean;
};

function closed(item: ReviewCountItem): boolean {
  return Boolean(item.email_original) || item.status === "confirmed" || item.status === "dismissed";
}

export function isStillReading(item: ReviewCountItem): boolean {
  if (closed(item)) return false;
  return item.activity?.state === "reading" || item.read_pending === true || item.status === "queued" || item.status === "preparing";
}

export function isUnreadable(item: ReviewCountItem): boolean {
  if (closed(item) || isStillReading(item)) return false;
  return item.attention === "unreadable";
}

export function porRevisar<T extends ReviewCountItem>(items: readonly T[]): T[] {
  return items.filter((item) => !closed(item) && !isStillReading(item) && !isUnreadable(item));
}

export function countPorRevisar(items: readonly ReviewCountItem[]): number {
  return porRevisar(items).length;
}

export function countStillReading(items: readonly ReviewCountItem[]): number {
  return items.filter(isStillReading).length;
}

export function countUnreadable(items: readonly ReviewCountItem[]): number {
  return items.filter(isUnreadable).length;
}
