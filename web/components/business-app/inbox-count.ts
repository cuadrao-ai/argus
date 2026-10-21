import type { BusinessCapture, ReceiptActivityCounts } from "@/lib/business-api";
import { emailStanding, type BusinessEmailDelivery, type EmailStanding } from "@/lib/business-email";
import { countNeedsAttention, countPorRevisar, countStillReading, type ReviewCountItem } from "@/lib/business-review-count";

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

type CountRecords = {
  inbox?: readonly ReviewCountItem[] | null;
  notes?: readonly BusinessCapture[] | null;
  emails?: readonly BusinessEmailDelivery[] | null;
  emailsError?: boolean;
  receiptActivity?: ReceiptActivityCounts | null;
};

/**
 * The server counts every row, past any page the browser loaded. Its email
 * part is only trusted once it says where each email stands (#1341); before
 * that, the emails are counted from the list.
 */
function serverCountsEmails(records: CountRecords): boolean {
  return Boolean(records.receiptActivity) && (records.emails ?? []).every((email) => email.standing !== undefined);
}

/** The emails as far as they are known: an outage counts as none, so it never hides the receipts' own count. */
function knownEmails(records: CountRecords): BandejaEmail[] | null {
  const emails = records.emails ?? (records.emailsError ? [] : null);
  return emails ? bandejaEmails(emails) : null;
}

/**
 * The one "por revisar" number: receipts ready for review plus typed notes
 * awaiting it. Inicio, the sidebar badge, the phone tab and the Bandeja's
 * segment all show this count. An email being read waits, like a receipt being read.
 */
export function inboxCount(records: CountRecords): number | null {
  const ready = records.receiptActivity?.ready_to_review_count;
  if (typeof ready === "number") return ready;
  if (!records.inbox) return null;
  return countPorRevisar(records.inbox) + (records.notes ? openNotesByDraft(records.notes).length : 0);
}

/** The one "con problema" number: receipts that need a fix plus emails that brought no receipt. */
export function problemCount(records: CountRecords): number | null {
  if (records.receiptActivity && records.emails && serverCountsEmails(records)) return records.receiptActivity.needs_attention_count;
  const emails = knownEmails(records);
  if (!records.inbox || !emails) return null;
  return countNeedsAttention(records.inbox) + emails.filter((email) => email.standing === "no_receipt").length;
}

/** Receipts and emails still being read. */
export function readingCount(records: CountRecords): number | null {
  if (records.receiptActivity && records.emails && serverCountsEmails(records)) return records.receiptActivity.reading_count;
  const emails = knownEmails(records);
  if (!records.inbox || !emails) return null;
  return countStillReading(records.inbox) + emails.filter((email) => email.standing === "reading").length;
}
