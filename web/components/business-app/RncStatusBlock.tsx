"use client";

import { useTranslation } from "react-i18next";
import type { BusinessFact } from "@/lib/business-dossier";
import { formatRnc, rncStatus } from "@/lib/rnc-status";

const TONES = {
  missing: { color: "#9e2f39", backgroundColor: "#f6dfe0" },
  invalid_length: { color: "#9e2f39", backgroundColor: "#f6dfe0" },
  unverified: { color: "#735c14", backgroundColor: "#f2e8c9" },
};

export default function RncStatusBlock({ fact, onEditRnc }: {
  fact?: BusinessFact<string> | null;
  onEditRnc?: () => void;
}) {
  const { t } = useTranslation();
  const status = rncStatus(fact);
  const label = t(`business.dgii.rnc_check.${status}.label`);
  return <div data-testid="rnc-status" data-rnc-status={status}>
    {fact?.state === "known" && fact.value.trim() ? <p className="mb-1.5 tabular-nums">{formatRnc(fact.value)}</p> : null}
    <span role="status" aria-label={t("business.dgii.rnc_check.aria", { label })} className="inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[12px] font-medium" style={TONES[status]}>
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />{label}
    </span>
    <p className="mt-1 text-[14px] leading-5 text-black/55 dark:text-white/55">{t(`business.dgii.rnc_check.${status}.reason`)}</p>
    {onEditRnc && status !== "unverified" ? <button type="button" onClick={onEditRnc} className="mt-1 min-h-11 min-w-11 rounded-lg text-[14px] underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]">{t(`business.dgii.rnc_check.${status}.action`)}</button> : null}
  </div>;
}
