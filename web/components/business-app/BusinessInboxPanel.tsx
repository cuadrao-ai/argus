"use client";

import { useCallback, useRef, useState } from "react";
import { ChevronRight, FileText, ImageIcon, Mail, MessageCircle, NotebookPen } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { BusinessCapture, ReceiptSummary } from "@/lib/business-api";
import ReceiptReadingControl from "./ReceiptReadingControl";
import BusinessEmailDeliveries from "./BusinessEmailDeliveries";
import { savedUnread, savedUnreadLine } from "./ReceiptReadNotice";
import { useBusiness } from "./BusinessWorkspace";
import { bandejaReceipts } from "./bandeja-order";
import { formatMoney, formatRelativeTime } from "./business-format";
import { cardClass, LoadingRows, PanelHeading, pillButtonClass, secondaryButtonClass, RecordMarks, StatusPill, UndoToast, useAttentionLabel } from "./business-ui";

export type OpenNote = { draftId: string; text: string; receivedAt: string; revision: number; earlier: number };

/**
 * One row per draft still awaiting review: its latest note, and how many came
 * before it. Recorded and dismissed drafts leave the Inbox.
 */
export function openNotesByDraft(captures: readonly BusinessCapture[]): OpenNote[] {
  const byDraft = new Map<string, OpenNote>();
  for (const note of captures) {
    if (note.review_state !== "open" && note.review_state !== "accepting") continue;
    const current = byDraft.get(note.draft_id);
    if (!current) {
      byDraft.set(note.draft_id, { draftId: note.draft_id, text: note.text, receivedAt: note.received_at, revision: note.revision, earlier: 0 });
    } else if (note.received_at > current.receivedAt) {
      byDraft.set(note.draft_id, { ...current, text: note.text, receivedAt: note.received_at, revision: Math.max(note.revision, current.revision), earlier: current.earlier + 1 });
    } else {
      current.earlier += 1;
      current.revision = Math.max(note.revision, current.revision);
    }
  }
  return [...byDraft.values()].sort((a, b) => (a.receivedAt < b.receivedAt ? 1 : -1));
}

export { inboxCount } from "./inbox-count";

