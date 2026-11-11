import { enteredIn } from "@/lib/business-grant";
import { randomId } from "@/lib/random-id";
import { captureOutcomeUnknown } from "./ManualCaptureDialog";
import type { DocumentType } from "./receipt-upload-queue";

/**
 * Text the owner typed instead of uploading a file; it becomes a Bandeja draft like any receipt. It keeps the
 * Business it was typed in, and every save and retry carries that Business, whatever is chosen when it is sent.
 */
export type TypedNote = { key: string; grant: string | null; text: string; documentType: DocumentType; status: "saving" | "saved" | "uncertain" | "refused" };
type Capture = (input: { text: string; document_type: DocumentType }, key: string, grant: string | null) => Promise<unknown>;

/** Text typed in Escríbelo and not yet saved, with the Compra or Venta chosen for it. */
export type NoteDraft = { readonly text: string; readonly documentType: DocumentType | null };
const NO_DRAFT: NoteDraft = { text: "", documentType: null };

/** A note still saving, or one whose save is unconfirmed and so waits for its retry, is lost if the page goes. */
export const isUnfinishedNote = (note: TypedNote) => note.status === "saving" || note.status === "uncertain";
/** Typed text is lost if the page goes; a chosen type alone is not worth asking about. */
export const hasDraftText = (draft: NoteDraft) => draft.text.trim() !== "";

/**
 * Owned by one mounted business workspace, like the upload queue, so closing Agregar never drops a note, from
 * its unsaved draft to a save that is running or unconfirmed. Each Business keeps its own draft. A retry repeats
 * the note's one key, so it is never saved twice.
 */
export class TypedNoteQueue {
  private items: readonly TypedNote[] = [];
  private drafts = new Map<string | null, NoteDraft>();
  private listeners = new Set<() => void>();

  constructor(private onSaved: () => void) {}

  snapshot = () => this.items;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  get unfinished() { return this.items.some(isUnfinishedNote) || [...this.drafts.values()].some(hasDraftText); }

  draft = (grant: string | null) => this.drafts.get(grant) ?? NO_DRAFT;

  editDraft(grant: string | null, change: Partial<NoteDraft>) {
    const next = { ...this.draft(grant), ...change };
    if (next.text || next.documentType) this.drafts.set(grant, next);
    else this.drafts.delete(grant);
    this.publish(this.items);
  }

  /** Saving a note ends its Business's draft. */
  add(note: Pick<TypedNote, "grant" | "text" | "documentType">, capture: Capture) {
    const entry: TypedNote = { ...note, key: randomId(), status: "saving" };
    this.drafts.delete(note.grant);
    this.publish([entry, ...this.items]);
    return this.send(entry, capture);
  }

  retry(key: string, capture: Capture) {
    const entry = this.items.find((item) => item.key === key);
    return entry?.status === "uncertain" ? this.send(entry, capture) : Promise.resolve();
  }

  /** Closing Agregar forgets what that Business finished; a note still saving or unconfirmed stays for its retry. */
  clearSettled(grant: string | null) {
    const entered = enteredIn(grant);
    this.publish(this.items.filter((item) => !entered(item) || isUnfinishedNote(item)));
  }

  private async send(entry: TypedNote, capture: Capture) {
    this.update(entry.key, "saving");
    try {
      await capture({ text: entry.text, document_type: entry.documentType }, entry.key, entry.grant);
    } catch (error) {
      const { status, code } = error as { status?: number; code?: string };
      this.update(entry.key, status && status >= 400 && status < 500 && !captureOutcomeUnknown(status, code) ? "refused" : "uncertain");
      return;
    }
    this.update(entry.key, "saved");
    this.onSaved();
  }

  private update(key: string, status: TypedNote["status"]) {
    this.publish(this.items.map((item) => (item.key === key ? { ...item, status } : item)));
  }

  private publish(items: readonly TypedNote[]) {
    this.items = items;
    this.listeners.forEach((listener) => listener());
  }
}
