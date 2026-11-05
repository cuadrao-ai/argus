"use client";

import { useTranslation } from "react-i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import { cardClass } from "./business-ui";

/**
 * The one sentence for a receipt saved without a read, naming only what the
 * person can do now: the per-receipt "Preparar con IA" button is the consent
 * for web and email receipts.
 */
export function savedUnreadLine(t: (key: string, fallback: string) => string, preparable: boolean): string {
  if (preparable) return t("business.review.saved_prepare_only", "Saved, unread. Press “Prepare with AI” so Cuadrao reads it.");
  return t("business.review.saved_waiting", "Saved, unread.");
}

/** A receipt nothing is reading and nothing will read until a person acts, as the server projects it. */
export function savedUnread(receipt: Pick<ReceiptSummary, "activity">): boolean {
  return receipt.activity?.state === "saved_unread";
}

/** What is happening to the receipt's read: the server's Bandeja flag says it is being read, its activity that it waits for a person. */
export default function ReceiptReadNotice({ receipt, preparable }: { receipt: Pick<ReceiptSummary, "activity" | "bandeja">; preparable: boolean }) {
  const { t } = useTranslation();
  if (receipt.bandeja?.leyendo) {
    return (
      <div role="status" data-testid="receipt-read-notice" data-state="reading" className={`${cardClass} text-[14px] text-black/70 dark:text-white/70`}>
        {t("business.review.preparing", "Reading your receipt. You can leave this page; the result will wait in your inbox.")}
      </div>
    );
  }
  if (!savedUnread(receipt)) return null;
  const line = savedUnreadLine(t, preparable);
  return (
    <p data-testid="receipt-read-notice" data-state="waiting" className="text-[14px] text-black/65 dark:text-white/65">
      {line}
    </p>
  );
}
