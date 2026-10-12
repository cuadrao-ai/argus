"use client";

import { useState } from "react";
import { ChevronRight, FileText, ImageIcon, MessageCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import { receiptsGroupedUnderEmails, type BusinessEmailDelivery } from "@/lib/business-email";
import BusinessEmailDeliveries from "./BusinessEmailDeliveries";
import { useBusiness } from "./BusinessWorkspace";
import { formatMoney, formatRelativeTime } from "./business-format";
import { cardClass, LoadingRows, PanelHeading, primaryButtonClass, StatusPill, useAttentionLabel } from "./business-ui";

export function ReceiptRow({ receipt, onOpen }: { receipt: ReceiptSummary; onOpen: () => void }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const attentionLabel = useAttentionLabel();
  const Icon = receipt.media_type === "application/pdf" ? FileText : ImageIcon;
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-center gap-3 rounded-[16px] px-3 py-3 text-left transition-colors hover:bg-black/[0.03] focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:hover:bg-white/[0.04]"
      >
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[12px] bg-black/[0.04] dark:bg-white/[0.06]">
          <Icon className="h-5 w-5 text-black/55 dark:text-white/55" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[15px] font-medium text-black dark:text-white">
            {receipt.merchant ?? receipt.filename ?? t("business.receipt.untitled", "Receipt")}
          </span>
          <span className="mt-0.5 flex items-center gap-1.5 truncate text-[13px] text-black/50 dark:text-white/50">
            {receipt.channel === "whatsapp" ? (
              <MessageCircle className="h-3.5 w-3.5 shrink-0" aria-label="WhatsApp" />
            ) : null}
            {receipt.attention
              ? attentionLabel(receipt.attention)
              : formatRelativeTime(receipt.received_at, locale)}
          </span>
        </span>
        <span className="hidden text-right text-[15px] font-medium tabular-nums text-black dark:text-white mobile:block">
          {formatMoney(receipt.amount, receipt.currency, locale)}
        </span>
        <StatusPill status={receipt.status} />
        <ChevronRight className="h-4 w-4 shrink-0 text-black/30 dark:text-white/30" />
      </button>
    </li>
  );
}

export default function BusinessInboxPanel() {
  const { t } = useTranslation();
  const { records, openPanel, actions } = useBusiness();
  // An email's own ".eml" document stays inside its email row once an attachment is saved.
  const [grouped, setGrouped] = useState<ReadonlySet<string>>(new Set());
  const items = records.inbox?.filter((receipt) => !receipt.email_original && !grouped.has(receipt.id)) ?? null;
  const onGrouped = (deliveries: readonly BusinessEmailDelivery[]) => setGrouped(receiptsGroupedUnderEmails(deliveries));

  const upload = actions.create.find((action) => action.id === "upload_receipt");

  return (
    <section>
      <PanelHeading
        title={t("business.inbox.title", "Inbox")}
        subtitle={t("business.inbox.subtitle", "Receipts waiting for you to review. Nothing here is an expense until you confirm it.")}
        action={
          upload ? (
            <button type="button" className={primaryButtonClass} onClick={upload.run}>
              {upload.label}
            </button>
          ) : null
        }
      />
      <BusinessEmailDeliveries onGrouped={onGrouped} />
      {records.error ? (
        <p role="alert" className="text-[14px] text-black/70 dark:text-white/70">
          {t("business.inbox.error", "We couldn't load your inbox. Try again.")}
        </p>
      ) : items === null ? (
        <LoadingRows />
      ) : items.length === 0 ? (
        <div className={`${cardClass} text-center`}>
          <p className="font-display text-[18px] font-medium text-black dark:text-white">
            {t("business.inbox.empty_title", "You're all caught up")}
          </p>
          <p className="mt-1 text-[14px] text-black/55 dark:text-white/55">
            {t("business.inbox.empty_body", "Upload a receipt or send one by WhatsApp. It will wait here for your review.")}
          </p>
        </div>
      ) : (
        <ul className={`${cardClass} divide-y divide-black/[0.05] p-2 dark:divide-white/[0.05]`}>
          {items.map((receipt) => (
            <ReceiptRow
              key={receipt.id}
              receipt={receipt}
              onOpen={() => openPanel({ kind: "receipt", receiptId: receipt.id })}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
