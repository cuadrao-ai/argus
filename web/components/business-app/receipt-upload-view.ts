import type { TFunction } from "i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import type { FailureClass } from "@/lib/failure-screen";
import type { ReceiptUpload, UploadRejection } from "./receipt-upload-queue";

/**
 * What one row shows. Every stage is read from the queue's own item, and every number in it is bytes the
 * browser reported as sent, rounded down. A stage with no measured byte carries no number.
 */
export type UploadStage =
  | { kind: "waiting" }
  /** The file is being sent and no byte of this attempt is measured yet. */
  | { kind: "starting" }
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
      if (!item.bytes || item.bytes.total <= 0 || item.bytes.sent <= 0) return { kind: "starting" };
      if (item.bytes.sent >= item.bytes.total) return { kind: "saving" };
      return { kind: "sending", percent: Math.floor((item.bytes.sent * 100) / item.bytes.total) };
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

/** Identical bytes under two file names are one receipt on the server: each receipt once, in first order. */
function receiptsOf(items: readonly { receipt: ReceiptSummary }[]): ReceiptSummary[] {
  const byId = new Map<string, ReceiptSummary>();
  for (const { receipt } of items) if (!byId.has(receipt.id)) byId.set(receipt.id, receipt);
  return [...byId.values()];
}

/**
 * A batch read for attention: files that need the owner first, then the one
 * uploading, then the ones waiting, then the saved ones. The share and time
 * left cover the bytes still to send at the current file's rate, and are null
 * until a byte is measured. `saved` and `deleted` are files, one row each;
 * `savedReceipts` and `deletedReceipts` are the documents they became, which
 * every count and the review list read.
 */
export function uploadBatchView(
  entries: readonly ReceiptUpload[],
  retryWaiting: (key: string) => boolean,
  attempts: Iterable<Pick<ReceiptUpload, "key" | "target" | "grant">> = [],
) {
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
  const busy = active.length > 0 || waiting.length > 0;
  const targets = new Set(entries.map(item => item.target));
  // A retry keeps its key. A file can already have been attempted and be waiting again.
  const tried = new Set(active.map(item => item.key));
  for (const item of attempts) {
    if (item.grant === entries[0]?.grant && targets.has(item.target)) tried.add(item.key);
  }
  const next = active[0] ?? waiting[0];
  const position = tried.size + (next && !tried.has(next.key) ? 1 : 0);
  const progress = busy ? { position, total: new Set([...tried, ...waiting.map(item => item.key)]).size } : null;
  const bytes = active[0]?.bytes;
  const fileShare = progress ? (position - 1 + (bytes?.total ? Math.min(1, bytes.sent / bytes.total) : 0)) / progress.total : 0;
  const savedReceipts = receiptsOf(saved);
  const first = attention[0] ?? active[0] ?? waiting[0] ?? saved[0];
  const state: "uploading" | "failed" | "saved" | "idle" = progress ? "uploading" : attention.length ? "failed" : savedReceipts.length ? "saved" : "idle";
  return {
    attention,
    active,
    waiting,
    saved,
    deleted,
    savedReceipts,
    lastSavedAt: saved.reduce((latest, item) => Math.max(latest, item.savedAt ?? 0), 0),
    state,
    target: first?.target,
    progress,
    fileShare,
    deletedReceipts: receiptsOf(deleted),
    /** Something is being sent or waits its turn; a failed file that nobody retried is not busy. */
    busy,
    share: total > 0 && done > 0 ? Math.min(1, done / total) : null,
    secondsLeft: rate ? Math.ceil(remaining / rate) : null,
  };
}

export type UploadBatch = ReturnType<typeof uploadBatchView>;

/** The panel lists each outcome. The island names the batch's current state. */
export function uploadSummaryText(t: TFunction, batch: UploadBatch, place: "panel" | "composer" | "island"): string {
  const progress = place === "composer" ? null : batch.progress;
  if (place === "island") {
    if (progress) return t("business.intake.island_uploading", progress);
    if (batch.state === "failed") return t("business.intake.summary_failed", { count: batch.attention.length });
    if (batch.state === "saved") return t("business.intake.chip_saved", { count: batch.savedReceipts.length });
    return "";
  }
  return [
    progress ? t("business.intake.uploading_progress", progress) : null,
    !progress && batch.savedReceipts.length > 0 ? t("business.intake.summary_saved", { count: batch.savedReceipts.length }) : null,
    batch.deletedReceipts.length > 0 ? t("business.document_delete.upload_deleted_count", { count: batch.deletedReceipts.length }) : null,
    batch.attention.length > 0 ? t("business.intake.summary_failed", { count: batch.attention.length }) : null,
  ].filter(Boolean).join(" · ");
}

/** The time left in round words. It says nothing until the queue has an honest rate. */
export function uploadTimeLeftText(t: TFunction, batch: UploadBatch, secondsLeft: number | null): string | null {
  if (batch.share !== null && batch.share >= 1) return t("business.intake.time_finishing");
  if (secondsLeft === null) return null;
  if (secondsLeft <= 10) return t("business.intake.time_seconds");
  if (secondsLeft < 60) return t("business.intake.time_under_minute");
  return t("business.intake.row_minutes_left", { count: Math.ceil(secondsLeft / 60) });
}
