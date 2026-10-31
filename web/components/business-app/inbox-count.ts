import type { BusinessCapture, ReceiptActivityCounts } from "@/lib/business-api";
import type { BusinessEmailDelivery, EmailStanding } from "@/lib/business-email";

export type OpenNote = { draftId: string; text: string; receivedAt: string; revision: number; earlier: number };

/**
 * One row per draft still awaiting review: its latest note, and how many came
 * before it as the server counts them over every note of the draft, not only
 * the page. Recorded and dismissed drafts leave the Inbox.
 */
export function openNotesByDraft(captures: readonly BusinessCapture[]): OpenNote[] {
  const byDraft = new Map<string, OpenNote>();
  for (const note of captures) {
    if (note.review_state !== "open" && note.review_state !== "accepting") continue;
    const current = byDraft.get(note.draft_id);
    if (!current || note.received_at > current.receivedAt) {
      byDraft.set(note.draft_id, { draftId: note.draft_id, text: note.text, receivedAt: note.received_at, revision: Math.max(note.revision, current?.revision ?? 0), earlier: note.earlier_count ?? 0 });
    } else {
      current.revision = Math.max(note.revision, current.revision);
    }
  }
  return [...byDraft.values()].sort((a, b) => (a.receivedAt < b.receivedAt ? 1 : -1));
}

/** An email that is a Bandeja row of its own: one still being read, or one that brought no receipt. */
export type BandejaEmail = { delivery: BusinessEmailDelivery; standing: EmailStanding };

export function bandejaEmails(deliveries: readonly BusinessEmailDelivery[]): BandejaEmail[] {
  return deliveries.flatMap((delivery) => (delivery.standing ? [{ delivery, standing: delivery.standing }] : []));
}

export type CountRecords = {
  receiptActivity?: ReceiptActivityCounts | null;
  /** Inbox groups in server order. The Bandeja badge adds `remitentes_nuevos` for the owner. */
  emailInbox?: readonly { id: string; items: readonly unknown[] }[] | null;
};

// The Bandeja's numbers are the server's: it counts every receipt, note and
// email past any page the browser loaded. Without its answer a number is
// unknown, never 0 and never a count of the rows that happened to load.

/** The one "por revisar" number Inicio, the sidebar badge, the phone tab and the Bandeja's segment show. */
export function inboxCount(records: CountRecords, viewer?: { role?: string } | null): number | null {
  const base = records.receiptActivity?.ready_to_review_count ?? null;
  if (base === null) return null;
  if (viewer?.role !== "owner") return base;
  const extra = records.emailInbox?.find((group) => group.id === "remitentes_nuevos")?.items.length ?? 0;
  return base + extra;
}

/** The one "con problema" number: receipts that need a fix plus emails that brought no receipt. */
export function problemCount(records: CountRecords): number | null {
  return records.receiptActivity?.needs_attention_count ?? null;
}

/** The one "por igualar" number the sidebar shows; null while bank matching is off on the server, never 0 for off. */
export function porIgualarCount(records: CountRecords): number | null {
  return records.receiptActivity?.por_igualar_count ?? null;
}

/** Receipts and emails still being read. */
export function readingCount(records: CountRecords): number | null {
  return records.receiptActivity?.reading_count ?? null;
}
