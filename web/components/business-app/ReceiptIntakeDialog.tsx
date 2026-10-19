"use client";

import ReceiptReadingControl from "./ReceiptReadingControl";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Camera, ClipboardPaste, FileUp, ReceiptText, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import type { ReceiptLimits, ReceiptSummary } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { primaryButtonClass, secondaryButtonClass } from "./business-ui";
import { Settle } from "./business-skeletons";
import { receiptFileAccept, receiptFormatLabels } from "./receipt-file";
import { ReceiptUploadQueue, isUnfinishedUpload, type IntakeTarget, type UploadRejection } from "./receipt-upload-queue";
import { readClipboardFile, useInputCapabilities } from "./useInputCapabilities";

export type { IntakeTarget } from "./receipt-upload-queue";

type IntakeProps = {
  target: IntakeTarget;
  queue: ReceiptUploadQueue;
  onClose: () => void;
  /** Every saved receipt of this target; one opens its review, several open the Inbox. */
  onReview: (receipts: ReceiptSummary[]) => void;
};

export default function ReceiptIntakeDialog({ target, ...props }: Omit<IntakeProps, "target"> & { target: IntakeTarget | null }) {
  if (!target) return null;
  return <IntakeSurface target={target} {...props} />;
}

function IntakeSurface(props: IntakeProps) {
  const { t } = useTranslation();
  const { records } = useBusiness();
  const limits = records.workspace?.receipt_limits;
  return limits ? (
    <IntakeForm limits={limits} {...props} />
  ) : (
    <AdaptivePanel title={t("business.intake.title", "Upload receipt")} closeLabel={t("common.close", "Close")} onClose={props.onClose} width="md">
      <div className="px-4 pb-4">
        <Settle pending layout="rows" rows={2} />
      </div>
    </AdaptivePanel>
  );
}

