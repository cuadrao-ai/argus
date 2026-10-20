"use client";

import { useEffect, useState } from "react";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { ChevronRight, FileText, ImageIcon, Mail, MessageCircle, NotebookPen } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import ReceiptReadingControl from "./ReceiptReadingControl";
import BusinessEmailDeliveries from "./BusinessEmailDeliveries";
import { useReceiptStateWord } from "./receipt-state-word";
import { useBusiness } from "./BusinessWorkspace";
import { bandejaReceipts } from "./bandeja-order";
import { isOpenRecord, OPEN_ROW_CLASS } from "./record-tray";
import { countNeedsAttention, isStillReading, needsAttention, porRevisar } from "@/lib/business-review-count";
import { inboxCount, openNotesByDraft, type OpenNote } from "./inbox-count";
import { formatMoney, formatRelativeTime } from "./business-format";
import { cardClass, PanelHeading, recordFiscalMark } from "./business-ui";
import { ListPager } from "./foundation/ListPager";
import BusinessAddMenu from "./BusinessAddMenu";
import { EmptyState } from "./foundation/EmptyState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Settle } from "./business-skeletons";

export { inboxCount, openNotesByDraft, type OpenNote } from "./inbox-count";

type ListKey = "review" | "problem" | "all" | "emails";

/** A Bandeja row is a receipt or a typed note awaiting review; both open their record. */
type BandejaItem = { kind: "receipt"; receipt: ReceiptSummary } | { kind: "note"; note: OpenNote };

const itemTime = (item: BandejaItem) => (item.kind === "receipt" ? item.receipt.received_at : item.note.receivedAt);
const itemNew = (item: BandejaItem) => item.kind === "receipt" && Boolean(item.receipt.activity?.unread);

