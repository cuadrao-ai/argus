"use client";

import { useTranslation } from "react-i18next";
import type { ReceiptStatus } from "@/lib/business-api";
import { cardClass } from "./business-ui";

/**
 * What is happening to a saved receipt, from backend state only: "Leyendo tu
 * recibo" while a read is pending; a neutral line while nothing will read it,
 * naming only what the person can do now (fill it in by hand, ask for an AI
 * read, both, or neither); nothing otherwise.
 */
/**
 * The one sentence for a receipt saved without a read, naming only what the
 * person can do now: the per-receipt "Preparar con IA" button is the consent
 * for web and email receipts, and filling it in by hand needs no read.
 */
export function savedUnreadLine(t: (key: string, fallback: string) => string, can: { enterable: boolean; preparable: boolean }): string {
  if (can.enterable && can.preparable) return t("business.review.saved_by_hand", "Saved, unread. Press “Prepare with AI” so Cuadrao reads it, or fill it in yourself.");
  if (can.enterable) return t("business.review.saved_by_hand_only", "Saved, unread. Fill it in yourself.");
  if (can.preparable) return t("business.review.saved_prepare_only", "Saved, unread. Press “Prepare with AI” so Cuadrao reads it.");
  return t("business.review.saved_waiting", "Saved, unread.");
}

/** A saved receipt that nothing is reading and nothing will read until a person acts. */
export function savedUnread(receipt: { status: string; read_pending?: boolean | null }): boolean {
  return receipt.status === "saved" && receipt.read_pending !== true;
}

export default function ReceiptReadNotice({ status, readPending, enterable, preparable }: { status: ReceiptStatus; readPending: boolean; enterable: boolean; preparable: boolean }) {
  const { t } = useTranslation();
  if (readPending) {
    return (
      <div role="status" data-testid="receipt-read-notice" data-state="reading" className={`${cardClass} text-[14px] text-black/70 dark:text-white/70`}>
        {t("business.review.preparing", "Reading your receipt. You can leave this page; the result will wait in your inbox.")}
      </div>
    );
  }
  if (status !== "saved") return null;
  const line = savedUnreadLine(t, { enterable, preparable });
  return (
    <p data-testid="receipt-read-notice" data-state="waiting" className="text-[14px] text-black/65 dark:text-white/65">
      {line}
    </p>
  );
}
