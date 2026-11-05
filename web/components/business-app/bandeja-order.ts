import type { ReceiptSummary } from "@/lib/business-api";

/** The Bandeja's receipt rows in the server's order. An email's own document lives inside its email row, never here. */
export function bandejaReceipts<T extends Pick<ReceiptSummary, "email_original">>(items: readonly T[]): T[] {
  return items.filter((receipt) => !receipt.email_original);
}

/**
 * The receipt to open once `approvedId` has left the Bandeja: the first row
 * still waiting that followed it in the order the person saw. Null past the
 * last row, so the Bandeja opens and lists any row the person skipped.
 */
export function nextBandejaReceipt(
  approvedId: string,
  seen: readonly Pick<ReceiptSummary, "id" | "email_original">[] | null,
  fresh: readonly Pick<ReceiptSummary, "id" | "email_original">[],
): string | null {
  const order = (seen ?? []).map((receipt) => receipt.id);
  const position = order.indexOf(approvedId);
  if (position < 0) return null;
  return bandejaReceipts(fresh).find((receipt) => receipt.id !== approvedId && order.indexOf(receipt.id) > position)?.id ?? null;
}

let titleFocusPending: string | null = null;

/** Only the receipt opened by Aprobar y siguiente can take its heading focus, once. */
export function handTitleFocus(receiptId: string): void {
  titleFocusPending = receiptId;
}

export function takeTitleFocus(receiptId: string): boolean {
  if (titleFocusPending !== receiptId) return false;
  titleFocusPending = null;
  return true;
}

export function clearTitleFocusUnless(recordId?: string): void {
  if (titleFocusPending !== recordId) titleFocusPending = null;
}
