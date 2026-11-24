"use client";

import { useTranslation } from "react-i18next";
import type { ReceptionTag } from "../recepcion/reception-status";
import { BUSINESS_STATUS, statusNameForTag } from "./presentation";

export function StatusPill({ tag }: { tag: ReceptionTag["tag"] }) {
  const { t } = useTranslation();
  const name = statusNameForTag(tag);
  const tone = BUSINESS_STATUS[name];
  const label = t(tone.labelKey, tone.label);
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
