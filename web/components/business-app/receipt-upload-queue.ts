import type { ReceiptLimits, ReceiptSummary } from "@/lib/business-api";
import { enteredIn } from "@/lib/business-grant";
import { classifyFailure, type FailureClass } from "@/lib/failure-screen";
import { randomId } from "@/lib/random-id";
import { receiptFileWithType } from "./receipt-file";
import { runFifo } from "./receipt-upload-fifo";

/** Where a captured receipt goes next: its review, or the composer. */
export type IntakeTarget = "inbox" | "composer";
export type UploadRejection = "unsupported" | "too_large" | "heic";
export type UploadOrigin = { target: "inbox" } | { target: "composer"; conversationId: string | null };
/**
 * Each file keeps the type picked when it was added, so one batch can mix receipts and sales; null lets the server
 * detect it. It also keeps the Business it was added in, so a file sent or retried after a switch still lands there.
 */
type UploadFile = { key: string; file: File; documentType: DocumentType | null; grant: string | null } & UploadOrigin;

/** A composer upload attaches only to the conversation it was added in. */
export function composerUploadDisposition(origin: UploadOrigin, current: { conversationId: string | null; intakeTarget: IntakeTarget | null }): "inbox" | "attach" | "attach_and_close" {
  if (origin.target !== "composer" || origin.conversationId !== current.conversationId) return "inbox";
  return current.intakeTarget === "composer" ? "attach_and_close" : "attach";
}

export type ReceiptUpload = UploadFile & (
  | { status: "queued" }
  | { status: "uploading"; consent: boolean; bytes: UploadBytes | null; peak: number }
  | { status: "failed"; consent: boolean; failure: FailureClass; share: number }
  | { status: "saved"; consent: boolean; receipt: ReceiptSummary }
  | { status: "rejected"; reason: UploadRejection }
);

export type DocumentType = "recibo" | "venta";
/**
 * `peak` is the furthest share (0 to 1) any attempt of this turn reached, so a bar never moves back when the upload
 * limit makes the file send again. A failed file keeps `share`, the share its last attempt had really sent.
 */
/** How far one attempt has gone; the rate and `secondsLeft` are null until a second of sending makes them honest. */
export type UploadBytes = { sent: number; total: number; bytesPerSecond: number | null; secondsLeft: number | null };
type Upload = (file: File, consent: boolean, key: string, documentType: DocumentType | null, onProgress: (sent: number, total: number) => void, grant: string | null) => Promise<ReceiptSummary>;

/** A row repaints at most this often while bytes move. */
const PROGRESS_REPAINT_MS = 100;

/** Seconds left at the rate so far; null until a second of sending gives an honest rate. */
export function uploadSecondsLeft(sent: number, total: number, elapsedMs: number): number | null {
  if (elapsedMs < 1_000 || sent <= 0) return null;
  return Math.max(0, Math.ceil(((total - sent) * elapsedMs) / sent / 1_000));
}

function bytesPerSecond(sent: number, elapsedMs: number): number | null {
  return elapsedMs < 1_000 || sent <= 0 ? null : (sent * 1_000) / elapsedMs;
}
/** Where the file stands among its target's files in the running drain: "Subiendo 6 de 9". */
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
 * hidden. One drain sends files one at a time in arrival order, whatever
 * their target: every queued file, and every failed file whose retry was
 * asked for. It ends only when nothing waits, so a file added or retried
 * while it runs is never left behind. Each file keeps one upload key, so a
 * retry never saves it twice, and one file's failure never blocks its
 * siblings. The upload limit (429) is not a failure: the drain waits out
 * Retry-After and sends the same file again.
 */
export class ReceiptUploadQueue {
  private items: readonly ReceiptUpload[] = [];
  private listeners = new Set<() => void>();
  private running = false;
  private current: UploadProgress | null = null;
  /** Files asked to upload and not yet taken by the drain, with the consent they were asked with. */
  private asked = new Map<string, boolean>();

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
  /** Whether this failed file's retry waits for the running drain. */
  retryWaiting = (key: string) => this.asked.has(key) && this.items.some((item) => item.key === key && item.status === "failed");

  /** One tap retries a failed file with the same file, upload key and consent; during a drain it waits its turn. */
  retry(key: string) {
    this.retryWhere((item) => item.key === key);
  }

  /** The connection is back: every file it stopped goes again, as if each had been tapped. */
  retryOffline() {
    this.retryWhere((item) => item.status === "failed" && item.failure === "offline");
  }

  private retryWhere(chosen: (item: ReceiptUpload) => boolean) {
    let asked = false;
    for (const item of this.items) {
      if (item.status !== "failed" || !chosen(item)) continue;
      this.asked.set(item.key, item.consent);
      asked = true;
    }
    if (!asked) return;
    this.publish([...this.items]);
    void this.drain();
  }

  updateReceipt(receipt: ReceiptSummary) {
    this.publish(this.items.map(item => item.status === "saved" && item.receipt.id === receipt.id ? { ...item, receipt } : item));
  }

  private waiting = (item: ReceiptUpload) => item.status === "queued" || (item.status === "failed" && this.asked.has(item.key));

  private publish(items: readonly ReceiptUpload[]) {
    this.items = items;
    this.listeners.forEach((listener) => listener());
  }
  private replace(next: ReceiptUpload) {
    this.publish(this.items.map((item) => item.key === next.key ? next : item));
  }

  /** One Business's files for one target: the queue holds every Business's files, and an action in one touches only its own. */
  private within(target: IntakeTarget, grant: string | null) {
    const entered = enteredIn(grant);
    return (item: ReceiptUpload) => item.target === target && entered(item);
  }

