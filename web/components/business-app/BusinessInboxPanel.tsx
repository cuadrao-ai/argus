"use client";

import { useEffect, useState } from "react";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { ChevronRight, FileText, ImageIcon, Mail, MessageCircle, NotebookPen } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import ReceiptReadingControl from "./ReceiptReadingControl";
import { useEmailWords } from "./BusinessEmailDeliveries";
import { useReceiptStateWord } from "./receipt-state-word";
import { useBusiness } from "./BusinessWorkspace";
import { bandejaReceipts } from "./bandeja-order";
import { isOpenRecord, OPEN_ROW_CLASS } from "./record-tray";
import { isStillReading, needsAttention, porRevisar } from "@/lib/business-review-count";
import { bandejaEmails, inboxCount, openNotesByDraft, problemCount, type BandejaEmail, type OpenNote } from "./inbox-count";
import { formatMoney, formatRelativeTime } from "./business-format";
import { cardClass, PanelHeading, primaryButtonClass, quietButtonClass, recordFiscalMark } from "./business-ui";
import { ListPager } from "./foundation/ListPager";
import BusinessAddMenu from "./BusinessAddMenu";
import { EmptyState } from "./foundation/EmptyState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Settle } from "./business-skeletons";
import { showToast } from "./foundation/toasts";

export { inboxCount, openNotesByDraft, type OpenNote } from "./inbox-count";

type ListKey = "review" | "problem" | "all";

/**
 * A Bandeja row is what arrived: a receipt, a typed note awaiting review, or
 * an email that is still being read or brought no receipt. Each opens its record.
 */
type BandejaItem = { kind: "receipt"; receipt: ReceiptSummary } | { kind: "note"; note: OpenNote } | { kind: "email"; email: BandejaEmail };

const itemTime = (item: BandejaItem) => (item.kind === "receipt" ? item.receipt.received_at : item.kind === "note" ? item.note.receivedAt : item.email.delivery.received_at);
const itemNew = (item: BandejaItem) => item.kind === "receipt" && Boolean(item.receipt.activity?.unread);

/** What each segment keeps of each kind. Por revisar's count is the one review count every screen shares. */
const SEGMENT: Record<ListKey, { receipts: (receipts: readonly ReceiptSummary[]) => readonly ReceiptSummary[]; notes: boolean; email: (email: BandejaEmail) => boolean }> = {
  // Anything still being read, receipt or email, waits under Todo; Por revisar lists exactly what its number counts.
  review: { receipts: porRevisar, notes: true, email: () => false },
  problem: { receipts: (receipts) => receipts.filter(needsAttention), notes: false, email: (email) => email.standing === "no_receipt" },
  all: { receipts: (receipts) => receipts, notes: true, email: () => true },
};

/** The rows a segment shows, newest first. */
export function bandejaRows(list: ListKey, receipts: readonly ReceiptSummary[], notes: readonly OpenNote[], emails: readonly BandejaEmail[] = []): BandejaItem[] {
  const segment = SEGMENT[list];
  const rows: BandejaItem[] = [
    ...segment.receipts(receipts).map((receipt) => ({ kind: "receipt" as const, receipt })),
    ...(segment.notes ? notes.map((note) => ({ kind: "note" as const, note })) : []),
    ...emails.filter(segment.email).map((email) => ({ kind: "email" as const, email })),
  ];
  return rows.sort((a, b) => (itemTime(a) < itemTime(b) ? 1 : -1));
}

/**
 * One quiet line per receipt: what it is, where it stands, the total and its
 * type. Fixing a problem happens in the record, so the row only opens it.
 */
