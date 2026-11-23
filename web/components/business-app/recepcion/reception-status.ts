import type { ReceiptSummary } from "@/lib/business-api";

/** The four row tags, plus the existing word for a discarded receipt. `reason` is a code the server sent. */
export type ReceptionTag =
  | { tag: "reading" }
  | { tag: "attention"; reason: string | null }
  | { tag: "listo" }
  | { tag: "approved" }
  | { tag: "dismissed" };

/** A receipt's tag, from the server's Bandeja group. Every place that says a receipt needs attention or is ready reads it here. */
export function receiptTag({ status, bandeja_group: group }: Pick<ReceiptSummary, "status" | "bandeja_group">): ReceptionTag {
  if (status === "confirmed") return { tag: "approved" };
  if (status === "dismissed") return { tag: "dismissed" };
  if (group?.group === "listo") return { tag: "listo" };
  if (group?.reason === "reading") return { tag: "reading" };
  return { tag: "attention", reason: group?.reason ?? null };
}
