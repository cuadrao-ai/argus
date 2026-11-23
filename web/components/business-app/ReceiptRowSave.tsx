"use client";

import { useTranslation } from "react-i18next";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { supportEmail } from "@/lib/support-email";
import { quietButtonClass } from "./business-ui";
import type { RowSave } from "./receipt-review-save";

/** What a row says about its save: working, or what failed, its reference and a way out. A save that landed says nothing. */
export default function ReceiptRowSave({ save, onRetry, onCancel }: { save?: RowSave; onRetry: () => void; onCancel?: () => void }) {
  const { t } = useTranslation();
  if (!save) return null;
  if (save.state === "saving") return <span role="status" data-testid="row-saving" className="mt-1 block text-[13px] leading-[18px] text-[#56635e] dark:text-white/70">{t("business.capture.saving", "Saving…")}</span>;
  return (
    <div role="alert" data-testid="row-save-failed" className="mt-1 space-y-1 text-[13px] leading-[18px] text-[#9e2f39] dark:text-[#ec9aa0]">
      <p>{save.message}</p>
      {save.retry ? null : <p>{t("auth.business_unavailable.body", { supportEmail })}</p>}
      <div className="flex flex-wrap items-center gap-x-3">
        <ReferenceCode reference={save.reference} />
        {save.retry ? <button type="button" className={quietButtonClass} onClick={onRetry}>{t("common.retry", "Retry")}</button> : null}
        {onCancel && !save.unknown ? <button type="button" className={quietButtonClass} onClick={onCancel}>{t("common.cancel", "Cancel")}</button> : null}
      </div>
    </div>
  );
}
