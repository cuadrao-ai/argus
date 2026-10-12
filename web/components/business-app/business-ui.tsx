"use client";

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { ReceiptAttention, ReceiptStatus } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";

export const cardClass =
  "rounded-[20px] border border-black/[0.06] bg-white p-5 dark:border-white/[0.06] dark:bg-[#1f2225]";

export const pillButtonClass =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 text-[15px] font-medium transition-opacity hover:opacity-85 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 disabled:opacity-40 dark:focus-visible:ring-white/30";

export const primaryButtonClass = `${pillButtonClass} bg-black text-white dark:bg-white dark:text-black`;
export const secondaryButtonClass = `${pillButtonClass} border border-black/10 bg-white text-black dark:border-white/10 dark:bg-[#1f2225] dark:text-white`;

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

export function LoadingRows({ rows = 3 }: { rows?: number }) {
  const { t } = useTranslation();
  return (
    <div role="status" aria-label={t("common.loading", "Loading")} className="space-y-3">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="h-16 animate-pulse rounded-[16px] bg-black/[0.04] dark:bg-white/[0.04]" />
      ))}
    </div>
  );
}
