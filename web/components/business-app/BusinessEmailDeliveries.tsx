"use client";

import { useEffect, useState } from "react";
import { ChevronRight, Mail, Paperclip } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import type { BusinessEmailDelivery, BusinessEmailDetail, BusinessEmailIntake } from "@/lib/business-email";
import { businessReceivingAddress, emailDeliveriesNeedRefresh } from "@/lib/business-email";
import { useBusiness } from "./BusinessWorkspace";
import { savedUnread, savedUnreadLine } from "./ReceiptReadNotice";
import { formatRelativeTime } from "./business-format";
import { cardClass, secondaryButtonClass } from "./business-ui";

type Load<T> = { status: "loading" } | { status: "error" } | { status: "ready"; data: T };

export function EmailReceivingAddress({ intake, onActivate }: { intake: BusinessEmailIntake; onActivate: () => Promise<void> }) {
  const { t } = useTranslation();
  const address = businessReceivingAddress(intake);
  const [copy, setCopy] = useState<"idle" | "copied" | "failed">("idle");
  const [activation, setActivation] = useState<"idle" | "working" | "failed">("idle");
  if (!address) {
    return (
      <div className="space-y-2">
        <p className="text-[13px] text-black/55 dark:text-white/55">{t("business.email.no_address", "This business has no receiving address yet.")}</p>
        <button type="button" className={secondaryButtonClass} disabled={activation === "working"} onClick={async () => {
          setActivation("working");
          try { await onActivate(); setActivation("idle"); } catch { setActivation("failed"); }
        }}>{t("business.email.activate", "Get a receiving address")}</button>
        {activation === "failed" ? <p role="alert" className="text-[13px] text-black/70 dark:text-white/70">{t("business.email.activate_failed", "Email receiving is not available for this business yet.")}</p> : null}
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-[13px] text-black/55 dark:text-white/55">{t("business.email.forward_to", "Forward receipts to this address:")}</p>
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 break-all text-[14px] font-medium text-black dark:text-white">{address}</span>
        <button type="button" className={secondaryButtonClass} onClick={async () => {
          try { await navigator.clipboard.writeText(address); setCopy("copied"); } catch { setCopy("failed"); }
        }}>{t("business.email.copy", "Copy address")}</button>
      </div>
      {copy !== "idle" ? <p role="status" className="text-[13px] text-black/55 dark:text-white/55">{copy === "copied" ? t("business.email.copied", "Address copied.") : t("business.email.copy_failed", "Could not copy. Select the address to copy it.")}</p> : null}
    </div>
  );
}

export function EmailDeliveryRow({ delivery, expanded, onExpanded, loadDetail, openReceipt, retryDelivery, inbox = null }: {
  /** The Inbox's receipts, to say when a captured part's receipt is still saved and unread. */
  inbox?: ReceiptSummary[] | null;
  delivery: BusinessEmailDelivery;
  expanded: boolean;
  onExpanded: (expanded: boolean) => void;
  loadDetail: (id: string) => Promise<BusinessEmailDetail>;
  openReceipt: (id: string) => void;
  retryDelivery: (id: string) => Promise<unknown>;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  // The receipt behind a captured part, when the Inbox has it: saved and unread until a person acts.
  const savedReceipt = (documentId: string) => {
    const receipt = inbox?.find((item) => item.id === documentId);
    return receipt && savedUnread(receipt) ? receipt : null;
  };
  const waitingRetryAt = delivery.waiting?.retry_at;
  const [body, setBody] = useState<Load<BusinessEmailDetail> | null>(null);
  const [retry, setRetry] = useState<"idle" | "sending" | "accepted" | "error">("idle");
  useEffect(() => { setRetry("idle"); }, [delivery.updated_at]);
  useEffect(() => {
    if (!expanded || waitingRetryAt) return;
    let current = true;
    setBody({ status: "loading" });
    loadDetail(delivery.id).then((data) => { if (current) setBody({ status: "ready", data }); }).catch(() => { if (current) setBody({ status: "error" }); });
    return () => { current = false; };
  }, [expanded, delivery.id, delivery.updated_at, waitingRetryAt, loadDetail]);
  const captured = delivery.parts.filter((part) => part.state === "captured" && part.document_id);
  const waiting = delivery.waiting;
  const stateLabel = waiting ? t("business.email.waiting_label", "Waiting until tomorrow") : t(`business.email.state.${delivery.state}`, delivery.state);
  const resumeAt = waiting ? new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(waiting.retry_at)) : null;
  return (
    <li className="rounded-[16px] border border-black/[0.06] dark:border-white/[0.08]">
      <button type="button" aria-expanded={expanded} onClick={() => onExpanded(!expanded)} className="flex w-full items-center gap-3 rounded-[16px] px-3 py-3 text-left transition-colors hover:bg-black/[0.03] focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:hover:bg-white/[0.04] dark:focus-visible:ring-white/30">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[12px] bg-black/[0.04] dark:bg-white/[0.06]"><Mail className="h-5 w-5 text-black/55 dark:text-white/55" aria-hidden="true" /></span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[15px] font-medium text-black dark:text-white">{delivery.subject || t("business.email.no_subject", "No subject")}</span>
          <span className="mt-0.5 block truncate text-[13px] text-black/50 dark:text-white/50">
            {[delivery.sender || t("business.email.no_sender", "Sender unavailable"), formatRelativeTime(delivery.received_at, locale), t("business.email.attachments", "{{count}} attachments", { count: delivery.parts.length })].join(" · ")}
          </span>
        </span>
        <span className="shrink-0 rounded-full bg-black/[0.05] px-2 py-0.5 text-[12px] text-black/70 dark:bg-white/[0.08] dark:text-white/70">{stateLabel}</span>
        <ChevronRight className={`h-4 w-4 shrink-0 text-black/30 transition-transform dark:text-white/30 ${expanded ? "rotate-90" : ""}`} />
      </button>
      {expanded ? (
        <div className="space-y-3 px-3 pb-3">
          {waiting ? <p role="status" className="text-[13px] text-black/55 dark:text-white/55">{t("business.email.waiting_resume", "This email is waiting. Processing resumes automatically from {{time}} UTC. You do not need to send it again.", { time: resumeAt })}</p> : null}
          {!waiting && delivery.error_code ? <p className="text-[13px] text-black/55 dark:text-white/55">{t(`business.email.error.${delivery.error_code}`, t("business.email.error.other", "Part of this email could not be saved."))}</p> : null}
          {!waiting && body?.status === "loading" ? <p role="status" className="text-[13px] text-black/55 dark:text-white/55">{t("common.loading", "Loading...")}</p> : null}
          {!waiting && body?.status === "error" ? <p role="alert" className="text-[13px] text-black/70 dark:text-white/70">{t("business.email.body_failed", "Could not load the message.")}</p> : null}
          {!waiting && body?.status === "ready" ? <blockquote className="whitespace-pre-wrap break-words border-l-2 border-black/10 pl-3 text-[14px] leading-relaxed text-black/75 dark:border-white/15 dark:text-white/75">{body.data.text_body || t("business.email.no_body", "No message text.")}</blockquote> : null}
          <ul className="space-y-2">
            {delivery.parts.map((part) => (
              <li key={part.id} className="flex flex-wrap items-center gap-2 rounded-xl bg-black/[0.03] px-3 py-2 dark:bg-white/[0.04]">
                <Paperclip className="h-4 w-4 shrink-0 text-black/45 dark:text-white/45" aria-hidden="true" />
                <span className="min-w-0 flex-1 break-words text-[14px] text-black dark:text-white">{part.filename || t("business.email.no_filename", "Unnamed attachment")}</span>
                <span className="text-[12px] text-black/50 dark:text-white/50">{t(`business.email.part_state.${part.state}`, part.state)}</span>
                {part.repeat_of_delivery_id || part.repeat_of_upload ? <span data-testid="email-part-repeat" className="text-[12px] font-medium text-black/70 dark:text-white/70">{part.repeat_of_delivery_id ? t("business.email.repeat", "You already received this file") : t("business.email.repeat_upload", "You already saved this file")}</span> : null}
                {part.state === "captured" && part.document_id && savedReceipt(part.document_id) ? <span data-testid="email-part-saved-unread" className="basis-full text-[12px] text-black/65 dark:text-white/65">{savedUnreadLine(t, { enterable: savedReceipt(part.document_id)!.enterable, preparable: savedReceipt(part.document_id)!.preparable })}</span> : null}
                {part.state === "captured" && part.document_id ? <button type="button" className={secondaryButtonClass} onClick={() => openReceipt(part.document_id!)}>{t("business.email.open_receipt", "Open receipt")}</button> : null}
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-2">
            {delivery.original_document_id ? <button type="button" className={secondaryButtonClass} onClick={() => openReceipt(delivery.original_document_id!)}>{captured.length ? t("business.email.original", "Open the original email") : t("business.email.open_receipt", "Open receipt")}</button> : null}
            {!waiting && delivery.retryable ? <button type="button" className={secondaryButtonClass} disabled={retry !== "idle"} onClick={async () => {
              setRetry("sending");
              try { await retryDelivery(delivery.id); setRetry("accepted"); } catch { setRetry("error"); }
            }}>{retry === "sending" ? t("business.email.retrying", "Requesting…") : t("business.email.retry", "Try again")}</button> : null}
          </div>
          {retry === "accepted" ? <p role="status" className="text-[13px] text-black/55 dark:text-white/55">{t("business.email.retry_accepted", "Retry requested. The status updates after processing.")}</p> : null}
          {retry === "error" ? <p role="alert" className="text-[13px] text-black/70 dark:text-white/70">{t("business.email.retry_failed", "Could not request a retry. Saved attachments are unchanged.")}</p> : null}
        </div>
      ) : null}
    </li>
  );
}

/** Received emails, newest first, and the address that receives them. */
/** `openEmailId`: the delivery to show expanded on arrival, when a receipt sent the person to its first email. */
export default function BusinessEmailDeliveries({ openEmailId }: { openEmailId?: string } = {}) {
  const { t } = useTranslation();
  const { source, openPanel, revision, records } = useBusiness();
  const [intake, setIntake] = useState<Load<BusinessEmailIntake>>({ status: "loading" });
  const [deliveries, setDeliveries] = useState<Load<BusinessEmailDelivery[]>>({ status: "loading" });
  const [expanded, setExpanded] = useState<string | null>(openEmailId ?? null);
  // A later arrival from another receipt names another email: it opens too.
  useEffect(() => { if (openEmailId) setExpanded(openEmailId); }, [openEmailId]);
  const [attempt, setAttempt] = useState(0);
  const [stalled, setStalled] = useState(false);
  useEffect(() => {
    let current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let polls = 0;
    setStalled(false);
    source.emailIntake().then((data) => { if (current) setIntake({ status: "ready", data }); }).catch(() => { if (current) setIntake({ status: "error" }); });
    const refresh = async () => {
      try {
        const items = await source.emailDeliveries();
        if (!current) return;
        setDeliveries({ status: "ready", data: items });
        if (!emailDeliveriesNeedRefresh(items)) return;
        if (polls++ < 6) timer = setTimeout(() => void refresh(), 5000);
        else setStalled(true);
      } catch { if (current) setDeliveries({ status: "error" }); }
    };
    void refresh();
    return () => { current = false; clearTimeout(timer); };
  }, [source, attempt, revision]);
  if (intake.status === "error" && deliveries.status === "error") return null;
  const ready = intake.status === "ready" ? intake.data : null;
  return (
    <section aria-label={t("business.email.title", "Received emails")} className="mb-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h3 className="font-display text-[16px] font-medium text-black dark:text-white">{t("business.email.title", "Received emails")}</h3>
        </div>
        <button type="button" className={secondaryButtonClass} onClick={() => setAttempt((value) => value + 1)}>{t("business.email.reload", "Refresh")}</button>
      </div>
      <div className={`${cardClass} mt-3 space-y-4`}>
        {intake.status === "error" ? <p role="alert" className="text-[13px] text-black/70 dark:text-white/70">{t("business.email.address_failed", "Could not load the receiving address.")}</p> : null}
        {ready ? <EmailReceivingAddress intake={ready} onActivate={async () => { const next = await source.createEmailAddress(); setIntake({ status: "ready", data: next }); }} /> : null}
        {deliveries.status === "error" ? <p role="alert" className="text-[13px] text-black/70 dark:text-white/70">{t("business.email.list_failed", "Could not load received emails.")}</p> : null}
        {stalled ? <p role="status" className="text-[13px] text-black/55 dark:text-white/55">{t("business.email.poll_stopped", "Some emails are still being read. Use Refresh to see the latest state.")}</p> : null}
        {deliveries.status === "ready" ? (deliveries.data.length ? (
          <ul className="space-y-2" data-testid="business-email-deliveries">
            {deliveries.data.map((delivery) => <EmailDeliveryRow key={delivery.id} delivery={delivery} inbox={records.inbox} expanded={expanded === delivery.id} onExpanded={(open) => setExpanded(open ? delivery.id : null)} loadDetail={source.emailDelivery} retryDelivery={source.retryEmailDelivery} openReceipt={(id) => openPanel({ kind: "receipt", receiptId: id })} />)}
          </ul>
        ) : <p className="text-[13px] text-black/55 dark:text-white/55">{t("business.email.empty", "No emails received yet.")}</p>) : null}
      </div>
    </section>
  );
}
