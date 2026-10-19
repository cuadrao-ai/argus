"use client";

import { useTranslation } from "react-i18next";
import type { ReceiptStatus } from "@/lib/business-api";
import { BUSINESS_STATUS, statusNameForReceipt } from "./presentation";

export function StatusPill({ status }: { status: ReceiptStatus }) {
  const { t } = useTranslation();
  const name = statusNameForReceipt(status);
  const tone = BUSINESS_STATUS[name];
  const label = t(tone.labelKey, tone.label);
  return (
    <span
      data-testid="status-pill"
      data-status={name}
      className="inline-flex min-h-6 shrink-0 items-center gap-1 rounded-full px-2 text-[12px] font-medium leading-4"
      style={{ color: tone.ink, backgroundColor: tone.surface }}
    >
      <span aria-hidden="true" data-testid="status-dot" className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: tone.ink }} />
      <span className="whitespace-normal break-words">{label}</span>
    </span>
  );
}