export function ReceiptRow({ receipt, open = false, onOpen }: { receipt: ReceiptSummary; open?: boolean; onOpen: () => void }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const stateWord = useReceiptStateWord();
  const Icon = receipt.media_type === "application/pdf" ? FileText : ImageIcon;
  const problem = receipt.status === "needs_attention";
  const reading = isStillReading(receipt);
  const fiscalMark = recordFiscalMark(receipt);
  const marks = [
    receipt.personal ? t("business.marks.personal_chip", "Personal") : null,
    fiscalMark === "sin_comprobante" ? t("business.marks.sin_comprobante_chip", "No comprobante") : fiscalMark === "missing_ncf" ? t("business.marks.missing_ncf_chip", "NCF missing") : null,
  ].filter(Boolean);
  const state = stateWord(receipt);
  const money = formatMoney(receipt.amount, receipt.currency, locale);
  return (
    <li aria-current={open ? "true" : undefined} data-testid="bandeja-row" data-new={receipt.activity?.unread ? "true" : undefined} className={`rounded-item ${OPEN_ROW_CLASS}`}>
      <button type="button" onClick={onOpen} className="flex w-full min-w-0 items-center gap-3 rounded-item px-3 py-3 text-left transition-colors hover:bg-black/[0.03] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#2f5a49] dark:hover:bg-white/[0.04]">
        <span className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-item bg-black/[0.04] dark:bg-white/[0.06]">
          {reading ? <span aria-hidden="true" data-testid="receipt-reading-ring" className="absolute inset-0 rounded-item border-2 border-[#2f5a49]/50 border-t-transparent motion-safe:animate-spin" /> : null}
          {receipt.activity?.unread && !reading ? <span data-testid="receipt-unread-dot" className="absolute -left-1 -top-1 h-2.5 w-2.5 rounded-full border-2 border-[#FFFEFA] bg-[#2f5a49] dark:border-[#1f2225]"><span className="sr-only">{t("business.inbox.row_new", "New")}</span></span> : null}
          <Icon className="h-5 w-5 text-[#56635e] dark:text-white/60" aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 truncate text-[15px] font-medium text-[#172b26] dark:text-white">{receipt.merchant ?? receipt.filename ?? t("business.receipt.untitled", "Receipt")}</span>
            <span className={`shrink-0 text-right text-[15px] font-medium tabular-nums text-[#172b26] dark:text-white ${money ? "cuadrao-amount" : ""}`}>{money || "—"}</span>
          </span>
          <span className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[13px]">
            {receipt.channel === "whatsapp" ? <MessageCircle className="h-3.5 w-3.5 shrink-0 text-[#56635e]" aria-label="WhatsApp" /> : receipt.channel === "email" ? <Mail className="h-3.5 w-3.5 shrink-0 text-[#56635e]" data-testid="inbox-channel-email" aria-label={t("business.dossier.email", "Email")} /> : null}
            <span data-testid="bandeja-row-state" className={`line-clamp-2 @md:truncate ${problem ? "font-medium text-[#9e2f39] dark:text-[#ec9aa0]" : "text-[#56635e] dark:text-white/65"}`}>
              {[state, formatRelativeTime(receipt.received_at, locale), ...marks].filter(Boolean).join(" · ")}
            </span>
          </span>
        </span>
        {/* A problem receipt has no read type yet; the column stays for alignment. */}
        <span data-testid="bandeja-row-type" className="hidden w-16 shrink-0 text-right text-[13px] text-[#56635e] @md:block dark:text-white/65">
          {problem ? null : receipt.document_type === "venta" ? t("business.intake.type_venta", "Sale") : t("business.intake.type_recibo", "Purchase")}
        </span>
        <ChevronRight className="h-4 w-4 shrink-0 text-black/30 dark:text-white/30" aria-hidden="true" />
      </button>
    </li>
  );
}

function NoteRow({ note, open, onOpen }: { note: OpenNote; open: boolean; onOpen: () => void }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  return (
    <li aria-current={open ? "true" : undefined} data-testid="bandeja-note" className={`rounded-item ${OPEN_ROW_CLASS}`}>
      <button type="button" onClick={onOpen} className="flex w-full min-w-0 items-center gap-3 rounded-item px-3 py-3 text-left transition-colors hover:bg-black/[0.03] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#2f5a49] dark:hover:bg-white/[0.04]">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-item bg-black/[0.04] dark:bg-white/[0.06]"><NotebookPen className="h-5 w-5 text-[#56635e] dark:text-white/60" aria-hidden="true" /></span>
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 truncate text-[15px] font-medium text-[#172b26] dark:text-white">{note.text.trim()}</span>
            <span className="shrink-0 text-right text-[15px] tabular-nums text-[#56635e]">—</span>
          </span>
          <span className="mt-0.5 block truncate text-[13px] text-[#56635e] dark:text-white/65">
            {[t("business.inbox.row_note", "Typed note"), formatRelativeTime(note.receivedAt, locale), note.earlier ? t("business.inbox.note_more", "{{count}} earlier notes", { count: note.earlier }) : null].filter(Boolean).join(" · ")}
          </span>
        </span>
        <ChevronRight className="h-4 w-4 shrink-0 text-black/30 dark:text-white/30" aria-hidden="true" />
      </button>
    </li>
  );
}

/**
 * An email as a row: who sent it, its subject and where it stands. Being read
 * reads like a receipt being read; with no receipt it says why in red, and
 * Reintentar sits on the row when the server allows a retry.
 */
function EmailRow({ email, open, onOpen }: { email: BandejaEmail; open: boolean; onOpen: () => void }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const { source, emailRefresh } = useBusiness();
  const words = useEmailWords();
  const [retrying, setRetrying] = useState(false);
  const [retryFailed, setRetryFailed] = useState(false);
  const { delivery, standing } = email;
  const reading = standing === "reading";
  const state = reading ? (delivery.waiting ? t("business.email.waiting_label", "Waiting until tomorrow") : t("business.inbox.row_reading", "Reading…")) : words.noReceipt(delivery);
  const retry = async () => {
    setRetrying(true);
    setRetryFailed(false);
    try {
      await source.retryEmailDelivery(delivery.id);
      showToast({ kind: "info", text: t("business.email.retry_accepted", "Retry requested. The status updates after processing.") });
      emailRefresh.refresh();
    } catch {
      setRetryFailed(true);
    } finally {
      setRetrying(false);
    }
  };
  return (
    <li aria-current={open ? "true" : undefined} data-testid="bandeja-email" data-standing={standing} className={`flex flex-wrap items-center gap-1 rounded-item ${OPEN_ROW_CLASS}`}>
      <button type="button" onClick={onOpen} className="flex min-w-0 flex-1 items-center gap-3 rounded-item px-3 py-3 text-left transition-colors hover:bg-black/[0.03] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#2f5a49] dark:hover:bg-white/[0.04]">
        <span className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-item bg-black/[0.04] dark:bg-white/[0.06]">
          {reading && !delivery.waiting ? <span aria-hidden="true" data-testid="receipt-reading-ring" className="absolute inset-0 rounded-item border-2 border-[#2f5a49]/50 border-t-transparent motion-safe:animate-spin" /> : null}
          <Mail className="h-5 w-5 text-[#56635e] dark:text-white/60" aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block min-w-0 truncate text-[15px] font-medium text-[#172b26] dark:text-white">{words.title(delivery)}</span>
          <span data-testid="bandeja-row-state" className={`mt-0.5 block line-clamp-2 text-[13px] @md:truncate ${reading ? "text-[#56635e] dark:text-white/65" : "font-medium text-[#9e2f39] dark:text-[#ec9aa0]"}`}>
            {/* The reason is a sentence elsewhere; on the row it is one clause among others. */}
            {[words.subject(delivery), state.replace(/\.$/, ""), formatRelativeTime(delivery.received_at, locale)].join(" · ")}
          </span>
        </span>
        {reading || !delivery.retryable ? <ChevronRight className="h-4 w-4 shrink-0 text-black/30 dark:text-white/30" aria-hidden="true" /> : null}
      </button>
      {!reading && delivery.retryable ? (
        <button type="button" disabled={retrying} onClick={() => void retry()} className={`${quietButtonClass} mr-2 shrink-0 px-3`}>
          {retrying ? t("business.email.retrying", "Requesting…") : t("business.email.retry", "Try again")}
        </button>
      ) : null}
      {retryFailed ? <p role="alert" data-testid="bandeja-email-retry-error" className="w-full px-3 pb-2 text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.email.retry_failed", "Could not request a retry. Saved attachments are unchanged.")}</p> : null}
    </li>
  );
}

function EmptyInbox({ upload }: { upload: { label: string; run: () => void } | null }) {
  const { t } = useTranslation();
  const { source, records } = useBusiness();
  const [proof, setProof] = useState<{ source: typeof source; activity: typeof records.receiptActivity; approved: boolean } | null>(null);
  const approved = !records.notesTruncated && proof?.source === source && proof.activity === records.receiptActivity && proof.approved;
  useEffect(() => {
    let current = true;
    if (records.notesTruncated || records.receiptActivity?.pending_review_count !== 0 || !source.receiptPage) return;
    const controller = new AbortController();
    source.receiptPage("all", controller.signal).then((page) => {
      const receipts = bandejaReceipts(page.items);
      if (current) setProof({ source, activity: records.receiptActivity, approved: page.activity?.pending_review_count === 0 && receipts.length > 0 && receipts.every((receipt) => receipt.status === "confirmed") });
    }).catch(() => undefined);
    return () => { current = false; controller.abort(); };
  }, [source, records.receiptActivity, records.notesTruncated]);
  return (
    <div data-testid="business-inbox-empty" className={cardClass}>
      {approved ? (
        <EmptyState kind="first_run" mark="check" compact title={t("business.empty.all_clear_title", "All approved. Squared away.")} body={t("business.empty.all_clear_body", "When another receipt arrives, it shows up here for review.")} action={upload ?? undefined} />
      ) : (
        <EmptyState kind="first_run" mark="inbox" compact title={t("business.empty.inbox_title", "Your receipts land here")} body={t("business.empty.inbox_body", "Upload, type or forward them by email. You review and approve them so they count in your numbers.")} action={upload ?? undefined} />
      )}
    </div>
  );
}

const INBOX_PAGE = 8;

/**
 * The one place receipts wait. Three segments split the same rows: what to
 * review, what has a problem, and everything that arrived. What arrived since
 * the last visit sits on top. An email is only how a receipt arrived: it is a
 * row of its own only while it is read or when it brought no receipt.
 */
export default function BusinessInboxPanel() {
  const { t } = useTranslation();
  const { isBelowTablet } = useResponsiveLayout();
  const { records, openPanel, actions, panel, chosen, revision, reload } = useBusiness();
  const receipts = records.inbox ? bandejaReceipts(records.inbox) : null;
  const notes = records.notes === null ? null : openNotesByDraft(records.notes);
  const uploadAction = actions.create.find((action) => action.id === "upload_receipt");
  const upload = chosen?.role === "owner" ? uploadAction : null;
  const emails = records.emails ? bandejaEmails(records.emails) : [];
  const [list, setList] = useState<ListKey>("review");
  const empty = receipts !== null && notes !== null && receipts.length === 0 && notes.length === 0 && emails.length === 0 && !records.notesError && !records.error;
  // A count waits for its lists, never a 0.
  const counts = { review: inboxCount(records) ?? undefined, problem: problemCount(records) ?? undefined };
  const rows = receipts && notes ? bandejaRows(list, receipts, notes, emails) : null;
  const fresh = rows?.filter(itemNew) ?? [];
  const earlier = rows?.filter((row) => !itemNew(row)) ?? [];
  const openReview = () => {
    const next = porRevisar(receipts ?? [])[0];
    if (next) openPanel({ kind: "receipt", receiptId: next.id, list: "inbox" });
  };
  const renderRow = (row: BandejaItem) => {
    if (row.kind === "receipt") return <ReceiptRow key={row.receipt.id} receipt={row.receipt} open={isOpenRecord(panel, { kind: "receipt", receiptId: row.receipt.id })} onOpen={() => openPanel({ kind: "receipt", receiptId: row.receipt.id, list: "inbox" })} />;
    if (row.kind === "note") return <NoteRow key={row.note.draftId} note={row.note} open={isOpenRecord(panel, { kind: "draft", draftId: row.note.draftId })} onOpen={() => openPanel({ kind: "draft", draftId: row.note.draftId, list: "inbox" })} />;
    const target = { kind: "email" as const, emailId: row.email.delivery.id };
    return <EmailRow key={target.emailId} email={row.email} open={isOpenRecord(panel, target)} onOpen={() => openPanel(target)} />;
  };
  const group = (title: string, items: BandejaItem[], testId: string) => items.length ? (
    <div data-testid={testId}>
      {fresh.length ? <h3 className="px-3 pb-1 pt-3 text-[12px] font-medium text-[#7d8a84] dark:text-white/50">{title}</h3> : null}
      <ListPager items={items} pageSize={INBOX_PAGE} revealLabel={t("business.inbox.reveal_more", "Ver más")} loadLabel={t("business.inbox.load_more", "Cargar más")} retryLabel={t("common.retry", "Reintentar")} listClassName="divide-y divide-[#EEF0EC] dark:divide-white/[0.06]" renderItem={renderRow} />
    </div>
  ) : null;

  return (
    <section className="@container">
      {isBelowTablet && !empty ? <div className="mb-4"><BusinessAddMenu placement="page" /></div> : null}
      <ReceiptReadingControl hideWhenEnabled />
      <PanelHeading
        title={t("business.inbox.title", "Inbox")}
        action={
          chosen?.role === "accountant" ? (
            <button type="button" data-testid="business-primary-review" onClick={openReview} className={primaryButtonClass}>
              {t("business.inbox.review_receipts", "Revisar recibos")}
            </button>
          ) : null
        }
      />
      {records.error ? (
        <EmptyState kind="error" testId="business-inbox-error" title={t("business.empty.inbox_error", "We couldn't load your inbox")} body={t("business.empty.error_body", "Your data is still saved. Check your connection and try again.")} action={{ label: t("common.retry", "Retry"), run: reload }} />
      ) : (
        <>
          <div className="mb-4">
            {/* A phone fits all three only with their short names. Counts wait for the list, never a 0. */}
            <SegmentedControl
              testId="bandeja-segments"
              label={t("business.inbox.segments", "Show")}
              value={list}
              onChange={setList}
              fill={isBelowTablet}
              segments={[
                { key: "review", label: isBelowTablet ? t("business.inbox.segment_review_short", "Review") : t("business.inbox.segment_review", "To review"), count: counts.review },
                { key: "problem", label: isBelowTablet ? t("business.inbox.segment_problem_short", "Issues") : t("business.inbox.segment_problem", "Problems"), count: counts.problem },
                { key: "all", label: t("business.inbox.segment_all", "All") },
              ]}
            />
          </div>
          <Settle pending={receipts === null || notes === null} layout="inbox">
            {rows === null ? null : empty ? (
              <EmptyInbox key={`${chosen?.space_id ?? "own"}:${revision}`} upload={upload ? { label: upload.label, run: upload.run } : null} />
            ) : (
              <>
                {records.notesError ? <p role="alert" className="mb-3 text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.empty.notes_error", "We couldn't load your notes")}</p> : null}
                {records.emailsError ? <p role="alert" data-testid="bandeja-emails-error" className="mb-3 text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.empty.email_error", "We couldn't load your emails")}</p> : null}
                {rows.length ? (
                  <div className={`${cardClass} p-2`} data-testid="business-inbox-receipts">
                    {group(t("business.inbox.group_new", "New since your last visit"), fresh, "bandeja-new")}
                    {group(t("business.inbox.group_earlier", "Earlier"), earlier, "bandeja-earlier")}
                  </div>
                ) : (
                  <div className={cardClass} data-testid="bandeja-segment-empty">
                    <EmptyState kind="filtered" mark={list === "problem" ? "check" : "inbox"} compact
                      title={list === "problem" ? t("business.inbox.no_problems", "No receipts with problems") : t("business.inbox.nothing_to_review", "Nothing to review")}
                      body={t("business.inbox.see_all_body", "Every receipt you have is under All.")}
                      action={{ label: t("business.inbox.see_all", "See all"), run: () => setList("all") }} />
                  </div>
                )}
                {records.notesTruncated ? <p className="mt-2 text-[13px] text-[#56635e] dark:text-white/65">{t("business.inbox.notes_latest", "Showing the latest 50 saved notes. Older open notes are reachable through search.")}</p> : null}
              </>
            )}
          </Settle>
        </>
      )}
    </section>
  );
}
