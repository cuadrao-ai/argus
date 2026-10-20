import type { ReceiptLimits, ReceiptSummary } from "@/lib/business-api";
import { classifyFailure, type FailureClass } from "@/lib/failure-screen";
import { randomId } from "@/lib/random-id";
import { receiptFileWithType } from "./receipt-file";
import { nextWaitingUpload, runFifo, waitingUploads } from "./receipt-upload-fifo";

/** Where a captured receipt goes next: its review, or the composer. */
export type IntakeTarget = "inbox" | "composer";
export type UploadRejection = "unsupported" | "too_large" | "heic";
export type UploadOrigin = { target: "inbox" } | { target: "composer"; conversationId: string | null };
/** Each file keeps the type picked when it was added, so one batch can mix receipts and sales; null lets the server detect it. */
type UploadFile = { key: string; file: File; documentType: DocumentType | null } & UploadOrigin;

/** A composer upload attaches only to the conversation it was added in. */
export function composerUploadDisposition(origin: UploadOrigin, current: { conversationId: string | null; intakeTarget: IntakeTarget | null }): "inbox" | "attach" | "attach_and_close" {
  if (origin.target !== "composer" || origin.conversationId !== current.conversationId) return "inbox";
  return current.intakeTarget === "composer" ? "attach_and_close" : "attach";
}

export type ReceiptUpload = UploadFile & (
  | { status: "queued" }
  | { status: "uploading"; consent: boolean; bytes: UploadBytes | null }
  | { status: "failed"; consent: boolean; failure: FailureClass }
  | { status: "saved"; consent: boolean; receipt: ReceiptSummary }
  | { status: "rejected"; reason: UploadRejection }
);

export type DocumentType = "recibo" | "venta";
/** How far one attempt has gone; the rate and `secondsLeft` are null until a second of sending makes them honest. */
export type UploadBytes = { sent: number; total: number; bytesPerSecond: number | null; secondsLeft: number | null };
type Upload = (file: File, consent: boolean, key: string, documentType: DocumentType | null, onProgress: (sent: number, total: number) => void) => Promise<ReceiptSummary>;

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
  /** Failed files whose retry was tapped while another drain ran; each goes once that drain ends. */
  private retryLater = new Map<string, IntakeTarget>();

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
  retryWaiting = (key: string) => this.retryLater.has(key);

  /** One tap retries a failed file with the same file and upload key; during a drain it waits its turn. */
  retry(key: string) {
    const item = this.items.find((candidate) => candidate.key === key && candidate.status === "failed");
    if (!item) return;
    if (this.running) {
      this.retryLater.set(key, item.target);
      this.publish([...this.items]);
      return;
    }
    void this.save(item.target, false, key);
  }

  private publish(items: readonly ReceiptUpload[]) {
    this.items = items;
    this.listeners.forEach((listener) => listener());
  }
  private replace(next: ReceiptUpload) {
    this.publish(this.items.map((item) => item.key === next.key ? next : item));
  }

  /** A file already in this target's list (same name, size and last change) is not added twice.
   *  A file added while a save is running joins the tail instead of being dropped. */
  add(files: readonly File[], limits: ReceiptLimits, target: IntakeTarget, conversationId: string | null = null, documentType: DocumentType | null = null): boolean {
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
      const base = { file, key: randomId(), documentType, ...origin };
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

  /** `only` limits this drain to one file key or a set of them; files added during the drain still join the tail. */
  async save(target: IntakeTarget, consent: boolean, only?: string | ReadonlySet<string>) {
    if (this.running) return;
    this.running = true;
    const included = (key: string) => only === undefined || (typeof only === "string" ? key === only : only.has(key));
    const presentAtStart = new Set(this.items.map((item) => item.key));
    const seeded = new Set(this.items.filter((item) => item.target === target &&
      included(item.key) && (item.status === "queued" || item.status === "failed")).map((item) => item.key));
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
          const uploading = { ...attempt, status: "uploading" as const };
          this.replace({ ...uploading, bytes: null });
          let painted = 0;
          const onProgress = (sent: number, total: number, startedAt: number) => {
            const now = Date.now();
            if (sent < total && now - painted < PROGRESS_REPAINT_MS) return;
            painted = now;
            this.replace({ ...uploading, bytes: { sent, total, bytesPerSecond: bytesPerSecond(sent, now - startedAt), secondsLeft: uploadSecondsLeft(sent, total, now - startedAt) } });
          };
          let receipt: ReceiptSummary;
          try {
            receipt = await this.uploadPastLimits(item.file, chosenConsent, item.key, item.documentType, onProgress);
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
      const next = this.retryLater.values().next();
      const keys = next.done ? null : new Set([...this.retryLater].filter(([, waiting]) => waiting === next.value).map(([key]) => key));
      keys?.forEach((key) => this.retryLater.delete(key));
      this.publish([...this.items]);
      if (keys && !next.done) void this.save(next.value, false, keys);
    }
  }

  private async uploadPastLimits(file: File, consent: boolean, key: string, documentType: DocumentType | null, onProgress: (sent: number, total: number, startedAt: number) => void): Promise<ReceiptSummary> {
    for (;;) {
      const startedAt = Date.now();
      try {
        return await this.upload(file, consent, key, documentType, (sent, total) => onProgress(sent, total, startedAt));
      } catch (error: unknown) {
        const waitMs = limitedFor(error);
        if (waitMs === null) throw error;
        await new Promise((resolve) => setTimeout(resolve, waitMs));
      }
    }
  }
}
