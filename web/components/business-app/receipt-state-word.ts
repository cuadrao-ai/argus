"use client";

import { useTranslation } from "react-i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import { BANDEJA_REASON_KEY, receiptTag } from "./recepcion/reception-status";

/** Where a receipt stands, in the Bandeja's words. Every list and preview that names it reads it here. */
export function useReceiptStateWord() {
  const { t } = useTranslation();
  return (receipt: ReceiptSummary): string => {
    if (receipt.deleted) return t("business.document_delete.deleted_state");
    const state = receiptTag(receipt);
    if (state.tag === "approved") return t("business.status.pill_approved", "Approved");
    if (state.tag === "dismissed") return t("business.status.dismissed", "Dismissed");
    if (state.tag === "listo") return t("business.inbox.row_ready", "Ready to review");
    if (state.tag === "reading") return t("business.inbox.row_reading", "Reading…");
    const reason = state.reason ? BANDEJA_REASON_KEY[state.reason] : undefined;
    return reason ? t(reason) : t("business.attention_short.other", "Needs attention");
  };
}