  /** A file already in this Business's list for the target (same name, size and last change) is not added twice.
   *  A file added while a save is running joins the tail instead of being dropped. */
  add(files: readonly File[], limits: ReceiptLimits, target: IntakeTarget, conversationId: string | null = null, documentType: DocumentType | null = null, grant: string | null = null): boolean {
    const selected = target === "composer" ? files.slice(0, 1) : files;
    if (!selected.length) return true;
    const identity = (file: File) => `${file.name}\u0000${file.size}\u0000${file.lastModified}`;
    const own = this.within(target, grant);
    const known = new Set(this.items.filter(own).map((item) => identity(item.file)));
    const fresh = selected.filter((candidate) => {
      if (known.has(identity(candidate))) return false;
      known.add(identity(candidate));
      return true;
    });
    if (!fresh.length) return true;
    const incoming: ReceiptUpload[] = fresh.map((candidate) => {
      const file = receiptFileWithType(candidate, limits);
      const origin: UploadOrigin = target === "composer" ? { target, conversationId } : { target };
      const base = { file, key: randomId(), documentType, grant, ...origin };
      const reason = rejectionFor(file, limits);
      return reason ? { ...base, status: "rejected", reason } : { ...base, status: "queued" };
    });
    const idleComposer = target === "composer" && !this.running;
    this.publish([...(idleComposer ? this.items.filter((item) => !own(item)) : this.items), ...incoming]);
    return true;
  }

  /** Forgets what is finished, once it is reviewed; queued, running and failed files stay. */
  clearSettled(target: IntakeTarget, grant: string | null) {
    const own = this.within(target, grant);
    if (!this.running) this.publish(this.items.filter((item) => !own(item) || isUnfinishedUpload(item)));
  }

  /** A file that waits, failed or was refused leaves the list, during a drain too; the one being sent stays. */
  remove(key: string) {
    if (this.items.some((item) => item.key === key && item.status === "uploading")) return;
    this.asked.delete(key);
    this.publish(this.items.filter((item) => item.key !== key));
  }

  clear(target: IntakeTarget, grant: string | null) {
    const own = this.within(target, grant);
    if (!this.running) this.publish(this.items.filter((item) => !own(item)));
  }

  /** Uploads every queued file, and the failed files of `target` that `only` names (all of them when it is omitted). */
  save(target: IntakeTarget, consent: boolean, only?: string | ReadonlySet<string>) {
    const included = (key: string) => only === undefined || (typeof only === "string" ? key === only : only.has(key));
    for (const item of this.items) {
      if (item.target !== target || !included(item.key) || this.asked.has(item.key)) continue;
      if (item.status === "queued") this.asked.set(item.key, consent);
      else if (item.status === "failed") this.asked.set(item.key, item.consent);
    }
    return this.drain();
  }

  private async drain() {
    if (this.running) return;
    this.running = true;
    const sentBy = new Map<IntakeTarget, number>();
    try {
      await runFifo(
        () => this.items.find(this.waiting),
        async (item) => {
          const consent = this.asked.get(item.key) ?? false;
          this.asked.delete(item.key);
          const position = (sentBy.get(item.target) ?? 0) + 1;
          sentBy.set(item.target, position);
          const remaining = this.items.filter((other) => other.key !== item.key && other.target === item.target && this.waiting(other)).length;
          this.current = { target: item.target, position, total: position + remaining };
          const attempt = { ...item, consent };
          const uploading = { ...attempt, status: "uploading" as const };
          this.replace({ ...uploading, bytes: null, peak: 0 });
          let painted = 0;
          let share = 0;
          let peak = 0;
          const onProgress = (sent: number, total: number, startedAt: number) => {
            share = total > 0 ? Math.min(1, sent / total) : 0;
            peak = Math.max(peak, share);
            const now = Date.now();
            // The first and the last report of an attempt always show; the ones between repaint at most so often.
            if (sent > 0 && sent < total && now - painted < PROGRESS_REPAINT_MS) return;
            painted = now;
            this.replace({ ...uploading, peak, bytes: { sent, total, bytesPerSecond: bytesPerSecond(sent, now - startedAt), secondsLeft: uploadSecondsLeft(sent, total, now - startedAt) } });
          };
          let receipt: ReceiptSummary;
          try {
            receipt = await this.uploadPastLimits(item, consent, onProgress);
          } catch (error: unknown) {
            if (error instanceof Error && "status" in error && error.status === 415) {
              this.replace({ ...item, status: "rejected", reason: "unsupported" });
            } else {
              const online = typeof navigator === "undefined" ? true : navigator.onLine;
              this.replace({
                ...attempt,
                status: "failed",
                failure: classifyFailure(error, { fetch: true, online }),
                share,
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
    // Something asked to upload in the moment between the last file and the end of the drain still goes.
    if (this.items.some(this.waiting)) await this.drain();
  }

  private async uploadPastLimits(item: UploadFile, consent: boolean, onProgress: (sent: number, total: number, startedAt: number) => void): Promise<ReceiptSummary> {
    for (;;) {
      const startedAt = Date.now();
      // Each attempt starts from nothing sent, so a failure reports this attempt's share, not an earlier one's.
      onProgress(0, item.file.size, startedAt);
      try {
        return await this.upload(item.file, consent, item.key, item.documentType, (sent, total) => onProgress(sent, total, startedAt), item.grant);
      } catch (error: unknown) {
        const waitMs = limitedFor(error);
        if (waitMs === null) throw error;
        await new Promise((resolve) => setTimeout(resolve, waitMs));
      }
    }
  }
}
