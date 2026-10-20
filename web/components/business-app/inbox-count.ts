import type { BusinessCapture } from "@/lib/business-api";
import { countPorRevisar, type ReviewCountItem } from "@/lib/business-review-count";

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

/**
 * The one "por revisar" number: receipts ready for review plus typed notes
 * awaiting it. Inicio, the sidebar badge, the phone tab and the Bandeja's
 * segment all show this count.
 */
export function inboxCount(records: { inbox?: readonly ReviewCountItem[] | null; notes?: readonly BusinessCapture[] | null }): number | null {
  if (!records.inbox) return null;
  return countPorRevisar(records.inbox) + (records.notes ? openNotesByDraft(records.notes).length : 0);
}
