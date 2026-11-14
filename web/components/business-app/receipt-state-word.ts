"use client";

import { useTranslation } from "react-i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import { receiptTag } from "./recepcion/reception-status";

/** A receipt's status, from the server's Bandeja group. The reason it needs attention is a separate fact and is never shown here. */
export function useReceiptStateWord() {
  const { t } = useTranslation();
  return (receipt: ReceiptSummary): string => {
    if (receipt.deleted) return t("business.document_delete.deleted_state");
    const state = receiptTag(receipt);
    if (state.tag === "approved") return t("business.status.pill_approved", "Approved");
    if (state.tag === "dismissed") return t("business.status.dismissed", "Dismissed");
    if (state.tag === "listo") return t("business.inbox.row_ready", "Ready to review");
    if (state.tag === "reading") return t("business.inbox.row_reading", "Reading…");
    return t("business.status.pill_attention", "Needs attention");
  };
}
