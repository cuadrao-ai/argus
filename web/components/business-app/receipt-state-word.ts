"use client";

import { useTranslation } from "react-i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import { savedUnread } from "./ReceiptReadNotice";

/** Where a receipt stands, in the Bandeja's words. Every list and preview that names it reads it here. */
export function useReceiptStateWord() {
  const { t } = useTranslation();
  return (receipt: ReceiptSummary): string => {
    if (receipt.status === "confirmed") return t("business.status.pill_approved", "Approved");
    if (receipt.status === "dismissed") return t("business.status.dismissed", "Dismissed");
    if (receipt.status === "needs_attention" || receipt.attention) {
      return receipt.attention ? t(`business.attention_short.${receipt.attention}`, t("business.attention_short.other", "Needs attention")) : "";
    }
    if (receipt.bandeja?.leyendo) return t("business.inbox.row_reading", "Reading…");
    if (savedUnread(receipt)) return t("business.inbox.row_saved", "Saved, not read");
    return t("business.inbox.row_ready", "Ready to review");
  };
}
