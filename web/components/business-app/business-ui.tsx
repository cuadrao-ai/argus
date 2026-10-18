"use client";

import { useContext, useEffect, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { ReceiptAttention, ReceiptStatus } from "@/lib/business-api";
import { BusinessContext, useBusiness } from "./BusinessWorkspace";

export const cardClass =
  "rounded-[20px] border border-black/[0.06] bg-white p-5 dark:border-white/[0.06] dark:bg-[#1f2225]";

export const pillButtonClass =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 text-[15px] font-medium transition-opacity hover:opacity-85 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 disabled:opacity-40 dark:focus-visible:ring-white/30";

export const primaryButtonClass = `${pillButtonClass} bg-black text-white dark:bg-white dark:text-black`;
export const secondaryButtonClass = `${pillButtonClass} border border-black/10 bg-white text-black dark:border-white/10 dark:bg-[#1f2225] dark:text-white`;
/** A destructive action: red, and always behind a confirmation. */
export const dangerButtonClass = `${pillButtonClass} border border-[#a8434c]/40 bg-white text-[#a8434c] dark:border-[#ec9aa0]/40 dark:bg-[#1f2225] dark:text-[#ec9aa0]`;
export const dangerConfirmButtonClass = `${pillButtonClass} bg-[#a8434c] text-white dark:bg-[#ec9aa0] dark:text-black`;

export function PanelHeading({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h2 className="font-display text-[26px] font-medium tracking-tight text-black dark:text-white">{title}</h2>
        {subtitle ? <p className="mt-1 text-[14px] text-black/55 dark:text-white/55">{subtitle}</p> : null}
      </div>
      {action}
    </div>
  );
}

/** Says, on every Business screen, when the records are invented. */
export function SampleDataNotice() {
  const { t } = useTranslation();
  const { source } = useBusiness();
  if (source.mode !== "fixture") return null;
  return (
    <div
      role="note"
      data-testid="business-sample-data"
      className="mb-5 rounded-[14px] border border-dashed border-[#c2a44d]/60 bg-[#c2a44d]/10 px-4 py-2.5 text-[13px] text-black/70 dark:text-white/70"
    >
      {t(
        "business.sample.notice",
        "Design preview with sample data. Nothing here is saved, uploaded or sent.",
      )}
    </div>
  );
}

const STATUS_TONE: Record<ReceiptStatus, string> = {
  saved: "bg-black/5 text-black/65 dark:bg-white/10 dark:text-white/65",
  queued: "bg-black/5 text-black/65 dark:bg-white/10 dark:text-white/65",
  preparing: "bg-black/5 text-black/65 dark:bg-white/10 dark:text-white/65",
  review_ready: "bg-[#5ba897]/15 text-[#2f7466] dark:text-[#7cc6b4]",
  needs_attention: "bg-[#d66d75]/15 text-[#a8434c] dark:text-[#ec9aa0]",
  confirmed: "bg-black/5 text-black/65 dark:bg-white/10 dark:text-white/65",
  dismissed: "bg-black/5 text-black/45 dark:bg-white/10 dark:text-white/45",
};

export function useStatusLabel() {
  const { t } = useTranslation();
  return (status: ReceiptStatus) =>
    ({
      saved: t("business.status.saved", "Saved, not prepared"),
      queued: t("business.status.queued", "Waiting to prepare"),
      preparing: t("business.status.preparing", "Preparing"),
      review_ready: t("business.status.review_ready", "Ready to review"),
      needs_attention: t("business.status.needs_attention", "Needs attention"),
      confirmed: t("business.status.confirmed", "Expense saved"),
      dismissed: t("business.status.dismissed", "Dismissed"),
    })[status];
}

export function StatusPill({ status }: { status: ReceiptStatus }) {
  const label = useStatusLabel();
  return (
    <span className={`inline-flex shrink-0 items-center rounded-full px-2.5 py-1 text-[12px] font-medium ${STATUS_TONE[status]}`}>
      {label(status)}
    </span>
  );
}

export function useCategoryLabel() {
  const { t } = useTranslation();
  return (id: string | null) =>
    id
      ? t(`business.category.${id}`, {
          defaultValue: {
            other: "Other",
            groceries: "Groceries",
            dining: "Dining",
            transport: "Transport",
            housing: "Housing",
            health: "Health",
            shopping: "Shopping",
            interest_fees: "Interest and fees",
          }[id] ?? id,
        })
      : t("business.category.none", "No category");
}

/** Each message names the cause and the next step the backend allows. */
export function useAttentionLabel() {
  const { t } = useTranslation();
  return (attention: ReceiptAttention | null) =>
    attention
      ? ({
          unreadable: t("business.attention.unreadable", "We couldn't read this receipt. Enter the details yourself or send a clearer photo."),
          ai_unavailable: t("business.attention.ai_unavailable", "AI preparation isn't available right now. Your receipt is saved. Try again later or enter the details yourself."),
          interrupted: t("business.attention.interrupted", "Preparation stopped before it finished. Your receipt is saved. Try again or enter the details yourself."),
          outcome_unknown: t("business.attention.outcome_unknown", "We couldn't recover the AI reading result. Your receipt is still saved. Try again or enter the details yourself."),
          no_purchase_found: t("business.attention.no_purchase_found", "Cuadrao read this receipt but didn't find a purchase to save. Enter the details yourself."),
          several_purchases: t("business.attention.several_purchases", "Cuadrao couldn't match this receipt to one purchase. Enter the details yourself to save one expense."),
          source_unavailable: t("business.attention.source_unavailable", "The original file is no longer available. Enter the details yourself."),
          check_details: t("business.attention.check_details", "Cuadrao couldn't read every part of this receipt. Check the details against the original before you confirm."),
          duplicate: t("business.attention.duplicate", "This looks like a receipt you already saved: same merchant, date and total. It won't be saved as a second expense."),
          other: t("business.attention.other", "Something went wrong with this receipt. It is still saved. Enter the details yourself."),
        } satisfies Record<ReceiptAttention, string>)[attention]
      : "";
}

export function LoadingRows({ rows = 3, layout = "rows" }: { rows?: number; layout?: "rows" | "overview" | "detail" }) {
  const { t } = useTranslation();
  const line = "rounded-md bg-black/[0.06] dark:bg-white/[0.08]";
  const pulse = "animate-pulse motion-reduce:animate-none";
  const fields = Array.from({ length: rows }, (_, index) => (
    <div key={index} className={layout === "overview" ? `${cardClass} min-h-40 space-y-4` : "flex min-h-20 items-center gap-3 px-3 py-3"}>
      {layout === "rows" ? <div className={`${line} h-11 w-11 shrink-0 rounded-[12px]`} /> : null}
      <div className="min-w-0 flex-1 space-y-3">
        <div className={`${line} h-3 w-2/5`} />
        <div className={`${line} ${layout === "overview" ? "h-7 w-3/5" : "h-4 w-3/4"}`} />
      </div>
      {layout === "rows" ? <div className={`${line} h-4 w-16 shrink-0`} /> : null}
    </div>
  ));
  return (
    <div role="status" aria-label={t("common.loading", "Loading")} data-testid="business-loading" data-layout={layout}>
      <div aria-hidden="true" className={pulse}>
        {layout === "detail" ? <>
          <div className="mb-5 space-y-4 py-3"><div className={`${line} h-4 w-20`} /><div className={`${line} h-7 w-48 max-w-full`} /></div>
          <div className="grid items-start gap-4 desktop:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div className={`${cardClass} h-28 desktop:h-80`} />
            <div className={`${cardClass} divide-y divide-black/[0.05] dark:divide-white/[0.05]`}>{fields}</div>
          </div>
        </> : <div className={layout === "overview" ? "grid gap-3 tablet:grid-cols-2" : `${cardClass} divide-y divide-black/[0.05] p-2 dark:divide-white/[0.05]`}>{fields}</div>}
      </div>
    </div>
  );
}

/** Where a source arrived from, by its channel; WhatsApp keeps its name, the rest have a word. */
export function useChannelLabel() {
  const { t } = useTranslation();
  return (channel: "web" | "whatsapp" | "email" | string) =>
    channel === "whatsapp" ? "WhatsApp" : channel === "email" ? t("business.dossier.email", "Email") : t("business.dossier.web", "Web upload");
}

/** The owner is looking: their own Business, not a client's opened through a grant. */
export function useOwnerView(): boolean {
  const business = useContext(BusinessContext);
  return !business?.chosen || business.chosen.role === "owner";
}

/**
 * The marks a record carries, as text in a muted chip, never colour alone:
 * "Personal" when a person marked it as no part of the Business; "Sin
 * comprobante fiscal" when the read facts hold no NCF and no e-CF. Grey on
 * purpose: a missing fiscal number is a fact about the receipt, not a fault.
 * When someone other than the owner marked it Personal, the owner sees a small
 * dot on the chip that reads "Marcado por <nombre>".
 */
export function RecordMarks({ personal, fiscalValue, known, markedBy = null, className = "" }: { personal?: boolean; fiscalValue?: "ncf" | "ecf" | null; known: boolean; markedBy?: string | null; className?: string }) {
  const { t } = useTranslation();
  const owner = useOwnerView();
  const chip = "inline-flex min-h-6 items-center whitespace-nowrap rounded-full border px-2 text-[11px] font-medium";
  if (!personal && (!known || fiscalValue)) return null;
  const marker = personal && owner && markedBy ? t("business.marks.marked_by", "Marked by {{name}}", { name: markedBy }) : null;
  return (
    <span className={`flex flex-wrap items-center gap-1.5 ${className}`} data-testid="record-marks">
      {personal ? (
        <span data-mark="personal" title={marker ?? undefined} className={`${chip} gap-1 border-[var(--cuadrao-green)]/35 text-[var(--cuadrao-green)]`}>
          {t("business.marks.personal_chip", "Personal")}
          {marker ? <><span data-testid="personal-marked-dot" aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--cuadrao-green)]" /><span className="sr-only">{marker}</span></> : null}
        </span>
      ) : null}
      {known && !fiscalValue ? <span data-mark="no_fiscal" className={`${chip} border-black/15 text-black/55 dark:border-white/15 dark:text-white/55`}>{t("business.marks.no_fiscal_chip", "No fiscal receipt number")}</span> : null}
    </span>
  );
}

/** A short announcement with one way back, for a change the person can undo. */
export function UndoToast({ text, onUndo, onClose }: { text: string; onUndo?: () => void; onClose: () => void }) {
  const { t } = useTranslation();
  useEffect(() => {
    const timer = setTimeout(onClose, 6000);
    return () => clearTimeout(timer);
  }, [onClose]);
  return (
    <div role="status" data-testid="undo-toast" className="fixed inset-x-4 bottom-24 z-[60] mx-auto flex max-w-md items-center justify-between gap-3 rounded-[14px] bg-black px-4 py-3 text-[13px] text-white shadow-lg dark:bg-white dark:text-black">
      <span className="min-w-0">{text}</span>
      {onUndo ? <button type="button" onClick={onUndo} className="inline-flex min-h-9 shrink-0 items-center rounded-full px-3 text-[13px] font-medium underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60 dark:focus-visible:ring-black/40">{t("business.marks.undo", "Undo")}</button> : null}
    </div>
  );
}

