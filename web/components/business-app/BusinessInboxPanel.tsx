"use client";

import { useEffect, useRef, useState } from "react";
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
import { bandejaEmails, openNotesByDraft, type BandejaEmail, type OpenNote } from "./inbox-count";
import { bandejaCounts, sourceLoad, type BandejaSource, type LoadFailure } from "./bandeja-sources";
import { useOnline } from "@/components/ui/ConnectionBanner";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { formatMoney, formatRelativeTime, UNKNOWN_VALUE } from "./business-format";
import { canAddRecords, cardClass, PanelHeading, primaryButtonClass, quietButtonClass, recordFiscalMark } from "./business-ui";
import { ListPager } from "./foundation/ListPager";
import BusinessAddMenu from "./BusinessAddMenu";
import { EmptyState } from "./foundation/EmptyState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { PullToRefresh } from "@/components/ui/PullToRefresh";
import { Settle } from "./business-skeletons";
import { showToast } from "./foundation/toasts";
import { resolveLanguage } from "@/lib/language-features";

export { inboxCount, openNotesByDraft, type OpenNote } from "./inbox-count";

type ListKey = "review" | "problem" | "all";

/**
 * A Bandeja row is what arrived: a receipt, a typed note awaiting review, or
 * an email that is still being read or brought no receipt. Each opens its record.
 */
type BandejaItem = { kind: "receipt"; receipt: ReceiptSummary } | { kind: "note"; note: OpenNote } | { kind: "email"; email: BandejaEmail };

const itemTime = (item: BandejaItem) => (item.kind === "receipt" ? item.receipt.received_at : item.kind === "note" ? item.note.receivedAt : item.email.delivery.received_at);
const itemNew = (item: BandejaItem) => item.kind === "receipt" && Boolean(item.receipt.activity?.unread);

/** What each segment keeps of each kind: a receipt by the server's flag for that segment, so each list is exactly what its number counts. */
const SEGMENT: Record<ListKey, { receipt: (receipt: ReceiptSummary) => boolean; notes: boolean; email: (email: BandejaEmail) => boolean }> = {
  // Anything still being read, receipt or email, waits under Todo.
  review: { receipt: (receipt) => receipt.bandeja?.por_revisar === true, notes: true, email: () => false },
  problem: { receipt: (receipt) => receipt.bandeja?.con_problema === true, notes: false, email: (email) => email.standing === "no_receipt" },
  all: { receipt: () => true, notes: true, email: () => true },
};

