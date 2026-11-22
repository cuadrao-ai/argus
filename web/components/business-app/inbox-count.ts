import type { BusinessCapture, CountedAnswer, DocumentDeleteAccess, BandejaGroup, ReceiptActivityCounts } from "@/lib/business-api";
import type { BusinessDataSource } from "./business-data";
import type { BusinessEmailDelivery, EmailStanding } from "@/lib/business-email";
import type { SentBy } from "@/lib/sent-by";

export type OpenNote = DocumentDeleteAccess & { bandeja_group?: BandejaGroup | null; sent_by?: SentBy | null; draftId: string; text: string; receivedAt: string; revision: number; earlier: number };

/**
 * One row per draft still awaiting review: its latest note, and how many came
 * before it as the server counts them over every note of the draft, not only
 * the page. Recorded and dismissed drafts leave the Inbox.
 */
export function openNotesByDraft(captures: readonly BusinessCapture[], includeDeleted = false): OpenNote[] {
  const byDraft = new Map<string, OpenNote>();
  for (const note of captures) {
    if (note.review_state !== "open" && note.review_state !== "accepting" && !(includeDeleted && note.deleted)) continue;
    const current = byDraft.get(note.draft_id);
    if (!current || note.received_at > current.receivedAt) {
      byDraft.set(note.draft_id, { deleted: note.deleted, delete_available: note.delete_available, restore_available: note.restore_available, bandeja_group: note.bandeja_group, sent_by: note.sent_by, draftId: note.draft_id, text: note.text, receivedAt: note.received_at, revision: Math.max(note.revision, current?.revision ?? 0), earlier: note.earlier_count ?? 0 });
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

export type CountRecords = { receiptActivity?: ReceiptActivityCounts | null };

// The Bandeja's numbers are the server's: it counts every receipt, note and
// email past any page the browser loaded. Without its answer a number is
// unknown, never 0 and never a count of the rows that happened to load.

/**
 * The source whose actions hand the counts they answer with to the workspace, the one owner of them. Every screen
 * reads its actions from this source, so the tabs and badges change with the answer and no screen asks again.
 * `expect` runs as an action starts and returns where that action's counts go.
 */
export function withAnsweredCounts(source: BusinessDataSource, expect: () => (counts: ReceiptActivityCounts) => void): BusinessDataSource {
  const counted = <A extends unknown[], R extends CountedAnswer>(act: (...args: A) => Promise<R>) => async (...args: A): Promise<R> => {
    const show = expect();
    const answer = await act(...args);
    show(answer.inbox_counts);
    return answer;
  };
  return {
    ...source,
    approveDraft: counted(source.approveDraft),
    approveListos: counted(source.approveListos),
    deleteDocument: source.deleteDocument && counted(source.deleteDocument),
    restoreDocument: source.restoreDocument && counted(source.restoreDocument),
    purgeDocument: source.purgeDocument && counted(source.purgeDocument),
  };
}

/** The one number Inicio, the sidebar badge and the phone tab show: every row waiting in the Bandeja, which the server keeps equal to its two tabs together. */
export function inboxCount(records: CountRecords): number | null {
  return records.receiptActivity?.pending_review_count ?? null;
}

/** The Bandeja's Por resolver tab. */
export function bandejaAttentionCount(records: CountRecords): number | null {
  return records.receiptActivity?.bandeja_attention_count ?? null;
}

/** The Bandeja's Listos tab. */
export function bandejaListoCount(records: CountRecords): number | null {
  return records.receiptActivity?.bandeja_listo_count ?? null;
}

/** The one "por igualar" number the sidebar shows; null while bank matching is off on the server, never 0 for off. */
export function porIgualarCount(records: CountRecords): number | null {
  return records.receiptActivity?.por_igualar_count ?? null;
}
