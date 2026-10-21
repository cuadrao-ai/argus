"use client";

import { useContext, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { ReceiptAttention, ReceiptStatus } from "@/lib/business-api";
import { BusinessContext } from "./BusinessWorkspace";
import { FOCUS_RING } from "./foundation/presentation";
import { StatusPill as FoundationStatusPill } from "./foundation/StatusPill";

export const cardClass =
  "rounded-surface border border-black/[0.06] bg-white p-5 dark:border-white/[0.06] dark:bg-[#1f2225]";
/**
 * The one owner of button looks (Lucas, October 21, 2026). Four levels, never a fifth:
 * primary is the screen's one main action in Cuadrao green; secondary is an outlined
 * alternative such as Listo or Volver; quiet is a green text action inside content;
 * danger is the red confirm of a delete. All are fully round with a 44px target.
 */
export const pillButtonClass =
  `inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 text-[15px] font-medium transition-[opacity,background-color] hover:opacity-90 ${FOCUS_RING} disabled:opacity-40`;

export const primaryButtonClass = `${pillButtonClass} bg-[var(--cuadrao-green)] text-[var(--cuadrao-cream)]`;
export const secondaryButtonClass = `${pillButtonClass} border border-[#7d8a84]/60 bg-white text-[#172b26] hover:bg-[#F7F5EE] hover:opacity-100 dark:border-white/20 dark:bg-[#1f2225] dark:text-white dark:hover:bg-white/[0.06]`;
export const quietButtonClass = `inline-flex min-h-11 items-center gap-1.5 rounded-full px-1 text-[15px] font-medium text-[var(--cuadrao-green)] underline-offset-4 hover:underline ${FOCUS_RING} disabled:opacity-40`;
/** A destructive action: red, and always behind a confirmation. */
export const dangerButtonClass = `${pillButtonClass} border border-[#9e2f39]/40 bg-white text-[#9e2f39] dark:border-[#ec9aa0]/40 dark:bg-[#1f2225] dark:text-[#ec9aa0]`;
export const dangerConfirmButtonClass = `${pillButtonClass} bg-[#9e2f39] text-white dark:bg-[#ec9aa0] dark:text-[#172b26]`;

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

export function StatusPill({ status }: { status: ReceiptStatus }) {
  return <FoundationStatusPill status={status} />;
}

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
          not_a_receipt: t("business.attention.not_a_receipt", "This doesn't look like a receipt"),
          several_purchases: t("business.attention.several_purchases", "Cuadrao couldn't match this receipt to one purchase. Enter the details yourself to save one expense."),
          source_unavailable: t("business.attention.source_unavailable", "The original file is no longer available. Enter the details yourself."),
          check_details: t("business.attention.check_details", "Cuadrao couldn't read every part of this receipt. Check the details against the original before you confirm."),
          duplicate: t("business.attention.duplicate", "This looks like a receipt you already saved: same merchant, date and total. It won't be saved as a second expense."),
          other: t("business.attention.other", "Something went wrong with this receipt. It is still saved. Enter the details yourself."),
        } satisfies Record<ReceiptAttention, string>)[attention]
      : "";
}

/** Title and body for a terminal read. Other attention values keep the one-line label. */
export function useTerminalRead() {
  const { t } = useTranslation();
  return (attention: ReceiptAttention | null, errorCode: string | null) => {
    const uploadLabel = t("business.file_read.upload_another", "Upload another file");
    const enterLabel = t("business.file_read.enter_details", "Enter details");
    if (
      attention === "unreadable" &&
      (errorCode === "unreadable_document" || errorCode === "receipt_requires_review")
    ) {
      return {
        title: t("business.file_read.unreadable_title", "We couldn't read this file"),
        body: t(
          "business.file_read.unreadable_body",
          "The image or PDF came out blurry, cropped, or damaged. Upload a clearer photo of the whole receipt, in good light, or enter the details yourself.",
        ),
        upload: true,
        uploadLabel,
        enterLabel,
      };
    }
    if (attention === "not_a_receipt") {
      return {
        title: t("business.file_read.not_a_receipt_title", "This doesn't look like a receipt."),
        body: t(
          "business.file_read.not_a_receipt_body",
          "Upload the photo or the PDF of a receipt.",
        ),
        upload: true,
        uploadLabel,
        enterLabel,
      };
    }
    return null;
  };
}

export function LoadingRows({ rows = 3, layout = "rows" }: { rows?: number; layout?: "rows" | "overview" | "detail" }) {
  const { t } = useTranslation();
  const line = "rounded-mark bg-black/[0.06] dark:bg-white/[0.08]";
  const pulse = "animate-pulse motion-reduce:animate-none";
  const fields = Array.from({ length: rows }, (_, index) => (
    <div key={index} className={layout === "overview" ? `${cardClass} min-h-40 space-y-4` : "flex min-h-20 items-center gap-3 px-3 py-3"}>
      {layout === "rows" ? <div className={`${line} h-11 w-11 shrink-0 rounded-item`} /> : null}
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

/** The person may add receipts and notes to the Business they are in: the server's prepare capability, the owner's included. */
export function canAddRecords(chosen: { capabilities: readonly string[] } | null | undefined): boolean {
  return Boolean(chosen?.capabilities.includes("prepare"));
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
/**
 * A record's marks, as the server reads them: Personal, and either "Sin
 * comprobante" (stated, out of the 606 and 607) or "Falta NCF" (no fiscal
 * number yet and none stated as missing). Nothing shows while unknown.
 */
export function recordFiscalMark(record: { sin_comprobante?: boolean; fiscal_known?: boolean; fiscal_value?: "ncf" | "ecf" | null }): "sin_comprobante" | "missing_ncf" | null {
  if (record.sin_comprobante) return "sin_comprobante";
  return record.fiscal_known && !record.fiscal_value ? "missing_ncf" : null;
}

export function RecordMarks({ personal, fiscal, markedBy = null, className = "" }: { personal?: boolean; fiscal: ReturnType<typeof recordFiscalMark>; markedBy?: string | null; className?: string }) {
  const { t } = useTranslation();
  const owner = useOwnerView();
  const chip = "inline-flex min-h-6 items-center whitespace-nowrap rounded-mark border px-2 text-[11px] font-medium";
  if (!personal && !fiscal) return null;
  const marker = personal && owner && markedBy ? t("business.marks.marked_by", "Marked by {{name}}", { name: markedBy }) : null;
  return (
    <span className={`flex flex-wrap items-center gap-1.5 ${className}`} data-testid="record-marks">
      {personal ? (
        <span data-mark="personal" title={marker ?? undefined} className={`${chip} gap-1 border-[var(--cuadrao-green)]/35 text-[var(--cuadrao-green)]`}>
          {t("business.marks.personal_chip", "Personal")}
          {marker ? <><span data-testid="personal-marked-dot" aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--cuadrao-green)]" /><span className="sr-only">{marker}</span></> : null}
        </span>
      ) : null}
      {fiscal ? <span data-mark={fiscal === "sin_comprobante" ? "sin_comprobante" : "no_fiscal"} className={`${chip} border-black/15 text-black/55 dark:border-white/15 dark:text-white/55`}>{fiscal === "sin_comprobante" ? t("business.marks.sin_comprobante_chip", "No comprobante") : t("business.marks.missing_ncf_chip", "NCF missing")}</span> : null}
    </span>
  );
}

/** A short announcement with one way back, for a change the person can undo. */
