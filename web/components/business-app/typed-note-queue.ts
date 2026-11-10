import { randomId } from "@/lib/random-id";
import { captureOutcomeUnknown } from "./ManualCaptureDialog";
import type { DocumentType } from "./receipt-upload-queue";

/**
 * Text the owner typed instead of uploading a file; it becomes a Bandeja draft like any receipt. It keeps the
 * Business it was typed in, and every save and retry carries that Business, whatever is chosen when it is sent.
 */
export type TypedNote = { key: string; grant: string | null; text: string; documentType: DocumentType; status: "saving" | "saved" | "uncertain" | "refused" };
type Capture = (input: { text: string; document_type: DocumentType }, key: string, grant: string | null) => Promise<unknown>;

/**
 * Owned by one mounted business workspace, like the upload queue, so closing Agregar never drops a note whose
 * save is running or unconfirmed. A retry repeats the note's one key, so it is never saved twice.
 */
export class TypedNoteQueue {
  private items: readonly TypedNote[] = [];
  private listeners = new Set<() => void>();

  constructor(private onSaved: () => void) {}

  snapshot = () => this.items;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  add(note: Pick<TypedNote, "grant" | "text" | "documentType">, capture: Capture) {
    const entry: TypedNote = { ...note, key: randomId(), status: "saving" };
    this.publish([entry, ...this.items]);
    return this.send(entry, capture);
  }

  retry(key: string, capture: Capture) {
    const entry = this.items.find((item) => item.key === key);
    return entry?.status === "uncertain" ? this.send(entry, capture) : Promise.resolve();
  }

  /** Closing Agregar forgets what is finished; a note still saving or unconfirmed stays for its retry. */
  clearSettled() {
    this.publish(this.items.filter((item) => item.status === "saving" || item.status === "uncertain"));
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
