import type { ReceiptLimits, ReceiptSummary } from "@/lib/business-api";
import { classifyFailure, type FailureClass } from "@/lib/failure-screen";
import { randomId } from "@/lib/random-id";
import { receiptFileWithType } from "./receipt-file";
import { nextWaitingUpload, runFifo, waitingUploads } from "./receipt-upload-fifo";

/** Where a captured receipt goes next: its review, or the composer. */
export type IntakeTarget = "inbox" | "composer";
export type UploadRejection = "unsupported" | "too_large" | "heic";
export type UploadOrigin = { target: "inbox" } | { target: "composer"; conversationId: string | null };
type UploadFile = { key: string; file: File } & UploadOrigin;

/** A composer upload attaches only to the conversation it was added in. */
export function composerUploadDisposition(origin: UploadOrigin, current: { conversationId: string | null; intakeTarget: IntakeTarget | null }): "inbox" | "attach" | "attach_and_close" {
  if (origin.target !== "composer" || origin.conversationId !== current.conversationId) return "inbox";
  return current.intakeTarget === "composer" ? "attach_and_close" : "attach";
}

export type ReceiptUpload = UploadFile & (
  | { status: "queued" }
  | { status: "uploading"; consent: boolean }
  | { status: "failed"; consent: boolean; failure: FailureClass }
  | { status: "saved"; consent: boolean; receipt: ReceiptSummary }
  | { status: "rejected"; reason: UploadRejection }
);

type Upload = (file: File, consent: boolean, key: string) => Promise<ReceiptSummary>;
/** Where the file stands in the running drain: "Subiendo 6 de 9". */
export type UploadProgress = { target: IntakeTarget; position: number; total: number };

/** The wait after a 429 that names no Retry-After. */
const UPLOAD_LIMIT_FALLBACK_MS = 5_000;

function limitedFor(error: unknown): number | null {
  if (!(error instanceof Error) || !("status" in error) || error.status !== 429) return null;
  const after = "retryAfterMs" in error ? error.retryAfterMs : null;
  return typeof after === "number" ? after : UPLOAD_LIMIT_FALLBACK_MS;
}
export const isUnfinishedUpload = (item: ReceiptUpload) =>
  item.status === "queued" || item.status === "uploading" || item.status === "failed";

function rejectionFor(file: File, limits: ReceiptLimits): UploadRejection | null {
  const type = file.type.split(";", 1)[0].trim().toLowerCase();
  if (type === "image/heic" || type === "image/heif" || /\.hei[cf]$/i.test(file.name)) return "heic";
  if (!limits.media_types.includes(type)) return "unsupported";
  if (file.size > limits.max_bytes) return "too_large";
  return null;
}

/**
 * Owned by one mounted business workspace, including while its dialog is
 * hidden. Each file keeps one upload key, so a retry never saves it twice,
 * and one file's failure never blocks its siblings. The upload limit (429)
 * is not a failure: the drain waits out Retry-After and sends the same file again.
 */
export class ReceiptUploadQueue {
  private items: readonly ReceiptUpload[] = [];
  private listeners = new Set<() => void>();
  private running = false;
  private current: UploadProgress | null = null;

  constructor(private upload: Upload, private onSaved: (receipt: ReceiptSummary, origin: UploadOrigin) => void) {}

  setOnSaved(listener: (receipt: ReceiptSummary, origin: UploadOrigin) => void) { this.onSaved = listener; }

  snapshot = () => this.items;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  get uploading() { return this.running; }
  get progress() { return this.current; }
  get unfinished() { return this.items.some(isUnfinishedUpload); }

  private publish(items: readonly ReceiptUpload[]) {
    this.items = items;
    this.listeners.forEach((listener) => listener());
  }
  private replace(next: ReceiptUpload) {
    this.publish(this.items.map((item) => item.key === next.key ? next : item));
  }

