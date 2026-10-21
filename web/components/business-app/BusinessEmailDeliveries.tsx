"use client";

import { useEffect, useState } from "react";
import { ArrowLeft, ChevronRight, FileText, Mail, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import type { ReceiptSummary } from "@/lib/business-api";
import type { BusinessEmailDelivery, BusinessEmailDetail, BusinessEmailIntake, BusinessEmailPart } from "@/lib/business-email";
import { businessReceivingAddress } from "@/lib/business-email";
import { useBusiness } from "./BusinessWorkspace";
import { useRecordTray } from "./record-tray";
import { savedUnread, savedUnreadLine } from "./ReceiptReadNotice";
import { formatRelativeTime } from "./business-format";
import { Settle } from "./business-skeletons";
import { cardClass, primaryButtonClass, quietButtonClass, secondaryButtonClass } from "./business-ui";
import { CopyButton, useCopyLabels, WrappingAddress } from "./foundation/CopyButton";
import { EmptyState } from "./foundation/EmptyState";

export type Load<T> = { status: "loading" } | { status: "error" } | { status: "ready"; data: T };

/** Where an email or one of its files stands: a word, its colour and a dot, never colour alone. */
type Tone = "done" | "partial" | "failed" | "working";
const TONE: Record<Tone, string> = {
  done: "text-[#2f5a49] dark:text-[#8fcbb0]",
  partial: "text-[#735c14] dark:text-[#f6e7c1]",
  failed: "text-[#9e2f39] dark:text-[#ec9aa0]",
  working: "text-[#56635e] dark:text-white/65",
};
const DELIVERY_TONE: Record<BusinessEmailDelivery["state"], Tone> = { captured: "done", partial: "partial", rejected: "failed", received: "working", processing: "working" };
const PART_TONE: Record<BusinessEmailPart["state"], Tone> = { captured: "done", rejected: "failed", pending: "working" };

function StateWord({ tone, children, testId }: { tone: Tone; children: string; testId?: string }) {
  return (
    <span data-testid={testId} data-tone={tone} className={`inline-flex shrink-0 items-center gap-1.5 text-[13px] font-medium ${TONE[tone]}`}>
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full bg-current ${tone === "working" ? "motion-safe:animate-pulse" : ""}`} />
      {children}
    </span>
  );
}

/** The Business's own receiving address: copy it, or turn it on. A failed load always offers a retry. */
export function EmailReceivingAddress({ intake, onActivate }: { intake: BusinessEmailIntake; onActivate: () => Promise<void> }) {
  const { t } = useTranslation();
  const address = businessReceivingAddress(intake);
  const labels = useCopyLabels(address ?? "");
  const [activation, setActivation] = useState<"idle" | "working" | "failed">("idle");
  if (!address) {
    return (
      <div className="space-y-2" data-testid="email-address">
        <p className="text-[14px] text-[#56635e] dark:text-white/70">{t("business.email.no_address", "This business has no receiving address yet.")}</p>
        <button type="button" className={primaryButtonClass} disabled={activation === "working"} onClick={async () => {
          setActivation("working");
          try { await onActivate(); setActivation("idle"); } catch { setActivation("failed"); }
        }}>{t("business.email.activate", "Get a receiving address")}</button>
        {activation === "failed" ? <p role="alert" className="text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.email.activate_failed", "Email receiving is not available for this business yet.")}</p> : null}
      </div>
    );
  }
  return (
    <div data-testid="email-address">
      <p className="text-[13px] text-[#56635e] dark:text-white/70">{t("business.email.forward_to", "Forward receipts to this address:")}</p>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <p className="min-w-0 break-words text-[15px] font-medium text-[#172b26] dark:text-white"><WrappingAddress address={address} /></p>
        <CopyButton value={address} label={t("business.email.copy", "Copy address")} {...labels} testId="email-copy-address" className={`${secondaryButtonClass} shrink-0`}>
          {t("business.email.copy", "Copy address")}
        </CopyButton>
      </div>
      <p className="mt-2 text-[13px] text-[#56635e] dark:text-white/70">{t("business.email.lands_in_bandeja", "Attachments arrive in the Bandeja, ready to review.")}</p>
    </div>
  );
}

/** The receiving address as loaded: a placeholder while it loads, a retry when it fails, then the address. */
export function EmailAddressSection({ intake, onRetry, onActivated }: { intake: Load<BusinessEmailIntake>; onRetry: () => void; onActivated: (next: BusinessEmailIntake) => void }) {
  const { t } = useTranslation();
  const { source } = useBusiness();
  return (
    <section aria-label={t("business.email.forward_to", "Forward receipts to this address:")}>
      {intake.status === "loading" ? <Settle pending layout="rows" rows={1} /> : null}
      {intake.status === "error" ? (
        <p role="alert" className="flex flex-wrap items-center gap-2 text-[14px] text-[#9e2f39] dark:text-[#ec9aa0]">
          {t("business.email.address_failed", "Could not load the receiving address.")}
          <button type="button" className={quietButtonClass} onClick={onRetry}>{t("common.retry", "Retry")}</button>
        </p>
      ) : null}
      {intake.status === "ready" ? <EmailReceivingAddress intake={intake.data} onActivate={async () => onActivated(await source.createEmailAddress())} /> : null}
    </section>
  );
}

/** The address on its own, for the Negocio page: it loads itself. */
export function BusinessEmailAddress() {
  const { source, revision } = useBusiness();
  const [intake, setIntake] = useState<Load<BusinessEmailIntake>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    setIntake({ status: "loading" });
    source.emailIntake().then((data) => { if (current) setIntake({ status: "ready", data }); }).catch(() => { if (current) setIntake({ status: "error" }); });
    return () => { current = false; };
  }, [source, revision, attempt]);
  return <EmailAddressSection intake={intake} onRetry={() => setAttempt((value) => value + 1)} onActivated={(next) => setIntake({ status: "ready", data: next })} />;
}

/** One received email: subject and where it stands, then who sent it, when, and how many files. */
export function EmailDeliveryRow({ delivery, onOpen }: { delivery: BusinessEmailDelivery; onOpen: () => void }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  return (
    <li>
      <button type="button" data-testid="email-delivery-row" onClick={onOpen} className="flex w-full min-w-0 items-center gap-3 rounded-item px-2 py-3 text-left transition-colors hover:bg-black/[0.03] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#2f5a49] dark:hover:bg-white/[0.04]">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-item bg-black/[0.04] dark:bg-white/[0.06]"><Mail className="h-5 w-5 text-[#56635e] dark:text-white/60" aria-hidden="true" /></span>
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 truncate text-[15px] font-medium text-[#172b26] dark:text-white">{delivery.subject || t("business.email.no_subject", "No subject")}</span>
            <DeliveryState delivery={delivery} />
          </span>
          {/* The sender gives way first; when and how many files always show. */}
          <span className="mt-0.5 flex min-w-0 gap-1 text-[13px] text-[#56635e] dark:text-white/65">
            <span className="min-w-0 truncate">{delivery.sender || t("business.email.no_sender", "Sender unavailable")}</span>
            <span className="shrink-0">{` · ${formatRelativeTime(delivery.received_at, locale)} · ${t("business.email.attachments", { count: delivery.parts.length, defaultValue: "{{count}} attachments" })}`}</span>
          </span>
        </span>
        <ChevronRight className="h-4 w-4 shrink-0 text-black/30 dark:text-white/30" aria-hidden="true" />
      </button>
    </li>
  );
}

function DeliveryState({ delivery }: { delivery: BusinessEmailDelivery }) {
  const { t } = useTranslation();
  if (delivery.waiting) return <StateWord tone="partial" testId="email-state">{t("business.email.waiting_label", "Waiting until tomorrow")}</StateWord>;
  return <StateWord tone={DELIVERY_TONE[delivery.state]} testId="email-state">{t(`business.email.state.${delivery.state}`, delivery.state)}</StateWord>;
}

/**
 * One email, opened over the list with a way back: what happened in one line,
 * the message, each attachment with where it went, and what the owner can do
 * next (open the receipt, try again).
 */
export function EmailDeliveryDetail({ delivery, loadDetail, openReceipt, retryDelivery, inbox = null }: {
  delivery: BusinessEmailDelivery;
  loadDetail: (id: string) => Promise<BusinessEmailDetail>;
  openReceipt: (id: string) => void;
  retryDelivery: (id: string) => Promise<unknown>;
  /** The Inbox's receipts, to say when a captured part's receipt is still saved and unread. */
  inbox?: ReceiptSummary[] | null;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const waiting = delivery.waiting;
  const [body, setBody] = useState<Load<BusinessEmailDetail>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [retry, setRetry] = useState<"idle" | "sending" | "accepted" | "error">("idle");
  useEffect(() => {
    if (waiting) return undefined;
    let current = true;
    setBody({ status: "loading" });
    loadDetail(delivery.id).then((data) => { if (current) setBody({ status: "ready", data }); }).catch(() => { if (current) setBody({ status: "error" }); });
    return () => { current = false; };
  }, [delivery.id, delivery.updated_at, waiting, loadDetail, attempt]);
  const savedReceipt = (documentId: string) => {
    const receipt = inbox?.find((item) => item.id === documentId);
    return receipt && savedUnread(receipt) ? receipt : null;
  };
  const captured = delivery.parts.filter((part) => part.state === "captured" && part.document_id);
  const resumeAt = waiting ? new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(waiting.retry_at)) : null;
  const reason = waiting
    ? t("business.email.waiting_resume", "This email is waiting. Processing resumes automatically from {{time}} UTC. You do not need to send it again.", { time: resumeAt })
    : delivery.error_code
      ? t(`business.email.error.${delivery.error_code}`, t("business.email.error.other", "Part of this email could not be saved."))
      : delivery.state === "captured"
        ? t("business.email.saved_line", { count: captured.length, defaultValue: "{{count}} receipts went to the Bandeja." })
        : null;

  return (
    <div className="space-y-5 pb-6 pt-4" data-testid="email-detail">
      <div className="space-y-1">
        <DeliveryState delivery={delivery} />
        {reason ? <p className="text-[14px] text-[#172b26] dark:text-white" data-testid="email-reason">{reason}</p> : null}
      </div>

      {!waiting ? (
        <section aria-label={t("business.email.message", "Message")}>
          {body.status === "loading" ? <Settle pending layout="rows" rows={2} /> : null}
          {body.status === "error" ? (
            <p role="alert" className="flex flex-wrap items-center gap-2 text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">
              {t("business.email.body_failed", "Could not load the message.")}
              <button type="button" className={quietButtonClass} onClick={() => setAttempt((value) => value + 1)}>{t("common.retry", "Retry")}</button>
            </p>
          ) : null}
          {body.status === "ready" ? <blockquote className="whitespace-pre-wrap break-words border-l-2 border-[#DCE0DA] pl-3 text-[14px] leading-relaxed text-[#56635e] dark:border-white/15 dark:text-white/75">{body.data.text_body || t("business.email.no_body", "No message text.")}</blockquote> : null}
        </section>
      ) : null}

      <section aria-labelledby="email-files-title">
        <h3 id="email-files-title" className="mb-1 text-[13px] font-medium text-[#56635e] dark:text-white/70">{t("business.email.files", "Attachments")}</h3>
        <ul className="divide-y divide-[#EEF0EC] dark:divide-white/[0.06]">
          {delivery.parts.map((part) => {
            const saved = part.state === "captured" && part.document_id ? savedReceipt(part.document_id) : null;
            return (
              <li key={part.id} className="flex min-h-14 flex-wrap items-center gap-x-3 gap-y-1 py-2">
                <FileText className="h-4 w-4 shrink-0 text-[#56635e] dark:text-white/60" aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className="block break-words text-[14px] text-[#172b26] dark:text-white">{part.filename || t("business.email.no_filename", "Unnamed attachment")}</span>
                  <span className="flex flex-wrap items-center gap-x-2 text-[13px] text-[#56635e] dark:text-white/65">
                    <StateWord tone={PART_TONE[part.state]}>{t(`business.email.part_state.${part.state}`, part.state)}</StateWord>
                    {part.state === "rejected" && part.error_code ? <span>{t(`business.email.part_error.${part.error_code}`, t("business.email.part_error.other", "It isn't a file we can save as a receipt."))}</span> : null}
                    {part.repeat_of_delivery_id || part.repeat_of_upload ? <span data-testid="email-part-repeat">{part.repeat_of_delivery_id ? t("business.email.repeat", "You already received this file") : t("business.email.repeat_upload", "You already saved this file")}</span> : null}
                    {saved ? <span data-testid="email-part-saved-unread">{savedUnreadLine(t, { enterable: saved.enterable, preparable: saved.preparable })}</span> : null}
                  </span>
                </span>
                {part.state === "captured" && part.document_id ? (
                  <button type="button" className={quietButtonClass} onClick={() => openReceipt(part.document_id!)}>
                    {t("business.email.open_receipt", "Open receipt")}<ChevronRight className="h-4 w-4" aria-hidden="true" />
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      </section>

      {delivery.original_document_id || (!waiting && delivery.retryable) ? (
        <div className="flex flex-wrap gap-2">
          {!waiting && delivery.retryable ? <button type="button" className={primaryButtonClass} disabled={retry === "sending" || retry === "accepted"} onClick={async () => {
            setRetry("sending");
            try { await retryDelivery(delivery.id); setRetry("accepted"); } catch { setRetry("error"); }
          }}>{retry === "sending" ? t("business.email.retrying", "Requesting…") : t("business.email.retry", "Try again")}</button> : null}
          {delivery.original_document_id ? <button type="button" className={secondaryButtonClass} onClick={() => openReceipt(delivery.original_document_id!)}>{captured.length ? t("business.email.original", "Open the original email") : t("business.email.open_receipt", "Open receipt")}</button> : null}
        </div>
      ) : null}
      {retry === "accepted" ? <p role="status" className="text-[13px] text-[#56635e] dark:text-white/70">{t("business.email.retry_accepted", "Retry requested. The status updates after processing.")}</p> : null}
      {retry === "error" ? <p role="alert" className="text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.email.retry_failed", "Could not request a retry. Saved attachments are unchanged.")}</p> : null}
    </div>
  );
}

/** The words every email row and record share: who sent it, its subject, and why it brought no receipt. */
export function useEmailWords() {
  const { t } = useTranslation();
  return {
    title: (delivery: BusinessEmailDelivery) => delivery.sender ? t("business.inbox.email_row_title", { sender: delivery.sender, defaultValue: "Email from {{sender}}" }) : t("business.inbox.email_row_unknown", "Email with no sender"),
    subject: (delivery: BusinessEmailDelivery) => delivery.subject ? t("business.inbox.email_subject", { subject: delivery.subject, defaultValue: "“{{subject}}”" }) : t("business.email.no_subject", "No subject"),
    // The email's own failure when it says more than "some parts", then the first file's, then a missing file.
    noReceipt: (delivery: BusinessEmailDelivery) => {
      if (delivery.error_code && delivery.error_code !== "email_parts_rejected") return t(`business.email.error.${delivery.error_code}`, t("business.email.error.other", "Part of this email could not be saved."));
      const rejected = delivery.parts.find((part) => part.state === "rejected");
      if (rejected) return t(`business.email.part_error.${rejected.error_code ?? "other"}`, t("business.email.part_error.other", "It isn't a file we can save as a receipt."));
      if (!delivery.parts.length) return t("business.email.no_attachment", "It had no attachment");
      return t("business.email.part_error.other", "It isn't a file we can save as a receipt.");
    },
  };
}

/**
 * One email as a record: beside the Bandeja on a desktop, the whole page with
 * a way back on a phone. It reads the workspace's emails, so it opens from a
 * Bandeja row, a receipt's Ver correo and an old link alike.
 */
export function EmailRecord({ emailId }: { emailId: string }) {
  const { t, i18n } = useTranslation();
  const { records, source, openPanel, emailRefresh } = useBusiness();
  const words = useEmailWords();
  const tray = useRecordTray();
  const delivery = records.emails?.find((item) => item.id === emailId) ?? null;
  const known = records.emails !== null || records.emailsError;
  return (
    <section data-testid="email-record" aria-labelledby="email-record-title">
      {tray ? null : (
        <button type="button" onClick={() => openPanel({ kind: "inbox" })} className="mb-4 flex min-h-11 items-center gap-2 rounded-full pr-3 text-[15px] text-[#56635e] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-white/70">
          <ArrowLeft className="h-5 w-5" aria-hidden="true" />
          {t("business.nav.inbox", "Inbox")}
        </button>
      )}
      {delivery ? (
        <>
          <header>
            <h2 id="email-record-title" className="break-words font-display text-[22px] font-medium leading-7 text-[#172b26] dark:text-white"><WrappingAddress address={words.title(delivery)} /></h2>
            <p className="mt-1 break-words text-[14px] text-[#56635e] dark:text-white/70">{[words.subject(delivery), formatRelativeTime(delivery.received_at, i18n.resolvedLanguage ?? "en")].join(" · ")}</p>
          </header>
          <EmailDeliveryDetail
            delivery={delivery}
            inbox={records.inbox}
            loadDetail={source.emailDelivery}
            retryDelivery={async (id) => { await source.retryEmailDelivery(id); emailRefresh.refresh(); }}
            openReceipt={(id) => openPanel({ kind: "receipt", receiptId: id, list: "inbox" })}
          />
        </>
      ) : known ? (
        <p role="alert" className="text-[14px] text-[#56635e] dark:text-white/70">{records.emailsError ? t("business.empty.email_error", "We couldn't load your emails") : t("business.email.not_found", "We couldn't find this email.")}</p>
      ) : (
        <Settle pending layout="rows" rows={3} />
      )}
    </section>
  );
}

/**
 * Every email received, newest first, under the receiving address in Negocio
 * > Correo de recibos. Opening one shows it in a sheet with a way back;
 * opening its receipt puts the email away first.
 */
export function EmailHistory() {
  const { t } = useTranslation();
  const { source, openPanel, records, emailRefresh } = useBusiness();
  const [opened, setOpened] = useState<string | null>(null);
  const openReceipt = (id: string) => {
    setOpened(null);
    openPanel({ kind: "receipt", receiptId: id });
  };
  const openDelivery = records.emails?.find((item) => item.id === opened) ?? null;

  return (
    <section aria-labelledby="email-history-title" data-testid="email-history">
      <div className="flex items-center justify-between gap-2">
        <h3 id="email-history-title" className="text-[14px] font-medium text-[#56635e] dark:text-white/70">{t("business.settings.correo_history", "History")}</h3>
        <button type="button" aria-label={t("business.email.reload", "Refresh")} data-testid="email-refresh" onClick={emailRefresh.refresh} className="flex h-11 w-11 items-center justify-center rounded-full text-[#56635e] hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-white/70 dark:hover:bg-white/10">
          <RefreshCw className={`h-4 w-4 ${emailRefresh.refreshing ? "motion-safe:animate-spin" : ""}`} aria-hidden="true" />
        </button>
      </div>
      {emailRefresh.stalled ? <p role="status" className="text-[13px] text-[#56635e] dark:text-white/70">{t("business.email.poll_stopped", "Some emails are still being read. Use Refresh to see the latest state.")}</p> : null}
      {records.emails === null && !records.emailsError ? <Settle pending layout="rows" rows={2} /> : null}
      {records.emails === null && records.emailsError ? <EmptyState kind="error" compact title={t("business.empty.email_error", "We couldn't load your emails")} body={t("business.empty.error_body", "Your data is still saved. Check your connection and try again.")} action={{ label: t("common.retry", "Retry"), run: emailRefresh.refresh }} /> : null}
      {records.emails ? (records.emails.length ? (
        <ul className={`${cardClass} divide-y divide-[#EEF0EC] p-2 dark:divide-white/[0.06]`} data-testid="business-email-deliveries">
          {records.emails.map((delivery) => <EmailDeliveryRow key={delivery.id} delivery={delivery} onOpen={() => setOpened(delivery.id)} />)}
        </ul>
      ) : (
        <p className="py-2 text-[14px] text-[#56635e] dark:text-white/70">{t("business.email.empty", "No emails received yet.")}</p>
      )) : null}

      {openDelivery ? (
        <AdaptivePanel
          title={openDelivery.subject || t("business.email.no_subject", "No subject")}
          summary={openDelivery.sender ?? undefined}
          closeLabel={t("common.back", "Back")}
          onClose={() => setOpened(null)}
          width="md"
        >
          <div className="desktop:px-5">
            <EmailDeliveryDetail delivery={openDelivery} inbox={records.inbox} loadDetail={source.emailDelivery} retryDelivery={async (id) => { await source.retryEmailDelivery(id); emailRefresh.refresh(); }} openReceipt={openReceipt} />
          </div>
        </AdaptivePanel>
      ) : null}
    </section>
  );
}
