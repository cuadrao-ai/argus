"use client";

import { useTranslation } from "react-i18next";
import type { ReceiptStatus } from "@/lib/business-api";
import { BUSINESS_STATUS, statusNameForReceipt } from "./presentation";

/** `label` names a finer state in the status's colour and mark, as a search preview names what its row says. */
export function StatusPill({ status, label: stateLabel }: { status: ReceiptStatus; label?: string }) {
  const { t } = useTranslation();
  const name = statusNameForReceipt(status);
  const tone = BUSINESS_STATUS[name];
  const label = stateLabel || t(tone.labelKey, tone.label);
  const Icon = tone.icon;
  return (
    <span
      data-testid="status-pill"
      data-status={name}
      className="inline-flex h-6 shrink-0 items-center gap-1 whitespace-nowrap rounded-mark px-2 text-[12px] font-medium leading-4"
      style={{ color: tone.ink, backgroundColor: tone.surface }}
    >
      <Icon aria-hidden="true" width={14} height={14} strokeWidth={2} className="shrink-0" />
      {label}
    </span>
  );
}