function IntakeForm({ limits, target, queue, onClose, onReview }: IntakeProps & { limits: ReceiptLimits }) {
  const { t, i18n } = useTranslation();
  const capabilities = useInputCapabilities();
  const { bridge } = useBusiness();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const replacingRef = useRef<string | null>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const entries = useSyncExternalStore(queue.subscribe, queue.snapshot, queue.snapshot).filter((item) => item.target === target);
  const consent = false;
  const [dragging, setDragging] = useState(false);
  const [clipboardEmpty, setClipboardEmpty] = useState(false);
  const uploading = queue.uploading;
  const pending = entries.some((item) => item.status === "queued" || item.status === "failed");
  const unfinished = entries.some(isUnfinishedUpload);
  const saved = entries.flatMap((item) => (item.status === "saved" ? [item.receipt] : []));
  const many = target === "inbox";
  const progress = many && queue.progress?.target === target ? queue.progress : null;

  const choose = (files: readonly File[]) => {
    setClipboardEmpty(false);
    queue.add(files, limits, target, bridge?.conversationId ?? null);
  };
  const chooseRef = useRef(choose);
  useEffect(() => {
    chooseRef.current = choose;
  });
  useEffect(() => {
    const onPaste = (event: ClipboardEvent) => {
      const files = Array.from(event.clipboardData?.files ?? []);
      if (files.length) {
        event.preventDefault();
        chooseRef.current(files);
      }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, []);

  const pasteFromClipboard = async () => {
    try {
      const pasted = await readClipboardFile(limits.media_types);
      if (pasted) choose([pasted]);
      else setClipboardEmpty(true);
    } catch {
      setClipboardEmpty(true);
    }
  };

  const sizeLabel = (bytes: number) =>
    new Intl.NumberFormat(i18n.resolvedLanguage ?? "en", { maximumFractionDigits: 1 }).format(bytes / 1024 / 1024);
  const formats = receiptFormatLabels(limits).join(", ");
  const rejectionText: Record<UploadRejection, string> = {
    unsupported: t("business.intake.unsupported", "This file isn't supported. Try {{formats}}.", { formats }),
    too_large: t("business.intake.too_large", "This file is larger than {{size}} MB. Use a smaller photo or PDF.", { size: sizeLabel(limits.max_bytes) }),
    heic: t("business.intake.heic", "This is an iPhone HEIC photo. Upload it from your iPhone's browser, which converts it, or export it as JPG first."),
  };
  const statusText: Record<string, string> = {
    queued: t("business.intake.queue_status.queued", "Ready to upload"),
    uploading: t("business.intake.queue_status.uploading", "Saving…"),
    saved: t("business.intake.queue_status.saved", "Saved to Inbox"),
    failed: t("business.intake.queue_status.failed", "Not saved. Try again."),
    rejected: t("business.intake.queue_status.rejected", "Cannot upload"),
  };

  return (
    <AdaptivePanel
      title={many ? t("business.intake.queue_title", "Upload receipts") : t("business.intake.title", "Upload receipt")}
      closeLabel={t("common.close", "Close")}
      onClose={onClose}
      width="md"
      footer={
        <div className="flex flex-wrap justify-end gap-2" data-testid="receipt-intake-footer">
          <button type="button" className={secondaryButtonClass} onClick={onClose}>
            {t("common.close", "Close")}
          </button>
          {saved.length > 0 && !unfinished && !uploading ? (
            <button type="button" className={primaryButtonClass} onClick={() => { queue.clear(target); onReview(saved); }}>
              {t("business.intake.review_saved", "Review saved receipts")}
            </button>
          ) : null}
          {pending || uploading ? (
            <button type="button" className={primaryButtonClass} disabled={uploading} onClick={() => void queue.save(target, consent)}>
              {progress ? t("business.intake.uploading_progress", "Uploading {{position}} of {{total}}…", { position: progress.position, total: progress.total }) : uploading ? t("business.intake.saving", "Saving…") : many ? t("business.intake.save_pending", "Save remaining files") : t("business.intake.save", "Save to Inbox")}
            </button>
          ) : null}
        </div>
      }
    >
      <div className="space-y-4 px-4 pb-6">
        <p className="text-[14px] text-black/60 dark:text-white/60">
          {t("business.intake.formats", "{{formats}}, up to {{size}} MB. The original stays private to you.", { formats, size: sizeLabel(limits.max_bytes) })}
        </p>

        <div
          onDragOver={(event) => {
            if (!capabilities.dragAndDrop) return;
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            if (!capabilities.dragAndDrop) return;
            event.preventDefault();
            setDragging(false);
            choose(Array.from(event.dataTransfer.files));
          }}
          className={`rounded-[16px] border border-dashed p-5 text-center transition-colors ${
            dragging ? "border-black/40 bg-black/[0.03] dark:border-white/40" : "border-black/15 dark:border-white/15"
          }`}
        >
          {capabilities.dragAndDrop ? (
            <p className="text-[14px] text-black/55 dark:text-white/55">
              {many ? t("business.intake.drop_multiple", "Drop your receipts here.") : t("business.intake.drop", "Drop a receipt here.")}
            </p>
          ) : null}
          <div className="mt-3 flex flex-wrap justify-center gap-2">
            <button type="button" className={secondaryButtonClass} onClick={() => { replacingRef.current = null; fileInputRef.current?.click(); }}>
              <FileUp className="h-4 w-4" />
              {many ? t("business.intake.choose_multiple", "Choose files") : t("business.intake.choose", "Choose file")}
            </button>
            {capabilities.clipboardRead ? (
              <button type="button" className={secondaryButtonClass} onClick={() => void pasteFromClipboard()}>
                <ClipboardPaste className="h-4 w-4" />
                {t("business.intake.paste", "Paste")}
              </button>
            ) : null}
            {capabilities.cameraCapture ? (
              <button type="button" className={secondaryButtonClass} onClick={() => cameraInputRef.current?.click()}>
                <Camera className="h-4 w-4" />
                {t("business.intake.camera", "Take photo")}
              </button>
            ) : null}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple={many}
            accept={receiptFileAccept(limits)}
            className="sr-only"
            tabIndex={-1}
            aria-hidden="true"
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []);
              if (files.length && replacingRef.current) queue.remove(replacingRef.current);
              replacingRef.current = null;
              choose(files);
              event.target.value = "";
            }}
          />
          <input
            ref={cameraInputRef}
            type="file"
            accept={limits.media_types.filter((type) => type.startsWith("image/")).join(",")}
            capture="environment"
            className="sr-only"
            tabIndex={-1}
            aria-hidden="true"
            onChange={(event) => {
              choose(Array.from(event.target.files ?? []));
              event.target.value = "";
            }}
          />
        </div>

        {clipboardEmpty ? (
          <p role="status" className="text-[14px] text-black/60 dark:text-white/60">
            {t("business.intake.clipboard_empty", "There's no receipt image or PDF to paste. Copy one first, or choose a file.")}
          </p>
        ) : null}

        {entries.length > 0 ? (
          <ul className="space-y-2" aria-live="polite" aria-label={t("business.intake.queue_title", "Upload receipts")} data-testid="receipt-upload-queue">
            {entries.map((item) => (
              <li key={item.key} className="rounded-xl border border-black/10 p-3 dark:border-white/15">
                <div className="flex items-center gap-2">
                  <ReceiptText className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span className="min-w-0 flex-1 break-words text-sm font-medium">{item.file.name}</span>
                  <span className="shrink-0 text-xs text-black/50 dark:text-white/50">{`${sizeLabel(item.file.size)} MB`}</span>
                  <button
                    type="button"
                    disabled={uploading}
                    onClick={() => queue.remove(item.key)}
                    aria-label={t("business.intake.remove_file", "Remove {{name}} from this upload list", { name: item.file.name })}
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full disabled:opacity-40"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <p className="text-sm text-black/60 dark:text-white/60">{item.status === "saved" && item.receipt.replayed ? t("business.intake.replayed", "Already saved before. This is that receipt.") : statusText[item.status]}</p>
                {item.status === "rejected" ? (
                  <div className="mt-2 space-y-2">
                    <p role="alert" className="text-sm text-[#a8434c] dark:text-[#ec9aa0]">{rejectionText[item.reason]}</p>
                    <button type="button" disabled={uploading} className={secondaryButtonClass} onClick={() => { replacingRef.current = item.key; fileInputRef.current?.click(); }}>
                      {t("business.intake.choose_another", "Choose another file")}
                    </button>
                  </div>
                ) : null}
                {item.status === "failed" ? (
                  <div className="mt-2 space-y-2">
                    <p role="alert" className="text-sm text-[#a8434c] dark:text-[#ec9aa0]">
                      {t("business.intake.failed", "We couldn't read the receipt. Try again.")}
                    </p>
                    <button type="button" disabled={uploading} className={secondaryButtonClass} onClick={() => void queue.save(target, consent, item.key)}>
                      {t("common.retry", "Retry")}
                    </button>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
        {entries.some((item) => item.status === "failed") ? (
          <p className="text-xs text-black/60 dark:text-white/60">{t("business.intake.retry_consent", "Retries keep the AI choice from the first attempt.")}</p>
        ) : null}

        <ReceiptReadingControl />
        {unfinished ? (
          <p className="text-xs text-black/60 dark:text-white/60">
            {t("business.intake.keep_open", "You can close this panel and come back to your uploads. Keep this page open until every file is saved.")}
          </p>
        ) : null}
      </div>
    </AdaptivePanel>
  );
}
