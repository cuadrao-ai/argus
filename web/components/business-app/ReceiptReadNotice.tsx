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
  const line =
    enterable && preparable
      ? t("business.review.saved_by_hand", "Saved. Nothing is reading it: fill in the details by hand whenever you like, or ask for an AI read.")
      : enterable
        ? t("business.review.saved_by_hand_only", "Saved. Nothing is reading it: fill in the details by hand whenever you like.")
        : preparable
          ? t("business.review.saved_prepare_only", "Saved. Nothing is reading it: ask for an AI read whenever you like.")
          : t("business.review.saved_waiting", "Saved. Nothing is reading it.");
  return (
    <p data-testid="receipt-read-notice" data-state="waiting" className="text-[14px] text-black/65 dark:text-white/65">
      {line}
    </p>
  );
}