  /** A file already in this target's list (same name, size and last change) is not added twice.
   *  A file added while a save is running joins the tail instead of being dropped. */
  add(files: readonly File[], limits: ReceiptLimits, target: IntakeTarget, conversationId: string | null = null): boolean {
    const selected = target === "composer" ? files.slice(0, 1) : files;
    if (!selected.length) return true;
    const identity = (file: File) => `${file.name}\u0000${file.size}\u0000${file.lastModified}`;
    const known = new Set(this.items.filter((item) => item.target === target).map((item) => identity(item.file)));
    const fresh = selected.filter((candidate) => {
      if (known.has(identity(candidate))) return false;
      known.add(identity(candidate));
      return true;
    });
    if (!fresh.length) return true;
    const incoming: ReceiptUpload[] = fresh.map((candidate) => {
      const file = receiptFileWithType(candidate, limits);
      const origin: UploadOrigin = target === "composer" ? { target, conversationId } : { target };
      const base = { file, key: randomId(), ...origin };
      const reason = rejectionFor(file, limits);
      return reason ? { ...base, status: "rejected", reason } : { ...base, status: "queued" };
    });
    const idleComposer = target === "composer" && !this.running;
    this.publish([...(idleComposer ? this.items.filter((item) => item.target !== target) : this.items), ...incoming]);
    return true;
  }

  /** Closing the dialog forgets what is finished; queued, running and failed files stay. */
  clearSettled(target: IntakeTarget) {
    if (!this.running) this.publish(this.items.filter((item) => item.target !== target || isUnfinishedUpload(item)));
  }

  remove(key: string) {
    if (!this.running) this.publish(this.items.filter((item) => item.key !== key));
  }

  clear(target: IntakeTarget) {
    if (!this.running) this.publish(this.items.filter((item) => item.target !== target));
  }

  async save(target: IntakeTarget, consent: boolean, onlyKey?: string) {
    if (this.running) return;
    this.running = true;
    const presentAtStart = new Set(this.items.map((item) => item.key));
    const seeded = new Set(this.items.filter((item) => item.target === target &&
      (!onlyKey || item.key === onlyKey) && (item.status === "queued" || item.status === "failed")).map((item) => item.key));
    const attempted = new Set<string>();
    try {
      await runFifo(
        () => nextWaitingUpload(this.items, target, attempted, seeded, presentAtStart),
        async (item) => {
          attempted.add(item.key);
          const remaining = waitingUploads(this.items, target, attempted, seeded, presentAtStart).length;
          this.current = { target, position: attempted.size, total: attempted.size + remaining };
          const chosenConsent = item.status === "failed" ? item.consent : consent;
          const attempt = { ...item, consent: chosenConsent };
          this.replace({ ...attempt, status: "uploading" });
          let receipt: ReceiptSummary;
          try {
            receipt = await this.uploadPastLimits(item.file, chosenConsent, item.key);
          } catch (error: unknown) {
            if (error instanceof Error && "status" in error && error.status === 415) {
              this.replace({ ...item, status: "rejected", reason: "unsupported" });
            } else {
              const online = typeof navigator === "undefined" ? true : navigator.onLine;
              this.replace({
                ...attempt,
                status: "failed",
                failure: classifyFailure(error, { fetch: true, online }),
              });
            }
            return;
          }
          this.replace({ ...attempt, status: "saved", receipt });
          this.onSaved(receipt, item);
        },
      );
    } finally {
      this.running = false;
      this.current = null;
      this.publish([...this.items]);
    }
  }

  private async uploadPastLimits(file: File, consent: boolean, key: string): Promise<ReceiptSummary> {
    for (;;) {
      try {
        return await this.upload(file, consent, key);
      } catch (error: unknown) {
        const waitMs = limitedFor(error);
        if (waitMs === null) throw error;
        await new Promise((resolve) => setTimeout(resolve, waitMs));
      }
    }
  }
}
