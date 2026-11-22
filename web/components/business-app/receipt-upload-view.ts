import type { TFunction } from "i18next";
import type { FailureClass } from "@/lib/failure-screen";
import type { ReceiptUpload, UploadProgress, UploadRejection } from "./receipt-upload-queue";

/** A file that started sending shows this much at once, so the bar is never an empty track. */
export const UPLOAD_START_PERCENT = 9;

/** What one row shows. Every stage is read from the queue's own item; only the start nudge is not bytes. */
export type UploadStage =
  | { kind: "waiting" }
  | { kind: "sending"; percent: number }
  /** Every byte is sent and the server has not answered yet. */
  | { kind: "saving" }
  | { kind: "saved"; replayed: boolean }
  | { kind: "deleted" }
  /** A failed upload: the bar stays at the share its last attempt really sent. */
  | { kind: "stopped"; percent: number; failure: FailureClass }
  | { kind: "rejected"; reason: UploadRejection };

export function uploadStage(item: ReceiptUpload, retryWaiting: boolean): UploadStage {
  switch (item.status) {
    case "queued":
      return { kind: "waiting" };
    case "uploading":
      if (item.bytes && item.bytes.total > 0 && item.bytes.sent >= item.bytes.total) return { kind: "saving" };
      return { kind: "sending", percent: Math.max(UPLOAD_START_PERCENT, Math.round(item.peak * 100)) };
    case "failed":
      return retryWaiting ? { kind: "waiting" } : { kind: "stopped", percent: Math.round(item.share * 100), failure: item.failure };
    case "saved":
      return item.receipt.deleted ? { kind: "deleted" } : { kind: "saved", replayed: item.receipt.replayed === true };
    case "rejected":
      return { kind: "rejected", reason: item.reason };
  }
}

/** The X shows only on a file that is not being sent and is not saved. */
export function uploadRemovable(stage: UploadStage): boolean {
  return stage.kind === "waiting" || stage.kind === "stopped" || stage.kind === "rejected";
}

/**
 * A batch read for attention: files that need the owner first, then the one
 * uploading, then the ones waiting, then the saved ones. The share and time
 * left cover the bytes still to send at the current file's rate.
 */
export function uploadBatchView(entries: readonly ReceiptUpload[], retryWaiting: (key: string) => boolean) {
  const attention = entries.filter((item) => item.status === "rejected" || (item.status === "failed" && !retryWaiting(item.key)));
  const active = entries.filter((item) => item.status === "uploading");
  const waiting = entries.filter((item) => item.status === "queued" || (item.status === "failed" && retryWaiting(item.key)));
  const completed = entries.filter((item) => item.status === "saved");
  const saved = completed.filter(item => !item.receipt.deleted);
  const deleted = completed.filter(item => item.receipt.deleted);
  const bytesOf = (items: readonly ReceiptUpload[]) => items.reduce((sum, item) => sum + item.file.size, 0);
  const sending = active.reduce((sum, item) => sum + (item.status === "uploading" && item.bytes ? item.bytes.sent : 0), 0);
  const total = bytesOf([...active, ...waiting, ...completed]);
  const done = bytesOf(completed) + sending;
  const rate = active.flatMap((item) => (item.status === "uploading" && item.bytes?.bytesPerSecond ? [item.bytes.bytesPerSecond] : []))[0] ?? null;
  const remaining = total - done;
  return {
    attention,
    active,
    waiting,
    saved,
    deleted,
    /** Something is being sent or waits its turn; a failed file that nobody retried is not busy. */
    busy: active.length > 0 || waiting.length > 0,
    share: total > 0 ? Math.min(1, done / total) : 0,
    secondsLeft: rate ? Math.ceil(remaining / rate) : null,
  };
}

export type UploadBatch = ReturnType<typeof uploadBatchView>;

/**
 * The batch in one line, for the panel's header and for the chip that stands in for the closed panel. Both read
 * the same counts; only the words for the running and the saved part differ.
 */
export function uploadSummaryText(t: TFunction, batch: UploadBatch, progress: UploadProgress | null, place: "panel" | "chip"): string {
  const running = place === "panel" ? "business.intake.uploading_progress" : "business.intake.chip_uploading";
  const saved = place === "panel" ? "business.intake.summary_saved" : "business.intake.chip_saved";
  return [
    progress ? t(running, { position: progress.position, total: progress.total }) : null,
    !progress && batch.saved.length > 0 ? t(saved, { count: batch.saved.length }) : null,
    batch.deleted.length > 0 ? t("business.document_delete.upload_deleted_count", { count: batch.deleted.length }) : null,
    batch.attention.length > 0 ? t("business.intake.summary_failed", { count: batch.attention.length }) : null,
  ].filter(Boolean).join(" · ");
}

/** The time left in round words. It says nothing until the queue has an honest rate. */
export function uploadTimeLeftText(t: TFunction, batch: UploadBatch, secondsLeft: number | null): string | null {
  if (batch.share >= 1) return t("business.intake.time_finishing");
  if (secondsLeft === null) return null;
  if (secondsLeft <= 10) return t("business.intake.time_seconds");
  if (secondsLeft < 60) return t("business.intake.time_under_minute");
  return t("business.intake.row_minutes_left", { count: Math.ceil(secondsLeft / 60) });
}