/** The rows a segment shows, newest first. */
export function bandejaRows(list: ListKey, receipts: readonly ReceiptSummary[], notes: readonly OpenNote[], emails: readonly BandejaEmail[] = []): BandejaItem[] {
  const segment = SEGMENT[list];
  const rows: BandejaItem[] = [
    ...receipts.filter(segment.receipt).map((receipt) => ({ kind: "receipt" as const, receipt })),
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
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const stateWord = useReceiptStateWord();
  const Icon = receipt.media_type === "application/pdf" ? FileText : ImageIcon;
  const problem = receipt.status === "needs_attention";
  const reading = receipt.bandeja?.leyendo === true;
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
            <span className={`shrink-0 text-right text-[15px] font-medium tabular-nums text-[#172b26] dark:text-white ${money ? "cuadrao-amount" : ""}`}>{money || UNKNOWN_VALUE}</span>
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
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  return (
    <li aria-current={open ? "true" : undefined} data-testid="bandeja-note" className={`rounded-item ${OPEN_ROW_CLASS}`}>
      <button type="button" onClick={onOpen} className="flex w-full min-w-0 items-center gap-3 rounded-item px-3 py-3 text-left transition-colors hover:bg-black/[0.03] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#2f5a49] dark:hover:bg-white/[0.04]">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-item bg-black/[0.04] dark:bg-white/[0.06]"><NotebookPen className="h-5 w-5 text-[#56635e] dark:text-white/60" aria-hidden="true" /></span>
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 truncate text-[15px] font-medium text-[#172b26] dark:text-white">{note.text.trim()}</span>
            <span className="shrink-0 text-right text-[15px] tabular-nums text-[#56635e]"><span aria-hidden="true">{UNKNOWN_VALUE}</span><span className="sr-only">{t("business.dossier.unknown_amount", "Amount unknown")}</span></span>
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
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
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

/** "All approved" is the server's counts saying so: nothing waits, and every receipt that left was saved, none dismissed. */
function EmptyInbox({ upload }: { upload: { label: string; run: () => void } | null }) {
  const { t } = useTranslation();
  const { records } = useBusiness();
  const activity = records.receiptActivity;
  const approved = !records.notesTruncated && activity?.pending_review_count === 0 && (activity.confirmed_count ?? 0) > 0 && activity.dismissed_count === 0;
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
 * One line for every list that did not load, with one Reintentar that asks
 * again for only those lists. Offline is the connection banner's to say: the
 * line stays away and the lists are asked again when the connection is back.
 */
function SourcesFailed({ failed, retry }: { failed: readonly { source: BandejaSource; failure: LoadFailure }[]; retry: () => void }) {
  const { t } = useTranslation();
  const online = useOnline();
  const wasOnline = useRef(online);
  useEffect(() => {
    if (online && !wasOnline.current && failed.length) retry();
    wasOnline.current = online;
  }, [online, failed.length, retry]);
  const said = failed.filter((item) => !item.failure.offline);
  if (!said.length) return null;
  const notes = said.some((item) => item.source === "notes");
  const emails = said.some((item) => item.source === "emails");
  const reference = said.find((item) => item.failure.reference)?.failure.reference;
  return (
    <div role="alert" data-testid="bandeja-sources-failed" className="mb-4 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-item border border-[#9e2f39]/30 bg-[#f6dfe0]/50 py-1 pl-3.5 pr-2 text-[14px] text-[#9e2f39] dark:border-[#ec9aa0]/30 dark:bg-[#ec9aa0]/10 dark:text-[#ec9aa0]">
      <p className="min-w-0 py-2">
        {notes && emails ? t("business.inbox.failed_notes_emails", "We couldn't load your notes or your emails.") : notes ? t("business.inbox.failed_notes", "We couldn't load your notes.") : t("business.inbox.failed_emails", "We couldn't load your emails.")}
        {reference ? <span className="ml-2 inline-flex align-middle"><ReferenceCode reference={reference} /></span> : null}
      </p>
      <button type="button" onClick={retry} className={`${quietButtonClass} px-3`}>{t("common.retry", "Retry")}</button>
    </div>
  );
}

/**
 * The one place receipts wait. Three segments split the same rows: what to
 * review, what has a problem, and everything that arrived. What arrived since
 * the last visit sits on top. An email is only how a receipt arrived: it is a
 * row of its own only while it is read or when it brought no receipt.
 * The rows come from three lists. While one is loading nothing claims to be
 * empty; when one failed the screen says so once and claims no empty state.
 */
export default function BusinessInboxPanel() {
  const { t } = useTranslation();
  const { isBelowTablet } = useResponsiveLayout();
  const { records, openPanel, actions, panel, chosen, revision, reload, refresh, retrySources } = useBusiness();
  const loads = { receipts: sourceLoad(records.inbox, null), notes: sourceLoad(records.notes, records.notesFailure), emails: sourceLoad(records.emails, records.emailsFailure) };
  const failed = (["notes", "emails"] as const).flatMap((source) => {
    const load = loads[source];
    return load.state === "failed" ? [{ source, failure: load.failure }] : [];
  });
  const retryFailed = () => retrySources(failed.map((item) => item.source));
  const pending = Object.values(loads).some((load) => load.state === "loading");
  const receipts = bandejaReceipts(records.inbox ?? []);
  const notes = openNotesByDraft(records.notes ?? []);
  const emails = bandejaEmails(records.emails ?? []);
  const uploadAction = actions.create.find((action) => action.id === "upload_receipt");
  const upload = canAddRecords(chosen) ? uploadAction : null;
  const [list, setList] = useState<ListKey>("review");
  const empty = !pending && !failed.length && receipts.length === 0 && notes.length === 0 && emails.length === 0;
  const counts = bandejaCounts(loads, records);
  const rows = pending ? null : bandejaRows(list, receipts, notes, emails);
  const fresh = rows?.filter(itemNew) ?? [];
  const earlier = rows?.filter((row) => !itemNew(row)) ?? [];
  const openReview = () => {
    const next = receipts.find((receipt) => receipt.bandeja?.por_revisar);
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
    <PullToRefresh onRefresh={refresh}>
      <section className="@container">
        {isBelowTablet && !empty ? <div className="mb-4"><BusinessAddMenu placement="page" /></div> : null}
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
        <ReceiptReadingControl />
        {records.error ? (
          <EmptyState kind="error" testId="business-inbox-error" title={t("business.empty.inbox_error", "We couldn't load your inbox")} body={t("business.empty.error_body", "Your data is still saved. Check your connection and try again.")} action={{ label: t("common.retry", "Retry"), run: reload }} />
        ) : (
          <>
            <div className="mb-4">
              {/* A phone fits all three only with their short names. */}
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
            <SourcesFailed failed={failed} retry={retryFailed} />
            <Settle pending={rows === null} layout="inbox">
              {rows === null ? null : empty ? (
                <EmptyInbox key={`${chosen?.space_id ?? "own"}:${revision}`} upload={upload ? { label: upload.label, run: upload.run } : null} />
              ) : (
                <>
                  {rows.length ? (
                    <div className={`${cardClass} p-2`} data-testid="business-inbox-receipts">
                      {group(t("business.inbox.group_new", "New since your last visit"), fresh, "bandeja-new")}
                      {group(t("business.inbox.group_earlier", "Earlier"), earlier, "bandeja-earlier")}
                    </div>
                  ) : failed.length ? null : (
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
    </PullToRefresh>
  );
}
