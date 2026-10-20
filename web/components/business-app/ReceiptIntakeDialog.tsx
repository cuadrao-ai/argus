"use client";

import ReceiptReadingControl from "./ReceiptReadingControl";

import Image from "next/image";
import { useEffect, useRef, useState, useSyncExternalStore, type DragEvent } from "react";
import { Camera, ChevronDown, ChevronRight, CircleAlert, CircleCheck, Clock, FileText, FolderOpen, FileUp, Mail, RotateCw, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { BusinessClosedNotice } from "@/components/status/BusinessClosedNotice";
import { RemovedMemberScreen } from "@/components/status/RemovedMemberScreen";
import { ServerErrorScreen } from "@/components/status/ServerErrorScreen";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { referenceCode, sessionEndedLoginPath, type FailureClass } from "@/lib/failure-screen";
import type { ReceiptLimits, ReceiptSummary } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { pillButtonClass, primaryButtonClass, secondaryButtonClass } from "./business-ui";
import { Settle } from "./business-skeletons";
import { receiptFileAccept, receiptFormatLabel, receiptFormatLabels } from "./receipt-file";
import { ReceiptUploadQueue, isUnfinishedUpload, type DocumentType, type IntakeTarget, type ReceiptUpload, type UploadRejection } from "./receipt-upload-queue";
import { CopyButton, WrappingAddress, useCopyLabels } from "./foundation/CopyButton";
import { useForwardAddress } from "./useForwardAddress";
import { useInputCapabilities } from "./useInputCapabilities";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";

export type { IntakeTarget } from "./receipt-upload-queue";

type IntakeProps = {
  target: IntakeTarget;
  queue: ReceiptUploadQueue;
  onClose: () => void;
  /** Every saved receipt of this target; one opens its review, several open the Inbox. */
  onReview: (receipts: ReceiptSummary[]) => void;
};

/** What a file dragged over the drop zone would do: nothing yet, upload, or be refused. */
type DragState = { kind: "idle" } | { kind: "accept"; count: number } | { kind: "reject" };

const MUTED = "text-[#56635e] dark:text-white/70";
const DANGER = "text-[#9e2f39] dark:text-[#ec9aa0]";
const smallAction = "inline-flex min-h-11 items-center gap-1.5 rounded-full px-3.5 text-[14px] font-medium text-[#2f5a49] hover:bg-[#2f5a49]/[0.06] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] disabled:opacity-40 dark:text-[#8fcbb0]";
/** Upload failures a tap on the row can fix; the rest have their own screen above the list. */
const ROW_RETRY: ReadonlySet<FailureClass> = new Set(["offline", "other", "server", "unavailable", "rate_limited"]);

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

function dragStateFor(event: DragEvent, limits: ReceiptLimits): DragState {
  const files = Array.from(event.dataTransfer.items ?? []).filter((item) => item.kind === "file");
  if (!files.length) return { kind: "idle" };
  const known = (type: string) => !type || (limits.media_types.includes(type) && type !== "image/heic" && type !== "image/heif");
  return files.every((item) => known(item.type.toLowerCase())) ? { kind: "accept", count: files.length } : { kind: "reject" };
}

function IntakeForm({ limits, target, queue, onClose, onReview }: IntakeProps & { limits: ReceiptLimits }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "es-419";
  const capabilities = useInputCapabilities();
  const { isBelowTablet } = useResponsiveLayout();
  /** The photo row is for phones: a camera, file capture and a phone-sized screen. */
  const showCamera = capabilities.cameraCapture && isBelowTablet;
  const pasteKeys = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘V" : "Ctrl+V";
  const { bridge, clearLostAccess } = useBusiness();
  const forwardAddress = useForwardAddress();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const replacingRef = useRef<string | null>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const entries = useSyncExternalStore(queue.subscribe, queue.snapshot, queue.snapshot).filter((item) => item.target === target);
  const consent = false;
  const [drag, setDrag] = useState<DragState>({ kind: "idle" });
  const [copyFailed, setCopyFailed] = useState(false);
  const addressRef = useRef<HTMLParagraphElement>(null);
  const copyLabels = useCopyLabels(forwardAddress ?? "");
  const uploading = queue.uploading;
  const unfinished = entries.some(isUnfinishedUpload);
  const saved = entries.flatMap((item) => (item.status === "saved" ? [item.receipt] : []));
  const batch = uploadBatchView(entries, queue.retryWaiting);
  const renderRow = (item: ReceiptUpload) => (
    <UploadRow
      key={item.key}
      item={item}
      locale={locale}
      fileSize={fileSize}
      rejection={item.status === "rejected" ? rejectionText[item.reason] : null}
      retryWaiting={queue.retryWaiting(item.key)}
      canRemove={!uploading && item.status !== "uploading" && item.status !== "saved"}
      onRemove={() => queue.remove(item.key)}
      onRetry={() => queue.retry(item.key)}
      onReplace={() => { replacingRef.current = item.key; fileInputRef.current?.click(); }}
    />
  );
  const [savedOpen, setSavedOpen] = useState(false);
  const many = target === "inbox";
  const progress = many && queue.progress?.target === target ? queue.progress : null;
  const failed = entries.find((item) => item.status === "failed");
  const failure: FailureClass | null = failed?.status === "failed" ? failed.failure : null;
  const [serverReference, setServerReference] = useState("");

  useEffect(() => {
    if (failure !== "server" && failure !== "unavailable") return;
    setServerReference((current) => current || referenceCode(null));
  }, [failure]);

  useEffect(() => {
    if (failure !== "session_ended") return;
    window.location.replace(sessionEndedLoginPath(window.location.pathname, window.location.search));
  }, [failure]);

  const [documentType, setDocumentType] = useState<DocumentType>("recibo");
  /** Files start uploading as soon as they arrive; a running drain takes them at its tail. */
  const choose = (files: readonly File[]) => {
    const before = new Set(queue.snapshot().map((item) => item.key));
    queue.add(files, limits, target, bridge?.conversationId ?? null, documentType);
    const fresh = queue.snapshot().filter((item) => !before.has(item.key) && item.status === "queued").map((item) => item.key);
    if (fresh.length) void queue.save(target, consent, new Set(fresh));
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

  const openPicker = () => {
    replacingRef.current = null;
    fileInputRef.current?.click();
  };
  /** Nothing could copy: select the address so the owner can copy it by hand. */
  const selectAddress = () => {
    setCopyFailed(true);
    const node = addressRef.current;
    const selection = window.getSelection();
    if (!node || !selection) return;
    const range = document.createRange();
    range.selectNodeContents(node);
    selection.removeAllRanges();
    selection.addRange(range);
  };

  const sizeLabel = (bytes: number) =>
    new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(bytes / 1024 / 1024);
  const fileSize = (bytes: number) => bytes < 1024 * 1024
    ? `${new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(Math.max(1, bytes / 1024))} KB`
    : `${sizeLabel(bytes)} MB`;
  const compact = entries.length > 0;
  const formats = receiptFormatLabels(limits).join(", ");
  const rejectionText: Record<UploadRejection, string> = {
    unsupported: t("business.intake.unsupported", "This file isn't supported. Try {{formats}}.", { formats }),
    too_large: t("business.intake.too_large", "This file is larger than {{size}} MB. Use a smaller photo or PDF.", { size: sizeLabel(limits.max_bytes) }),
    heic: t("business.intake.heic", "This is an iPhone HEIC photo. Upload it from your iPhone's browser, which converts it, or export it as JPG first."),
  };

  const onDragEnter = (event: DragEvent) => {
    if (!capabilities.dragAndDrop) return;
    event.preventDefault();
    dragDepth.current += 1;
    setDrag(dragStateFor(event, limits));
  };
  const onDragLeave = () => {
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDrag({ kind: "idle" });
  };
  const onDrop = (event: DragEvent) => {
    if (!capabilities.dragAndDrop) return;
    event.preventDefault();
    dragDepth.current = 0;
    setDrag({ kind: "idle" });
    choose(Array.from(event.dataTransfer.files));
  };

  const zoneTone =
    drag.kind === "accept"
      ? "border-2 border-solid border-[#2f5a49] bg-[#e3ebe1] ring-4 ring-[#2f5a49]/15 dark:border-[#8fcbb0] dark:bg-[#8fcbb0]/10"
      : drag.kind === "reject"
        ? "border-2 border-solid border-[#9e2f39] bg-[#f6dfe0] ring-4 ring-[#9e2f39]/15 dark:border-[#ec9aa0] dark:bg-[#ec9aa0]/10"
        : "border border-dashed border-[#7d8a84] bg-[#FFFEFA] hover:border-[#2f5a49] hover:bg-[#2f5a49]/[0.03] dark:border-white/30 dark:bg-white/[0.02]";
  const zoneTitle =
    drag.kind === "accept"
      ? t("business.intake.drop_release", { count: drag.count, defaultValue: "Drop to upload {{count}} files" })
      : drag.kind === "reject"
        ? t("business.intake.drop_reject", "That file type can't be uploaded. Use {{formats}}.", { formats })
        : capabilities.dragAndDrop && !isBelowTablet
          ? many ? t("business.intake.drop_title_multiple", "Drag your receipts here") : t("business.intake.drop_title", "Drag your receipt here")
          : many ? t("business.intake.touch_title_multiple", "Choose your receipts") : t("business.intake.touch_title", "Choose your receipt");

  return (
    <AdaptivePanel
      title={many ? t("business.intake.queue_title", "Upload receipts") : t("business.intake.title", "Upload receipt")}
      closeLabel={t("common.close", "Close")}
      onClose={onClose}
      width="md"
      footer={entries.length === 0 ? undefined : (
        <div className="flex flex-wrap items-center justify-end gap-2" data-testid="receipt-intake-footer">
          {saved.length > 0 && !unfinished && !uploading ? (
            <button type="button" className={primaryButtonClass} onClick={() => { queue.clear(target); onReview(saved); }}>
              {t("business.intake.review_saved", "Review saved receipts")}
            </button>
          ) : null}
          <button type="button" className={secondaryButtonClass} onClick={onClose}>
            {t("business.intake.done", "Done")}
          </button>
        </div>
      )}
    >
      <div className="space-y-5 px-4 pb-6">
        <div
          data-testid="intake-drop-zone"
          data-drag={drag.kind}
          onDragEnter={onDragEnter}
          onDragOver={(event) => { if (capabilities.dragAndDrop) event.preventDefault(); }}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={openPicker}
          data-compact={compact}
          className={`group cursor-pointer rounded-[20px] transition-[background-color,border-color,box-shadow] duration-150 motion-reduce:transition-none ${compact ? "flex items-center gap-3 px-4 py-3 text-left" : "px-5 py-8 text-center"} ${zoneTone}`}
        >
          <div className={`${compact ? "h-11 w-11 rounded-[12px]" : "mx-auto h-14 w-14 rounded-[16px]"} flex shrink-0 items-center justify-center transition-transform duration-150 motion-reduce:transition-none ${drag.kind === "reject" ? "bg-[#9e2f39]/10 text-[#9e2f39]" : "bg-[#2f5a49]/10 text-[#2f5a49] dark:text-[#8fcbb0]"} ${drag.kind === "accept" ? "-translate-y-1 motion-reduce:translate-y-0" : ""}`}>
            {drag.kind === "reject" ? <CircleAlert className={compact ? "h-5 w-5" : "h-7 w-7"} aria-hidden="true" /> : <FileUp className={compact ? "h-5 w-5" : "h-7 w-7"} aria-hidden="true" />}
          </div>
          <div className={compact ? "min-w-0 flex-1" : ""}>
            <p role="status" aria-live="polite" className={`font-display font-medium ${compact ? "text-[15px] leading-5" : "mt-4 text-[18px] leading-6"} ${drag.kind === "reject" ? DANGER : "text-[#172b26] dark:text-white"}`}>{zoneTitle}</p>
            {compact && drag.kind === "idle" ? <p className={`text-[13px] ${MUTED}`}>{t("business.intake.formats_short", "{{formats}} · up to {{size}} MB", { formats, size: sizeLabel(limits.max_bytes) })}</p> : null}
          </div>
          {drag.kind === "idle" && !compact ? (
            <>
              <p className={`mt-1 text-[13px] ${MUTED}`}>{t("business.intake.formats_short", "{{formats}} · up to {{size}} MB", { formats, size: sizeLabel(limits.max_bytes) })}</p>
              <button type="button" data-testid="intake-choose" className={`${pillButtonClass} mt-5 bg-[#2f5a49] text-[#FFFEFA] dark:bg-[#8fcbb0] dark:text-[#172b26]`} onClick={(event) => { event.stopPropagation(); openPicker(); }}>
                <FolderOpen className="h-4 w-4" aria-hidden="true" />
                {many ? t("business.intake.choose_multiple", "Choose files") : t("business.intake.choose", "Choose file")}
              </button>
              {capabilities.dragAndDrop && !isBelowTablet ? (
                <p className={`mt-3 text-[12px] ${MUTED}`}>{t("business.intake.paste_hint", { keys: pasteKeys, defaultValue: "or paste with {{keys}}" })}</p>
              ) : null}
            </>
          ) : null}
          <input
            ref={fileInputRef}
            type="file"
            multiple={many}
            accept={receiptFileAccept(limits)}
            className="sr-only"
            tabIndex={-1}
            aria-hidden="true"
            onClick={(event) => event.stopPropagation()}
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
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => {
              choose(Array.from(event.target.files ?? []));
              event.target.value = "";
            }}
          />
        </div>

        <div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p id="intake-type-question" className={`text-[14px] ${MUTED}`}>{t("business.intake.saved_as", "Saved as")}</p>
            <div role="radiogroup" aria-labelledby="intake-type-question" className="inline-flex rounded-full bg-black/[0.05] p-1 dark:bg-white/10" data-testid="intake-document-type">
              {(["recibo", "venta"] as const).map((type) => (
                <button
                  key={type}
                  type="button"
                  role="radio"
                  aria-checked={documentType === type}
                  data-testid={`intake-type-${type}`}
                  className={`min-h-11 rounded-full px-4 text-[14px] font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] ${documentType === type ? "bg-white text-[#172b26] shadow-[0_0_0_1px_rgba(0,0,0,0.08)] dark:bg-[#1f2225] dark:text-white" : `${MUTED} hover:text-[#172b26] dark:hover:text-white`}`}
                  onClick={() => setDocumentType(type)}
                >
                  {t(type === "venta" ? "business.intake.type_venta" : "business.intake.type_recibo", type === "venta" ? "Sale" : "Purchase")}
                </button>
              ))}
            </div>
          </div>
          <p className={`mt-1 text-right text-[13px] ${MUTED}`}>
            {documentType === "venta"
              ? t("business.intake.type_venta_help", "An invoice the business issued.")
              : t("business.intake.type_recibo_help", "Something the business paid for.")}
          </p>
        </div>

        {failure === "server" || failure === "unavailable" ? (
          <ServerErrorScreen reference={serverReference} onRetry={() => failed && queue.retry(failed.key)} />
        ) : null}
        {failure === "removed" ? <RemovedMemberScreen onReturn={clearLostAccess} /> : null}
        {failure === "closed" ? <BusinessClosedNotice /> : null}

        {entries.length > 0 ? (
          <section aria-label={t("business.intake.queue_title", "Upload receipts")}>
            <div data-testid="receipt-upload-summary-bar" className="sticky top-0 z-10 -mx-4 mb-2 bg-white px-4 py-2 dark:bg-[#1f2225]">
              <p role="status" aria-live="polite" data-testid="receipt-upload-summary" className="text-[14px] font-medium tabular-nums text-[#172b26] dark:text-white">
                {[
                  progress ? t("business.intake.uploading_progress", "Uploading {{position}} of {{total}}…", { position: progress.position, total: progress.total }) : null,
                  progress && batch.secondsLeft !== null ? timeLeftText(t, batch.secondsLeft) : null,
                  !progress && batch.saved.length > 0 ? t("business.intake.summary_saved", { count: batch.saved.length, defaultValue: "{{count}} saved" }) : null,
                  batch.attention.length > 0 ? t("business.intake.summary_failed", { count: batch.attention.length, defaultValue: "{{count}} not uploaded" }) : null,
                ].filter(Boolean).join(" · ")}
              </p>
              {progress ? (
                <div role="progressbar" aria-label={t("business.intake.queue_title", "Upload receipts")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(batch.share * 100)} className="mt-2 h-1 overflow-hidden rounded-full bg-[#2f5a49]/15">
                  <div className="h-full rounded-full bg-[#2f5a49] transition-[width] duration-200 ease-out motion-reduce:transition-none dark:bg-[#8fcbb0]" style={{ width: `${batch.share * 100}%` }} />
                </div>
              ) : null}
            </div>
            <ul className="space-y-2" data-testid="receipt-upload-queue">
              {[...batch.attention, ...batch.active, ...batch.waiting].map(renderRow)}
              {batch.saved.length === 1 ? batch.saved.map(renderRow) : null}
            </ul>
            {batch.saved.length > 1 ? (
              <div className="mt-2 rounded-[16px] border border-[#DCE0DA] dark:border-white/10" data-testid="receipt-upload-saved-fold">
                <button
                  type="button"
                  aria-expanded={savedOpen}
                  aria-controls="receipt-upload-saved"
                  className="flex min-h-11 w-full items-center gap-2 rounded-[16px] px-3 text-left text-[14px] font-medium text-[#2f5a49] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:text-[#8fcbb0]"
                  onClick={() => setSavedOpen((open) => !open)}
                >
                  <CircleCheck className="h-5 w-5 shrink-0" aria-hidden="true" />
                  <span className="flex-1 tabular-nums">{t("business.intake.summary_saved", { count: batch.saved.length, defaultValue: "{{count}} saved" })}</span>
                  <ChevronDown className={`h-4 w-4 shrink-0 transition-transform motion-reduce:transition-none ${savedOpen ? "rotate-180" : ""}`} aria-hidden="true" />
                </button>
                {savedOpen ? <ul id="receipt-upload-saved" className="space-y-2 px-2 pb-2">{batch.saved.map(renderRow)}</ul> : null}
              </div>
            ) : null}
          </section>
        ) : null}

        {many && (forwardAddress || showCamera) ? (
          <section aria-labelledby="intake-other-ways" data-testid="intake-other-ways">
            <h3 id="intake-other-ways" className={`mb-2 text-[14px] font-medium ${MUTED}`}>{t("business.intake.other_ways", "Other ways to add receipts")}</h3>
            <ul className="divide-y divide-[#DCE0DA] rounded-[16px] border border-[#DCE0DA] dark:divide-white/10 dark:border-white/10">
              {forwardAddress ? (
                <li className="flex items-center gap-3 p-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#2f5a49]/10 text-[#2f5a49] dark:text-[#8fcbb0]">
                    <Mail className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[15px] font-medium text-[#172b26] dark:text-white">{t("business.intake.email_way", "Forward them by email")}</p>
                    <p ref={addressRef} data-testid="intake-forward-address" className={`select-all break-words text-[13px] ${MUTED}`}><WrappingAddress address={forwardAddress} /></p>
                    {copyFailed ? (
                      <p className={`mt-1 text-[13px] ${DANGER}`}>{t("business.email.copy_failed", "Could not copy. Select the address to copy it.")}</p>
                    ) : null}
                  </div>
                  <CopyButton
                    value={forwardAddress}
                    label={t("business.email.copy", "Copy address")}
                    {...copyLabels}
                    onFailed={selectAddress}
                    testId="intake-forward-copy"
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-[#2f5a49] hover:bg-[#2f5a49]/[0.06] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:text-[#8fcbb0]"
                  />
                </li>
              ) : null}
              {showCamera ? (
                <li>
                  <button type="button" data-testid="intake-camera" className="flex min-h-11 w-full items-center gap-3 p-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49]" onClick={() => cameraInputRef.current?.click()}>
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#2f5a49]/10 text-[#2f5a49] dark:text-[#8fcbb0]">
                      <Camera className="h-5 w-5" aria-hidden="true" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[15px] font-medium text-[#172b26] dark:text-white">{t("business.intake.camera_way", "Take a photo")}</span>
                      <span className={`block text-[13px] ${MUTED}`}>{t("business.intake.camera_way_help", "With your phone's camera")}</span>
                    </span>
                    <ChevronRight className={`h-4 w-4 shrink-0 ${MUTED}`} aria-hidden="true" />
                  </button>
                </li>
              ) : null}
            </ul>
          </section>
        ) : null}

        <ReceiptReadingControl />
        {unfinished ? (
          <p className={`text-[13px] ${MUTED}`}>
            {t("business.intake.keep_open", "You can close this panel and come back to your uploads. Keep this page open until every file is saved.")}
          </p>
        ) : null}
      </div>
    </AdaptivePanel>
  );
}

type Translate = ReturnType<typeof useTranslation>["t"];

function timeLeftText(t: Translate, seconds: number): string {
  return seconds < 60
    ? t("business.intake.row_seconds_left", { count: Math.max(1, seconds), defaultValue: "{{count}} s left" })
    : t("business.intake.row_minutes_left", { count: Math.ceil(seconds / 60), defaultValue: "{{count}} min left" });
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
  const saved = entries.filter((item) => item.status === "saved");
  const bytesOf = (items: readonly ReceiptUpload[]) => items.reduce((sum, item) => sum + item.file.size, 0);
  const sending = active.reduce((sum, item) => sum + (item.status === "uploading" && item.bytes ? item.bytes.sent : 0), 0);
  const total = bytesOf([...active, ...waiting, ...saved]);
  const done = bytesOf(saved) + sending;
  const rate = active.flatMap((item) => (item.status === "uploading" && item.bytes?.bytesPerSecond ? [item.bytes.bytesPerSecond] : []))[0] ?? null;
  const remaining = total - done;
  return {
    attention,
    active,
    waiting,
    saved,
    share: total > 0 ? Math.min(1, done / total) : 0,
    secondsLeft: rate ? Math.ceil(remaining / rate) : null,
  };
}

/** A small preview of an image file; a PDF or other file shows its kind instead. */
function FileThumb({ file }: { file: File }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    if (!file.type.startsWith("image/") || typeof createImageBitmap === "undefined") return undefined;
    let live = true;
    createImageBitmap(file).then((bitmap) => {
      const scale = Math.min(1, 112 / Math.max(bitmap.width, bitmap.height));
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
    <span className="flex h-14 w-11 shrink-0 items-center justify-center overflow-hidden rounded-[8px] border border-[#DCE0DA] bg-[#F7F5EE] dark:border-white/10 dark:bg-white/5">
      {src ? <Image unoptimized src={src} alt="" width={44} height={56} className="h-full w-full object-cover" /> : <FileText className="h-5 w-5 text-[#56635e] dark:text-white/70" aria-hidden="true" />}
    </span>
  );
}

function UploadRow({ item, locale, fileSize, rejection, retryWaiting, canRemove, onRemove, onRetry, onReplace }: {
  item: ReceiptUpload;
  locale: string;
  fileSize: (bytes: number) => string;
  rejection: string | null;
  retryWaiting: boolean;
  canRemove: boolean;
  onRemove: () => void;
  onRetry: () => void;
  onReplace: () => void;
}) {
  const { t } = useTranslation();
  const bytes = item.status === "uploading" ? item.bytes : null;
  const share = bytes && bytes.total > 0 ? Math.min(1, bytes.sent / bytes.total) : 0;
  const percent = new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 0 }).format(share);
  const left = bytes?.secondsLeft;
  const timeLeft = left == null || share >= 1 ? null : timeLeftText(t, left);
  const failedRetryable = item.status === "failed" && ROW_RETRY.has(item.failure);
  return (
    <li data-testid="receipt-upload-row" data-status={item.status} className={`rounded-[16px] border p-3 ${item.status === "failed" || item.status === "rejected" ? "border-[#9e2f39]/30 bg-[#f6dfe0]/40 dark:border-[#ec9aa0]/30" : "border-[#DCE0DA] bg-[#FFFEFA] dark:border-white/10 dark:bg-transparent"}`}>
      <div className="flex items-center gap-3">
        <FileThumb file={item.file} />
        <div className="min-w-0 flex-1">
          <p className="break-words text-[14px] font-medium text-[#172b26] dark:text-white">{item.file.name}</p>
          <p className={`flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] tabular-nums ${MUTED}`}>
            <span>{`${receiptFormatLabel(item.file.type)} · ${fileSize(item.file.size)}`}</span>
            <span data-testid="receipt-upload-type" className="inline-flex h-5 items-center rounded-full bg-black/[0.06] px-2 text-[12px] font-medium text-[#172b26] dark:bg-white/10 dark:text-white">
              {t(item.documentType === "venta" ? "business.intake.type_venta" : "business.intake.type_recibo", item.documentType === "venta" ? "Sale" : "Purchase")}
            </span>
            {item.status === "queued" || retryWaiting ? (
              <span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5" aria-hidden="true" />{t("business.intake.row_waiting", "Waiting")}</span>
            ) : null}
          </p>
        </div>
        {item.status === "saved" ? <CircleCheck className="h-6 w-6 shrink-0 text-[#2f5a49] dark:text-[#8fcbb0]" aria-hidden="true" /> : null}
        {canRemove ? (
          <button
            type="button"
            onClick={onRemove}
            aria-label={t("business.intake.remove_file", "Remove {{name}} from this upload list", { name: item.file.name })}
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] ${MUTED}`}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        ) : null}
      </div>

      {item.status === "uploading" ? (
        <div className="mt-3">
          <div
            role="progressbar"
            aria-label={item.file.name}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(share * 100)}
            className="h-1.5 overflow-hidden rounded-full bg-[#2f5a49]/15"
          >
            <div className="h-full rounded-full bg-[#2f5a49] transition-[width] duration-200 ease-out motion-reduce:transition-none dark:bg-[#8fcbb0]" style={{ width: `${share * 100}%` }} />
          </div>
          <p className={`mt-1.5 text-[13px] tabular-nums ${MUTED}`}>{[percent, timeLeft].filter(Boolean).join(" · ")}</p>
        </div>
      ) : null}
      {item.status === "saved" ? (
        <p className="mt-2 text-[13px] text-[#2f5a49] dark:text-[#8fcbb0]">
          {item.receipt.replayed ? t("business.intake.replayed", "Already saved before. This is that receipt.") : t("business.intake.row_saved", "Saved")}
        </p>
      ) : null}
      {item.status === "failed" && !retryWaiting ? (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <p role="alert" className={`text-[13px] ${DANGER}`}>
            {item.failure === "offline" ? t("business.intake.row_failed_offline", "Connection lost. Your file is still here.") : t("business.intake.row_failed", "Couldn't upload. Your file is still here.")}
          </p>
          {failedRetryable ? (
            <button type="button" className={smallAction} aria-label={t("business.intake.retry_file", "Retry {{name}}", { name: item.file.name })} onClick={onRetry}>
              <RotateCw className="h-4 w-4" aria-hidden="true" />
              {t("common.retry", "Retry")}
            </button>
          ) : null}
        </div>
      ) : null}
      {item.status === "rejected" && rejection ? (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <p role="alert" className={`text-[13px] ${DANGER}`}>{rejection}</p>
          <button type="button" className={smallAction} onClick={onReplace}>
            {t("business.intake.choose_another", "Choose another file")}
          </button>
        </div>
      ) : null}
    </li>
  );
}
