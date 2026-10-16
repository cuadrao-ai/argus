import type { ReceiptSummary } from "@/lib/business-api";

/** The Bandeja's receipt rows in the server's order. An email's own document lives inside its email row, never here. */
export function bandejaReceipts<T extends Pick<ReceiptSummary, "email_original">>(items: readonly T[]): T[] {
  return items.filter((receipt) => !receipt.email_original);
}

/**
 * The receipt to open once `approvedId` has left the Bandeja: the first row
 * still waiting that followed it in the order the person saw, else the first
 * row still waiting. Null when nothing is left to review.
 */
export function nextBandejaReceipt(
  approvedId: string,
  seen: readonly Pick<ReceiptSummary, "id" | "email_original">[] | null,
  fresh: readonly Pick<ReceiptSummary, "id" | "email_original">[],
): string | null {
  const waiting = bandejaReceipts(fresh).filter((receipt) => receipt.id !== approvedId);
  const order = (seen ?? []).map((receipt) => receipt.id);
  const position = order.indexOf(approvedId);
  const after = position < 0 ? undefined : waiting.find((receipt) => order.indexOf(receipt.id) > position);
  return (after ?? waiting[0])?.id ?? null;
}
