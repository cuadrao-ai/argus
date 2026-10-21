import type { BusinessCapture, ReceiptActivityCounts } from "@/lib/business-api";
import { emailStanding, type BusinessEmailDelivery, type EmailStanding } from "@/lib/business-email";

export type OpenNote = { draftId: string; text: string; receivedAt: string; revision: number; earlier: number };

/**
 * One row per draft still awaiting review: its latest note, and how many came
 * before it. Recorded and dismissed drafts leave the Inbox.
 */
export function openNotesByDraft(captures: readonly BusinessCapture[]): OpenNote[] {
  const byDraft = new Map<string, OpenNote>();
  for (const note of captures) {
    if (note.review_state !== "open" && note.review_state !== "accepting") continue;
    const current = byDraft.get(note.draft_id);
    if (!current) {
      byDraft.set(note.draft_id, { draftId: note.draft_id, text: note.text, receivedAt: note.received_at, revision: note.revision, earlier: 0 });
    } else if (note.received_at > current.receivedAt) {
      byDraft.set(note.draft_id, { ...current, text: note.text, receivedAt: note.received_at, revision: Math.max(note.revision, current.revision), earlier: current.earlier + 1 });
    } else {
      current.earlier += 1;
      current.revision = Math.max(note.revision, current.revision);
    }
  }
  return [...byDraft.values()].sort((a, b) => (a.receivedAt < b.receivedAt ? 1 : -1));
}

/** An email that is a Bandeja row of its own: one still being read, or one that brought no receipt. */
export type BandejaEmail = { delivery: BusinessEmailDelivery; standing: EmailStanding };

export function bandejaEmails(deliveries: readonly BusinessEmailDelivery[]): BandejaEmail[] {
  return deliveries.flatMap((delivery) => {
    const standing = emailStanding(delivery);
    return standing ? [{ delivery, standing }] : [];
  });
}

type CountRecords = { receiptActivity?: ReceiptActivityCounts | null };

// The Bandeja's numbers are the server's: it counts every receipt, note and
// email past any page the browser loaded. Without its answer a number is
// unknown, never 0 and never a count of the rows that happened to load.

/** The one "por revisar" number Inicio, the sidebar badge, the phone tab and the Bandeja's segment show. */
export function inboxCount(records: CountRecords): number | null {
  return records.receiptActivity?.ready_to_review_count ?? null;
}

/** The one "con problema" number: receipts that need a fix plus emails that brought no receipt. */
export function problemCount(records: CountRecords): number | null {
  return records.receiptActivity?.needs_attention_count ?? null;
}

/** Receipts and emails still being read. */
export function readingCount(records: CountRecords): number | null {
  return records.receiptActivity?.reading_count ?? null;
}