export function NotesAwaitingReview({ notes, error, truncated = false, onOpen }: { notes: OpenNote[]; error: boolean; truncated?: boolean; onOpen: (draftId: string) => void }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  if (!error && notes.length === 0) return null;
  return (
    <section aria-label={t("business.inbox.notes_title", "Notes awaiting review")} className="mb-6">
      <h3 className="font-display text-[16px] font-medium text-black dark:text-white">{t("business.inbox.notes_title", "Notes awaiting review")}</h3>
      <p className="mb-3 mt-0.5 text-[13px] text-black/55 dark:text-white/55">{t("business.inbox.notes_subtitle", "Saved in your own words. Open one to add facts or a receipt.")}</p>
      {error ? (
        <p role="alert" className="text-[14px] text-black/70 dark:text-white/70">{t("business.inbox.notes_error", "We couldn't load your notes. Try again.")}</p>
      ) : (
        <ul className={`${cardClass} divide-y divide-black/[0.05] p-2 dark:divide-white/[0.05]`} data-testid="business-inbox-notes">
          {notes.map((note) => (
            <li key={note.draftId}>
              <button
                type="button"
                onClick={() => onOpen(note.draftId)}
                className="flex w-full items-center gap-3 rounded-[16px] px-3 py-3 text-left transition-colors hover:bg-black/[0.03] focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:hover:bg-white/[0.04] dark:focus-visible:ring-white/30"
              >
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[12px] bg-black/[0.04] dark:bg-white/[0.06]">
                  <NotebookPen className="h-5 w-5 text-black/55 dark:text-white/55" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-2 whitespace-pre-line break-words text-[15px] text-black dark:text-white">{note.text.trim()}</span>
                  <span className="mt-0.5 block truncate text-[13px] text-black/50 dark:text-white/50">
                    {[formatRelativeTime(note.receivedAt, locale), t("business.dossier.revision", "Revision {{version}}", { version: note.revision }), note.earlier ? t("business.inbox.note_more", "{{count}} earlier notes", { count: note.earlier }) : null].filter(Boolean).join(" · ")}
                  </span>
                </span>
                <ChevronRight className="h-4 w-4 shrink-0 text-black/30 dark:text-white/30" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {truncated && !error ? <p className="mt-2 text-[13px] text-black/55 dark:text-white/55">{t("business.inbox.notes_latest", "Showing the latest 50 saved notes. Older open notes are reachable through search.")}</p> : null}
    </section>
  );
}

export function ReceiptRow({ receipt, onOpen, onMark, onRetry }: { receipt: ReceiptSummary; onOpen: () => void; onMark?: (receipt: ReceiptSummary) => void; onRetry?: () => Promise<void> }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const attentionLabel = useAttentionLabel();
  const Icon = receipt.media_type === "application/pdf" ? FileText : ImageIcon;
  const needsAttention = receipt.status === "needs_attention";
  const [retry, setRetry] = useState<"idle" | "retrying" | "failed">("idle");
  const inFlight = useRef(false);
  const tryAgain = async () => {
    if (inFlight.current || !receipt.preparable || !onRetry) return;
    inFlight.current = true;
    setRetry("retrying");
    try {
      await onRetry();
      setRetry("idle");
    } catch {
      setRetry("failed");
    } finally {
      inFlight.current = false;
    }
  };
  return (
    // On a phone the Personal toggle wraps under the row so the merchant keeps its column.
    <li className="flex flex-wrap items-center gap-1">
      <button
        type="button"
        onClick={onOpen}
        className={`flex min-w-0 flex-1 ${needsAttention ? "basis-full items-start" : "basis-80 items-center"} gap-3 rounded-[16px] px-3 py-3 text-left transition-colors hover:bg-black/[0.03] focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:hover:bg-white/[0.04]`}
      >
        <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-[12px] bg-black/[0.04] dark:bg-white/[0.06]">
          {receipt.activity?.state === "reading" ? <span aria-hidden="true" data-testid="receipt-reading-ring" className="absolute inset-0 rounded-[12px] border-2 border-teal-500/50 border-t-transparent motion-safe:animate-spin" /> : receipt.activity?.unread ? <span aria-hidden="true" data-testid="receipt-unread-dot" className="absolute right-0 top-0 h-2 w-2 rounded-full bg-teal-600" /> : null}
          <Icon className="h-5 w-5 text-black/55 dark:text-white/55" />
        </span>
        <span className="min-w-0 flex-1">
          <span className={`block ${needsAttention ? "break-words" : "truncate"} text-[15px] font-medium text-black dark:text-white`}>
            {receipt.merchant ?? receipt.filename ?? t("business.receipt.untitled", "Receipt")}
          </span>
          <span className={`mt-0.5 flex gap-1.5 ${needsAttention ? "items-start whitespace-normal break-words text-black/70 dark:text-white/75" : "items-center truncate text-black/50 dark:text-white/50"} text-[13px]`}>
            {receipt.channel === "whatsapp" ? (
              <MessageCircle className="h-3.5 w-3.5 shrink-0" aria-label="WhatsApp" />
            ) : receipt.channel === "email" ? (
              <Mail className="h-3.5 w-3.5 shrink-0" data-testid="inbox-channel-email" aria-label={t("business.dossier.email", "Email")} />
            ) : null}
            {receipt.attention
              ? attentionLabel(receipt.attention)
              : savedUnread(receipt)
                ? receipt.activity?.state === "saved_unread"
                  ? t("business.activity.saved_row", "Saved unread. Waiting for receipt reading.")
                  : savedUnreadLine(t, { enterable: receipt.enterable, preparable: receipt.preparable })
                : formatRelativeTime(receipt.received_at, locale)}
          </span>
          {needsAttention ? <span className="mt-2 block"><StatusPill status={receipt.status} /></span> : null}
          <RecordMarks personal={receipt.personal} fiscalValue={receipt.fiscal_value} known={receipt.fiscal_known === true} markedBy={receipt.personal_marked_by} className="mt-1" />
        </span>
        <span className="hidden text-right text-[15px] font-medium tabular-nums text-black dark:text-white mobile:block">
          {formatMoney(receipt.amount, receipt.currency, locale)}
        </span>
        {!needsAttention ? <StatusPill status={receipt.status} /> : null}
        <ChevronRight className="h-4 w-4 shrink-0 text-black/30 dark:text-white/30" />
      </button>
      {needsAttention && (receipt.enterable || (receipt.preparable && onRetry)) ? (
        <div className="w-full min-w-0 px-3 pb-3">
          {receipt.preparable && onRetry ? <p className="mb-2 text-[13px] text-black/55 dark:text-white/55">{t("business.review.retry_consent", "Trying again sends this receipt to our AI provider.")}</p> : null}
          <div className="flex flex-wrap gap-2">
            {receipt.preparable && onRetry ? <button type="button" className={secondaryButtonClass} disabled={retry === "retrying"} onClick={() => void tryAgain()}>{t("common.retry", "Retry")}</button> : null}
            {receipt.enterable ? <button type="button" className={secondaryButtonClass} disabled={retry === "retrying"} onClick={onOpen}>{locale === "es-419" ? "Escribir datos" : t("business.actions.record_expense", "Record expense")}</button> : null}
          </div>
          {retry === "failed" ? <p role="alert" className="mt-2 break-words text-[13px] text-[#a8434c] dark:text-[#ec9aa0]">{t("business.review.prepare_failed", "We couldn't start preparation. Your receipt is saved. Try again.")}</p> : null}
        </div>
      ) : null}
      {onMark && receipt.personal_editable ? (
        <button
          type="button"
          data-testid={`mark-personal-${receipt.id}`}
          aria-pressed={receipt.personal === true}
          aria-label={receipt.personal ? t("business.marks.unmark_personal_label", "No longer personal") : t("business.marks.mark_personal_label", "Mark as personal")}
          onClick={() => onMark(receipt)}
          className={`ml-auto inline-flex min-h-11 shrink-0 items-center rounded-full border px-3 text-[12px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40 ${receipt.personal ? "border-[var(--cuadrao-green)] bg-[var(--cuadrao-green)] text-[var(--cuadrao-cream)]" : "border-black/15 text-black/70 hover:bg-black/[0.04] dark:border-white/20 dark:text-white/75 dark:hover:bg-white/[0.06]"}`}
        >
          {t("business.marks.mark_personal", "Personal")}
        </button>
      ) : null}
    </li>
  );
}

/** One tap marks or unmarks; the toast offers the way back for a moment. */
export function usePersonalMark() {
  const { t } = useTranslation();
  const { source, reload } = useBusiness();
  const [toast, setToast] = useState<{ text: string; undo?: () => void } | null>(null);
  const close = useCallback(() => setToast(null), []);
  const mark = useCallback(async (receipt: ReceiptSummary) => {
    try {
      const detail = await source.receipt(receipt.id);
      const draftId = detail.draft_id;
      if (!draftId) return;
      const next = !receipt.personal;
      const marked = await source.markPersonal(draftId, detail.version, next, crypto.randomUUID());
      reload();
      setToast({
        text: next ? t("business.marks.marked_personal", "Marked as personal. It does not count in the Business totals.") : t("business.marks.unmarked_personal", "No longer personal. It counts in the totals again."),
        undo: async () => {
          setToast(null);
          try { await source.markPersonal(draftId, marked.version, !next, crypto.randomUUID()); reload(); } catch { setToast({ text: t("business.marks.mark_failed", "We could not save the change. Try again.") }); }
        },
      });
    } catch {
      setToast({ text: t("business.marks.mark_failed", "We could not save the change. Try again.") });
    }
  }, [reload, source, t]);
  return { mark, toast: toast ? <UndoToast text={toast.text} onUndo={toast.undo} onClose={close} /> : null };
}

export default function BusinessInboxPanel() {
  const { t } = useTranslation();
  const { records, openPanel, actions, panel, chosen, source, reload } = useBusiness();
  const personal = usePersonalMark();
  const items = records.inbox ? bandejaReceipts(records.inbox) : null;
  const notes = records.notes === null ? null : openNotesByDraft(records.notes);

  const upload = chosen?.role === "owner" ? actions.create.find((action) => action.id === "upload_receipt") : null;

  return (
    <section>
      <ReceiptReadingControl />
      <PanelHeading
        title={t("business.inbox.title", "Inbox")}
        subtitle={t("business.inbox.subtitle", "Receipts waiting for you to review. Nothing here is an expense until you confirm it.")}
        action={
          upload ? (
            <button type="button" data-testid="business-primary-upload" className={`${pillButtonClass} bg-[var(--cuadrao-green)] text-[var(--cuadrao-cream)]`} onClick={upload.run}>
              {upload.label}
            </button>
          ) : null
        }
      />
      <BusinessEmailDeliveries openEmailId={panel.kind === "inbox" ? panel.emailId : undefined} />
      {records.error ? (
        <p role="alert" className="text-[14px] text-black/70 dark:text-white/70">
          {t("business.inbox.error", "We couldn't load your inbox. Try again.")}
        </p>
      ) : items === null || notes === null ? (
        <LoadingRows />
      ) : items.length === 0 && notes.length === 0 && !records.notesError ? (
        <div className={`${cardClass} text-center`}>
          <p className="font-display text-[18px] font-medium text-black dark:text-white">
            {t("business.inbox.all_reviewed", "All reviewed")}
          </p>
          <p className="mt-1 text-[14px] text-black/55 dark:text-white/55">
            {t("business.inbox.empty_body", "Upload a receipt or send one by WhatsApp. It will wait here for your review.")}
          </p>
        </div>
      ) : (
        <>
          <NotesAwaitingReview notes={notes} error={records.notesError} truncated={records.notesTruncated} onOpen={(draftId) => openPanel({ kind: "draft", draftId })} />
          {items.length ? (
            <ul data-testid="business-inbox-receipts" className={`${cardClass} divide-y divide-black/[0.05] p-2 dark:divide-white/[0.05]`}>
              {items.map((receipt) => (
                <ReceiptRow
                  key={receipt.id}
                  receipt={receipt}
                  onOpen={() => openPanel({ kind: "receipt", receiptId: receipt.id })}
                  onMark={personal.mark}
                  onRetry={async () => {
                    try { await source.prepareReceipt(receipt.id); } finally { reload(); }
                  }}
                />
              ))}
            </ul>
          ) : null}
        </>
      )}
      {personal.toast}
    </section>
  );
}
