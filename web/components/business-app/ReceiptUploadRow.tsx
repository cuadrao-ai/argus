"use client";

import Image from "next/image";
import { useEffect, useState, type ReactNode } from "react";
import { Check, Clock, FileText, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { FailureClass } from "@/lib/failure-screen";
import type { ReceiptUpload } from "./receipt-upload-queue";
import { uploadRemovable, type UploadStage } from "./receipt-upload-view";
import styles from "./receipt-intake.module.css";

const MUTED = "text-[#56635e] dark:text-white/70";
const DANGER = "text-[#9e2f39] dark:text-[#ec9aa0]";
export const intakeLinkClass = "inline-flex min-h-10 shrink-0 items-center whitespace-nowrap rounded-item px-2.5 text-[13.5px] font-semibold text-[#245040] hover:bg-[#EEF3EF] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] disabled:opacity-40 dark:text-[#8fcbb0] dark:hover:bg-[#8fcbb0]/10";
/** Upload failures a tap on the row can fix; the rest have their own screen above the list. */
const ROW_RETRY: ReadonlySet<FailureClass> = new Set(["offline", "other", "server", "unavailable", "rate_limited"]);

/** A small preview of an image file; a PDF or other file shows its kind instead. */
function FileThumb({ file, bad }: { file: File; bad: boolean }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    if (!file.type.startsWith("image/") || typeof createImageBitmap === "undefined") return undefined;
    let live = true;
    createImageBitmap(file).then((bitmap) => {
      const scale = Math.min(1, 80 / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(bitmap.width * scale));
      canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      bitmap.close();
      if (live) setSrc(canvas.toDataURL("image/jpeg", 0.8));
    }).catch(() => undefined);
    return () => {
      live = false;
    };
  }, [file]);
  return (
    <span className={`flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-item ${bad ? "bg-[#f6dfe0] text-[#9e2f39] dark:bg-[#4a2a2f] dark:text-[#ec9aa0]" : "bg-[#F0EEE7] text-[#56635e] dark:bg-white/[0.06] dark:text-white/70"}`}>
      {src ? <Image unoptimized src={src} alt="" width={40} height={40} className="h-full w-full object-cover" /> : <FileText className="h-[18px] w-[18px]" aria-hidden="true" />}
    </span>
  );
}

/**
 * One file of the batch. `stage` is the queue's own state for it; the row adds no state of its own.
 * `problem` is the line a refused file shows; `restoreControl` is what a file deleted before offers.
 */
export default function ReceiptUploadRow({ item, stage, size, problem, restoreControl, onRemove, onRetry, onReplace }: {
  item: ReceiptUpload;
  stage: UploadStage;
  size: string;
  problem: string | null;
  restoreControl: ReactNode;
  onRemove: () => void;
  onRetry: () => void;
  onReplace: () => void;
}) {
  const { t } = useTranslation();
  const name = item.file.name;
  const bad = stage.kind === "stopped" || stage.kind === "rejected";
  // A picked type shows at once; a detected one only once the server has read it.
  const shownType = item.documentType ?? (item.status === "saved" ? item.receipt.document_type ?? "recibo" : null);
  const error = stage.kind === "rejected"
    ? problem
    : stage.kind === "stopped"
      ? stage.failure === "offline" ? t("business.intake.row_failed_offline") : t("business.intake.row_failed")
      : null;
  const detail = stage.kind === "deleted"
    ? t("business.document_delete.upload_deleted")
    : stage.kind === "saved" && stage.replayed
      ? t("business.intake.replayed")
      : [size, shownType ? t(shownType === "venta" ? "business.intake.type_venta" : "business.intake.type_recibo") : null].filter(Boolean).join(" · ");
  return (
    <li data-testid="receipt-upload-row" data-status={item.status} data-stage={stage.kind} className="grid min-h-[60px] grid-cols-[40px_minmax(0,1fr)_auto_40px] items-center gap-x-3 border-b border-[#ECEAE3] py-2 last:border-b-0 dark:border-white/[0.07]">
      <FileThumb file={item.file} bad={bad} />
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="truncate text-[14px] font-medium text-[#172b26] dark:text-white" title={name}>{name}</span>
        {error
          ? <span role="alert" className={`text-[12.5px] leading-[17px] ${DANGER}`}>{error}</span>
          : <span data-testid="receipt-upload-detail" className={`text-[12.5px] leading-[17px] tabular-nums ${MUTED}`}>{detail}</span>}
      </span>
      <span className={`flex items-center justify-end gap-2 tablet:min-w-[140px] text-[13px] font-medium tabular-nums ${stage.kind === "saved" ? "text-[#2f5a49] dark:text-[#8fcbb0]" : MUTED}`}>
        {stage.kind === "waiting" ? <><Clock className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />{t("business.intake.row_waiting")}</> : null}
        {stage.kind === "starting" ? <span className={`${styles.bar} ${styles.unknown} rounded-full`} role="progressbar" aria-label={t("business.intake.row_uploading", { name })} aria-busy="true"><i /></span> : null}
        {stage.kind === "sending" ? <>
          <span className={`${styles.bar} ${styles.striped} rounded-full`} role="progressbar" aria-label={t("business.intake.row_uploading", { name })} aria-valuemin={0} aria-valuemax={100} aria-valuenow={stage.percent}><i style={{ width: `${stage.percent}%` }} /></span>
          <span className="min-w-[34px] text-right">{t("business.intake.row_percent", { percent: stage.percent })}</span>
        </> : null}
        {stage.kind === "saving" ? <><span className={`${styles.bar} ${styles.unknown} rounded-full`} aria-hidden="true"><i /></span>{t("business.intake.row_saving")}</> : null}
        {stage.kind === "saved" ? <><Check className={`h-4 w-4 shrink-0 ${styles.pop}`} strokeWidth={2.2} aria-hidden="true" />{t("business.intake.row_saved")}</> : null}
        {stage.kind === "deleted" ? restoreControl : null}
        {stage.kind === "stopped" ? <>
          <span className={`${styles.bar} ${styles.frozen} rounded-full`} role="img" aria-label={t("business.intake.row_stopped_at", { percent: stage.percent })}><i style={{ width: `${stage.percent}%` }} /></span>
          {ROW_RETRY.has(stage.failure) ? <button type="button" className={intakeLinkClass} aria-label={t("business.intake.retry_file", { name })} onClick={onRetry}>{t("common.retry")}</button> : null}
        </> : null}
        {stage.kind === "rejected" ? <button type="button" className={intakeLinkClass} onClick={onReplace}>{t("business.intake.choose_another")}</button> : null}
      </span>
      <span>
        {uploadRemovable(stage) ? (
          <button type="button" onClick={onRemove} aria-label={t("business.intake.remove_file", { name })} className={`flex h-9 w-9 items-center justify-center rounded-item hover:bg-[#F0EEE7] hover:text-[#172b26] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:hover:bg-white/[0.06] dark:hover:text-white ${MUTED}`}>
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        ) : null}
      </span>
    </li>
  );
}
