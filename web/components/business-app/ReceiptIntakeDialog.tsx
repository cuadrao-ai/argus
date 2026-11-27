"use client";

import { useEffect, useRef, useState, useSyncExternalStore, type DragEvent } from "react";
import { Camera, ChevronDown, ChevronRight, CircleAlert, CircleCheck, Mail, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { BusinessClosedNotice } from "@/components/status/BusinessClosedNotice";
import { RemovedMemberScreen } from "@/components/status/RemovedMemberScreen";
import { ServerErrorScreen } from "@/components/status/ServerErrorScreen";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { referenceCode, sessionEndedLoginPath, type FailureClass } from "@/lib/failure-screen";
import { randomId } from "@/lib/random-id";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import type { ReceiptLimits, ReceiptSummary } from "@/lib/business-api";
import { useReceivingChannels } from "./business-context";
import { useBusiness } from "./BusinessWorkspace";
import { primaryButtonClass } from "./business-ui";
import { Settle } from "./business-skeletons";
import { receiptFileAccept, receiptFormatLabels } from "./receipt-file";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { ReceiptUploadQueue, type DocumentType, type IntakeTarget, type ReceiptUpload, type UploadRejection } from "./receipt-upload-queue";
import { uploadBatchView, uploadStage, uploadSummaryText, uploadTimeLeftText } from "./receipt-upload-view";
import ReceiptDropZone, { type DragState } from "./ReceiptDropZone";
import ReceiptUploadRow, { intakeLinkClass } from "./ReceiptUploadRow";
import { ReceiptReadingOption, useReceiptReading } from "./ReceiptReadingControl";
import { CopyButton, WrappingAddress, useCopyLabels } from "./foundation/CopyButton";
import { CHANNEL_ICON } from "./foundation/channel-icons";
import { EmptyState } from "./foundation/EmptyState";
import { showToast } from "./foundation/toasts";
import { enteredIn, getChosenGrant, subscribeChosenGrant } from "@/lib/business-grant";
import { useForwardAddress } from "./useForwardAddress";
import { useInputCapabilities } from "./useInputCapabilities";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { resolveLanguage } from "@/lib/language-features";
import styles from "./receipt-intake.module.css";

export type { IntakeTarget } from "./receipt-upload-queue";

type IntakeProps = {
  target: IntakeTarget;
  focusAttention?: boolean;
  queue: ReceiptUploadQueue;
  onClose: () => void;
  /** Every saved receipt of this target, in the order the dossier walks them. */
  onReview: (receipts: ReceiptSummary[]) => void;
};

const MUTED = "text-[#56635e] dark:text-white/70";
const DANGER = "text-[#9e2f39] dark:text-[#ec9aa0]";
const CARD = "rounded-surface border border-[#E4E2DA] bg-[#FFFEFA] pl-4 dark:border-white/10 dark:bg-[#1f2225]";
const CARD_ROW = "border-b border-[#ECEAE3] last:border-b-0 dark:border-white/[0.07]";
const FOLD = "mb-3 mr-2 mt-1 rounded-item border border-[#E4E2DA] bg-[#FBFAF6] dark:border-white/10 dark:bg-[#1f2225]";
const FOLD_HEAD = "flex min-h-12 min-w-0 flex-1 items-center gap-2.5 rounded-item px-3 text-left text-[14px] font-medium tabular-nums focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49]";

export default function ReceiptIntakeDialog({ target, ...props }: Omit<IntakeProps, "target"> & { target: IntakeTarget | null }) {
  if (!target) return null;
  return <IntakeSurface target={target} {...props} />;
}

/** The form needs the business's upload limits; until they arrive the sheet shows the load's own state. */
function IntakeSurface(props: IntakeProps) {
  const { t } = useTranslation();
  const { records, reload } = useBusiness();
  const limits = records.workspace?.receipt_limits;
  if (limits) return <IntakeForm limits={limits} {...props} />;
  const failed = records.error || Boolean(records.serverReference);
  return (
    <AdaptivePanel title={props.target === "inbox" ? t("business.intake.panel_title") : t("business.intake.title")} closeLabel={t("common.close")} onClose={props.onClose} width="record">
      <div className="px-4 pb-4">
        {records.closed ? (
          <div className="flex justify-center"><BusinessClosedNotice /></div>
        ) : failed ? (
          <EmptyState kind="error" compact testId="receipt-intake-error" title={t("business.empty.overview_error", "We couldn't load your business")} body={t("business.empty.error_body", "Your data is still saved. Check your connection and try again.")} action={{ label: t("common.retry", "Retry"), run: reload }} />
        ) : (
          <Settle pending layout="rows" rows={2} />
        )}
      </div>
    </AdaptivePanel>
  );
}

function dragStateFor(event: DragEvent, limits: ReceiptLimits): DragState {
  const files = Array.from(event.dataTransfer.items ?? []).filter((item) => item.kind === "file");
  if (!files.length) return "idle";
  const known = (type: string) => !type || (limits.media_types.includes(type) && type !== "image/heic" && type !== "image/heif");
  return files.every((item) => known(item.type.toLowerCase())) ? "accept" : "reject";
}

/** The lowest value seen while `active`, so a time left only ever shrinks; it starts over with the next batch. */
function useOnlyShrinks(value: number | null, active: boolean): number | null {
  const [low, setLow] = useState<number | null>(null);
  const next = !active ? null : value === null ? low : low === null ? value : Math.min(low, value);
  if (next !== low) setLow(next);
  return next;
}

function IntakeForm({ limits, target, queue, onClose, onReview, focusAttention }: IntakeProps & { limits: ReceiptLimits }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const capabilities = useInputCapabilities();
  const { isBelowTablet } = useResponsiveLayout();
  /** The photo row is for phones: a camera, file capture and a phone-sized screen. */
  const showCamera = capabilities.cameraCapture && isBelowTablet;
  const canDrag = capabilities.dragAndDrop && !isBelowTablet;
  const { bridge, clearLostAccess, source, chosen, reload, openPanel } = useBusiness();
  const channels = useReceivingChannels();
  const forwardAddress = useForwardAddress();
  const readingState = useReceiptReading();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const replacingRef = useRef<string | null>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const grant = useSyncExternalStore(subscribeChosenGrant, getChosenGrant, () => null);
  // Only this Business's uploads show; a save or retry carries the Business the file was entered in.
  const entries = useSyncExternalStore(queue.subscribe, queue.snapshot, queue.snapshot).filter((item) => item.target === target).filter(enteredIn(grant));
  const consent = false;
  const [drag, setDrag] = useState<DragState>("idle");
  const [copyFailed, setCopyFailed] = useState(false);
  const addressRef = useRef<HTMLParagraphElement>(null);
  const copyLabels = useCopyLabels(forwardAddress ?? "");
  const batch = uploadBatchView(entries, queue.retryWaiting, queue.attempts);
  const saved = batch.savedReceipts;
  const [deletedOpen, setDeletedOpen] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [restoreFailures, setRestoreFailures] = useState<ReadonlyMap<string, string>>(new Map());
  const restoreKeys = useRef(new Map<string, string>());
  const restoreInFlight = useRef(false);
  const canRestore = Boolean(chosen?.capabilities.includes("approve") && source.restoreDocument);
  const restorable = batch.deleted.filter(item => item.receipt.restore_available);
  const restore = async (ids: readonly string[], view: "receipt" | "inbox" = "inbox") => {
    if (!canRestore || !source.restoreDocument || restoreInFlight.current) return;
    restoreInFlight.current = true;
    setRestoring(true);
    const restored: string[] = [];
    try {
      for (const id of new Set(ids)) {
        const key = restoreKeys.current.get(id) ?? randomId();
        restoreKeys.current.set(id, key);
        setRestoreFailures(current => { const next = new Map(current); next.delete(id); return next; });
        try {
          await source.restoreDocument(id, key);
          const receipt = await source.receipt(id);
          queue.updateReceipt(receipt);
          if (!receipt.deleted) { restoreKeys.current.delete(id); restored.push(id); }
          reload();
        } catch (error) {
          setRestoreFailures(current => new Map(current).set(id, referenceCode(error)));
        }
      }
    } finally {
      restoreInFlight.current = false;
      setRestoring(false);
    }
    if (restored.length > 0) showToast({ kind: "success", text: t("business.document_delete.restored"), action: { label: t("business.document_delete.view"), run: () => openPanel(view === "receipt" ? { kind: "receipt", receiptId: restored[0], list: "inbox" } : { kind: "inbox" }) } });
  };
  const renderRow = (item: ReceiptUpload) => {
    const restoreFailure = item.status === "saved" ? restoreFailures.get(item.receipt.id) : undefined;
    return <ReceiptUploadRow
      key={item.key}
      item={item}
      stage={uploadStage(item, queue.retryWaiting(item.key))}
      size={fileSize(item.file.size)}
      problem={item.status === "rejected" ? rejectionText[item.reason] : null}
      restoreControl={item.status === "saved" && item.receipt.deleted ? <span className="inline-flex flex-col items-end">
        {canRestore && item.receipt.restore_available ? <button type="button" className={intakeLinkClass} disabled={restoring} onClick={() => void restore([item.receipt.id], "receipt")}>{t("business.document_delete.restore")}</button> : null}
        {restoreFailure ? <span role="alert" className={`text-[13px] ${DANGER}`}>{t("business.document_delete.restore_failed")} <ReferenceCode reference={restoreFailure} /></span> : null}
      </span> : null}
      onRemove={() => queue.remove(item.key)}
      onRetry={() => queue.retry(item.key)}
      onReplace={() => { replacingRef.current = item.key; fileInputRef.current?.click(); }}
    />;
  };
  const [savedOpen, setSavedOpen] = useState(false);
  const many = target === "inbox";
  const batchSummary = uploadSummaryText(t, batch, many ? "panel" : "composer");
  const firstAttention = useRef<HTMLElement | null>(null);
  const timeLeft = uploadTimeLeftText(t, batch, useOnlyShrinks(batch.secondsLeft, batch.busy));
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

  const reading = readingState.reading;
  // With reading off nothing detects the type, so the batch is a purchase until the person says it is a sale.
  const noDetect = reading !== null && !reading.enabled;
  const [picked, setPicked] = useState<DocumentType | null>(null);
  const documentType: DocumentType | null = picked ?? (noDetect ? "recibo" : null);
  /** Files start uploading as soon as they arrive; a running drain takes them at its tail. */
  const choose = (files: readonly File[]) => {
    const before = new Set(queue.snapshot().map((item) => item.key));
    queue.add(files, limits, target, bridge?.conversationId ?? null, documentType, grant);
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
  const hasFiles = entries.length > 0;
  const formats = receiptFormatLabels(limits).join(", ");
  const rejectionText: Record<UploadRejection, string> = {
    unsupported: t("business.intake.unsupported", { formats }),
    too_large: t("business.intake.too_large", { size: sizeLabel(limits.max_bytes) }),
    heic: t("business.intake.heic"),
  };

  const onDragEnter = (event: DragEvent) => {
    if (!capabilities.dragAndDrop) return;
    event.preventDefault();
    dragDepth.current += 1;
    setDrag(dragStateFor(event, limits));
  };
  const onDragLeave = () => {
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDrag("idle");
  };
  const onDrop = (event: DragEvent) => {
    if (!capabilities.dragAndDrop) return;
    event.preventDefault();
    dragDepth.current = 0;
    setDrag("idle");
    choose(Array.from(event.dataTransfer.files));
  };

  const zoneTitle =
    drag === "accept"
      ? t("business.intake.drop_release")
      : drag === "reject"
        ? t("business.intake.drop_reject", { formats })
        : hasFiles && canDrag
          ? t("business.intake.drop_more")
          : many ? t("business.intake.drop_title_multiple") : t("business.intake.drop_title");
  const kindHelp = noDetect
    ? t("business.intake.kind_help_no_reading")
    : documentType === null
      ? t("business.intake.kind_help_auto")
      : t("business.intake.kind_help_picked");
  const WhatsappIcon = CHANNEL_ICON.whatsapp;
  const otherWays = many && (forwardAddress || channels.whatsapp.available || showCamera) && (!hasFiles || showCamera);

  return (
    <AdaptivePanel
      title={many ? t("business.intake.panel_title") : t("business.intake.title")}
      closeLabel={t("common.close")}
      onClose={onClose}
      width="record"
      initialFocusRef={focusAttention ? firstAttention : undefined}
      summary={batchSummary || undefined}
      snaps={["peek", "half", "full"]}
      initialSnap={isBelowTablet ? "full" : "half"}
      // Closing never stops an upload, so the footer says what does: closing the tab.
      footer={hasFiles ? (
        <div className="flex items-center justify-between gap-3" data-testid="receipt-intake-footer">
          {batch.busy ? (
            <p data-testid="receipt-intake-keep" className={`flex items-center gap-2 text-[13px] leading-[18px] ${MUTED}`}>
              <CircleAlert className="h-4 w-4 shrink-0 text-[#735c14] dark:text-[#f6e7c1]" aria-hidden="true" />
              {t("business.intake.keep_tab")}
            </p>
          ) : <span />}
          <button type="button" data-testid="receipt-intake-review" className={`${primaryButtonClass} shrink-0`} disabled={batch.busy || restoring || saved.length === 0} onClick={() => { queue.clearSettled(target, grant); onReview(saved); }}>
            {t("business.intake.review_count", { count: saved.length })}
          </button>
        </div>
      ) : undefined}
    >
      <div data-upload-form="" className="flex flex-col gap-4 px-4 pb-6 pt-5 desktop:px-6">
        <ReceiptDropZone
          compact={hasFiles}
          drag={drag}
          title={zoneTitle}
          formats={t("business.intake.formats_each", { formats, size: sizeLabel(limits.max_bytes) })}
          canDrag={canDrag}
          onPick={openPicker}
          onDragEnter={onDragEnter}
          onDragOver={(event) => { if (capabilities.dragAndDrop) event.preventDefault(); }}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
        />
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

        <section className={`${CARD} pr-3`} aria-label={t("business.intake.options_label")} data-testid="intake-options">
          <ReceiptReadingOption state={readingState} className="border-b border-[#ECEAE3] dark:border-white/[0.07]" />
          <div className="flex min-h-16 flex-wrap items-center justify-between gap-x-4 gap-y-2 py-2.5">
            <span className="flex min-w-0 flex-col gap-0.5">
              <span className="text-[14px] font-medium text-[#172b26] dark:text-white">{t("business.intake.kind_label")}</span>
              <span data-testid="intake-type-help" className={`text-[12.5px] leading-[17px] ${MUTED}`}>{kindHelp}</span>
            </span>
            <SegmentedControl
              testId="intake-document-type"
              label={t("business.intake.kind_label")}
              segments={[
                { key: "auto" as const, label: t("business.intake.kind_auto"), disabled: noDetect },
                { key: "recibo" as const, label: t("business.intake.kind_recibo") },
                { key: "venta" as const, label: t("business.intake.kind_venta") },
              ]}
              value={documentType ?? "auto"}
              onChange={(key) => setPicked(key === "auto" ? null : key)}
            />
          </div>
        </section>

        {failure === "server" || failure === "unavailable" ? (
          <ServerErrorScreen reference={serverReference} onRetry={() => failed && queue.retry(failed.key)} />
        ) : null}
        {failure === "removed" ? <RemovedMemberScreen onReturn={clearLostAccess} /> : null}
        {failure === "closed" ? <BusinessClosedNotice /> : null}

        {hasFiles ? (
          <section className={`${CARD} pr-2`} aria-label={t("business.intake.files_title")} data-testid="receipt-upload-card">
            <div className="flex h-11 items-center justify-between border-b border-[#ECEAE3] pr-2 dark:border-white/[0.07]">
              <h3 className="font-display text-[14px] font-semibold text-[#172b26] dark:text-white">{t("business.intake.files_title")}</h3>
              <span className={`text-[13px] tabular-nums ${MUTED}`}>{t("business.intake.files_count", { count: entries.length })}</span>
            </div>
            <p role="status" aria-live="polite" data-testid="receipt-upload-summary" className="sr-only">{batchSummary}</p>
            {batch.busy ? (
              <div data-testid="receipt-upload-summary-bar" className="flex items-center gap-3 pb-1.5 pr-2 pt-2.5">
                {batch.share === null
                  ? <span className={`${styles.total} ${styles.unknown} rounded-full`} role="progressbar" aria-label={t("business.intake.total_progress")} aria-busy="true"><i /></span>
                  : <span className={`${styles.total} rounded-full`} role="progressbar" aria-label={t("business.intake.total_progress")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.floor(batch.share * 100)}><i style={{ width: `${batch.share * 100}%` }} /></span>}
                {timeLeft ? <span data-testid="receipt-upload-time-left" aria-live="polite" className={`shrink-0 text-[12.5px] font-medium tabular-nums ${MUTED}`}>{timeLeft}</span> : null}
              </div>
            ) : null}
            <ul className="py-1" data-testid="receipt-upload-queue" ref={list => {
              firstAttention.current = list?.querySelector<HTMLElement>('[data-status="failed"] button, [data-status="rejected"] button') ?? null;
            }}>
              {[...batch.attention, ...batch.active, ...batch.waiting].map(renderRow)}
            </ul>
            {batch.saved.length > 0 ? (
              <div className={FOLD} data-testid="receipt-upload-saved-fold">
                <button type="button" aria-expanded={savedOpen} aria-controls="receipt-upload-saved" className={`${FOLD_HEAD} w-full text-[#2f5a49] dark:text-[#8fcbb0]`} onClick={() => setSavedOpen((open) => !open)}>
                  <span key={saved.length} className={styles.bump}><CircleCheck className="h-[18px] w-[18px] shrink-0" aria-hidden="true" /></span>
                  <span className="flex-1">{t("business.intake.summary_saved", { count: saved.length })}</span>
                  <ChevronDown className={`h-4 w-4 shrink-0 transition-transform motion-reduce:transition-none ${savedOpen ? "rotate-180" : ""}`} aria-hidden="true" />
                </button>
                {savedOpen ? <ul id="receipt-upload-saved" className="border-t border-[#ECEAE3] pb-1 pl-3 pr-2 dark:border-white/[0.07]">{batch.saved.map(renderRow)}</ul> : null}
              </div>
            ) : null}
            {batch.deleted.length > 0 ? (
              <div className={FOLD} data-testid="receipt-upload-deleted-fold">
                <div className="flex items-center pr-1.5">
                  <button type="button" aria-expanded={deletedOpen} aria-controls="receipt-upload-deleted" className={`${FOLD_HEAD} ${MUTED}`} onClick={() => setDeletedOpen(open => !open)}>
                    <RotateCcw className="h-[18px] w-[18px] shrink-0" aria-hidden="true" />
                    <span className="flex-1">{t("business.document_delete.upload_deleted_count", { count: batch.deletedReceipts.length })}</span>
                    <ChevronDown className={`h-4 w-4 shrink-0 transition-transform motion-reduce:transition-none ${deletedOpen ? "rotate-180" : ""}`} aria-hidden="true" />
                  </button>
                  {canRestore && restorable.length > 0 ? <button type="button" className={intakeLinkClass} disabled={restoring} onClick={() => void restore(restorable.map(item => item.receipt.id))}>{t("business.document_delete.restore_all")}</button> : null}
                </div>
                {!deletedOpen && batch.deleted.some(item => restoreFailures.has(item.receipt.id)) ? <p role="alert" className={`px-3 pb-2 text-[13px] ${DANGER}`}>{t("business.document_delete.restore_failed")}</p> : null}
                {deletedOpen ? <ul id="receipt-upload-deleted" className="border-t border-[#ECEAE3] pb-1 pl-3 pr-2 dark:border-white/[0.07]">{batch.deleted.map(renderRow)}</ul> : null}
              </div>
            ) : null}
          </section>
        ) : null}

        {otherWays ? (
          <section className={`${CARD} pr-2`} aria-labelledby="intake-other-ways" data-testid="intake-other-ways">
            <div className="flex h-11 items-center border-b border-[#ECEAE3] dark:border-white/[0.07]">
              <h3 id="intake-other-ways" className="font-display text-[14px] font-semibold text-[#172b26] dark:text-white">{t("business.intake.other_ways")}</h3>
            </div>
            <ul className="py-1">
              {forwardAddress ? (
                <li data-testid="intake-way-email" className={`grid min-h-[60px] grid-cols-[24px_minmax(0,1fr)_auto] items-center gap-x-3 py-2 ${CARD_ROW}`}>
                  <Mail className={`h-[18px] w-[18px] ${MUTED}`} aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="text-[14px] font-medium text-[#172b26] dark:text-white">{t("business.intake.email_way")}</p>
                    <p ref={addressRef} data-testid="intake-forward-address" className="select-all break-words font-mono text-[13px] text-[#3d4a45] dark:text-white/70"><WrappingAddress address={forwardAddress} /></p>
                    {copyFailed ? (
                      <p className={`mt-1 text-[13px] ${DANGER}`}>{t("business.email.copy_failed")}</p>
                    ) : null}
                  </div>
                  <CopyButton
                    value={forwardAddress}
                    label={t("business.email.copy")}
                    {...copyLabels}
                    onFailed={selectAddress}
                    testId="intake-forward-copy"
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-[#2f5a49] hover:bg-[#2f5a49]/[0.06] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:text-[#8fcbb0]"
                  />
                </li>
              ) : null}
              {channels.whatsapp.available ? (
                <li data-testid="intake-way-whatsapp" className={`grid min-h-[60px] grid-cols-[24px_minmax(0,1fr)] items-center gap-x-3 py-2 ${CARD_ROW}`}>
                  <WhatsappIcon size={18} className={MUTED} aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="text-[14px] font-medium text-[#172b26] dark:text-white">{t("business.intake.whatsapp_way")}</p>
                    <p className={`text-[13px] ${MUTED}`}>{t("business.intake.whatsapp_way_help")}</p>
                  </div>
                </li>
              ) : null}
              {showCamera ? (
                <li className={CARD_ROW}>
                  <button type="button" data-testid="intake-camera" className="grid min-h-[60px] w-full grid-cols-[24px_minmax(0,1fr)_auto] items-center gap-x-3 rounded-item py-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49]" onClick={() => cameraInputRef.current?.click()}>
                    <Camera className={`h-[18px] w-[18px] ${MUTED}`} aria-hidden="true" />
                    <span className="min-w-0">
                      <span className="block text-[14px] font-medium text-[#172b26] dark:text-white">{t("business.intake.camera_way")}</span>
                      <span className={`block text-[13px] ${MUTED}`}>{t("business.intake.camera_way_help")}</span>
                    </span>
                    <ChevronRight className={`h-4 w-4 shrink-0 ${MUTED}`} aria-hidden="true" />
                  </button>
                </li>
              ) : null}
            </ul>
          </section>
        ) : null}
      </div>
    </AdaptivePanel>
  );
}