/** The rows a segment shows, newest first. "Por revisar" is the one review count every screen shares. */
export function bandejaRows(list: ListKey, receipts: readonly ReceiptSummary[], notes: readonly OpenNote[]): BandejaItem[] {
  if (list === "emails") return [];
  const picked = list === "review" ? porRevisar(receipts) : list === "problem" ? receipts.filter(needsAttention) : receipts;
  const rows: BandejaItem[] = [...picked.map((receipt) => ({ kind: "receipt" as const, receipt })), ...(list === "problem" ? [] : notes.map((note) => ({ kind: "note" as const, note })))];
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
    <li aria-current={open ? "true" : undefined} data-testid="bandeja-row" data-new={receipt.activity?.unread ? "true" : undefined} className={`rounded-[12px] ${OPEN_ROW_CLASS}`}>
      <button type="button" onClick={onOpen} className="flex w-full min-w-0 items-center gap-3 rounded-[12px] px-3 py-3 text-left transition-colors hover:bg-black/[0.03] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#2f5a49] dark:hover:bg-white/[0.04]">
        <span className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-[8px] bg-black/[0.04] dark:bg-white/[0.06]">
          {reading ? <span aria-hidden="true" data-testid="receipt-reading-ring" className="absolute inset-0 rounded-[8px] border-2 border-[#2f5a49]/50 border-t-transparent motion-safe:animate-spin" /> : null}
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
    <li aria-current={open ? "true" : undefined} data-testid="bandeja-note" className={`rounded-[12px] ${OPEN_ROW_CLASS}`}>
      <button type="button" onClick={onOpen} className="flex w-full min-w-0 items-center gap-3 rounded-[12px] px-3 py-3 text-left transition-colors hover:bg-black/[0.03] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#2f5a49] dark:hover:bg-white/[0.04]">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[8px] bg-black/[0.04] dark:bg-white/[0.06]"><NotebookPen className="h-5 w-5 text-[#56635e] dark:text-white/60" aria-hidden="true" /></span>
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
 * review, what has a problem, and everything. What arrived since the last
 * visit sits on top. Email lives one tap away, behind Ver correos.
 */
export default function BusinessInboxPanel() {
  const { t } = useTranslation();
  const { isBelowTablet } = useResponsiveLayout();
  const { records, openPanel, actions, panel, chosen, revision, reload } = useBusiness();
  const receipts = records.inbox ? bandejaReceipts(records.inbox) : null;
  const notes = records.notes === null ? null : openNotesByDraft(records.notes);
  const uploadAction = actions.create.find((action) => action.id === "upload_receipt");
  const upload = chosen?.role === "owner" ? uploadAction : null;
  const askedEmail = panel.kind === "inbox" ? panel.emailId : undefined;
  const askedEmails = panel.kind === "inbox" && (panel.segment === "emails" || Boolean(panel.emailId));
  const [list, setList] = useState<ListKey>(askedEmails ? "emails" : "review");
  // Ver correos (the top bar, search) and a record's "first email" link ask again each time, even with the Bandeja on screen.
  useEffect(() => { if (askedEmails) setList("emails"); }, [askedEmails, askedEmail, panel]);
  const empty = receipts !== null && notes !== null && receipts.length === 0 && notes.length === 0 && !records.notesError && !records.error;
  const review = inboxCount(records);
  const counts = receipts && notes && review !== null ? { review, problem: countNeedsAttention(receipts) } : null;
  const rows = receipts && notes ? bandejaRows(list, receipts, notes) : null;
  const fresh = rows?.filter(itemNew) ?? [];
  const earlier = rows?.filter((row) => !itemNew(row)) ?? [];
  const openReview = () => {
    const next = porRevisar(receipts ?? [])[0];
    if (next) openPanel({ kind: "receipt", receiptId: next.id, list: "inbox" });
  };
  const renderRow = (row: BandejaItem) => row.kind === "receipt" ? (
    <ReceiptRow key={row.receipt.id} receipt={row.receipt} open={isOpenRecord(panel, { kind: "receipt", receiptId: row.receipt.id })} onOpen={() => openPanel({ kind: "receipt", receiptId: row.receipt.id, list: "inbox" })} />
  ) : (
    <NoteRow key={row.note.draftId} note={row.note} open={isOpenRecord(panel, { kind: "draft", draftId: row.note.draftId })} onOpen={() => openPanel({ kind: "draft", draftId: row.note.draftId, list: "inbox" })} />
  );
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
            <button type="button" data-testid="business-primary-review" onClick={openReview} className="inline-flex min-h-11 items-center justify-center rounded-full bg-[var(--cuadrao-green)] px-5 text-[16px] font-medium text-[#fffefa] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49]">
              {t("business.inbox.review_receipts", "Revisar recibos")}
            </button>
          ) : null
        }
      />
      {records.error ? (
        <EmptyState kind="error" testId="business-inbox-error" title={t("business.empty.inbox_error", "We couldn't load your inbox")} body={t("business.empty.error_body", "Your data is still saved. Check your connection and try again.")} action={{ label: t("common.retry", "Retry"), run: reload }} />
      ) : (
        <Settle pending={receipts === null || notes === null} layout="inbox">
          {rows === null || counts === null ? null : (
            <>
              <div className="mb-4">
                {/* A phone fits all four only with their short names. */}
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
                    { key: "emails", label: t("business.inbox.segment_emails", "Emails") },
                  ]}
                />
              </div>
              {list === "emails" ? (
                <BusinessEmailDeliveries
                  openEmailId={askedEmail}
                  onOpenReceipt={(id) => openPanel({ kind: "receipt", receiptId: id, list: "inbox" })}
                />
              ) : empty ? (
                <EmptyInbox key={`${chosen?.space_id ?? "own"}:${revision}`} upload={upload ? { label: upload.label, run: upload.run } : null} />
              ) : (
                <>
                  {records.notesError ? <p role="alert" className="mb-3 text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.empty.notes_error", "We couldn't load your notes")}</p> : null}
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
            </>
          )}
        </Settle>
      )}
    </section>
  );
}
