"use client";

import { useTranslation } from "react-i18next";
import type { BusinessFact, ReviewFlag } from "@/lib/business-dossier";
import { formatRnc, rncStatus } from "@/lib/rnc-status";
import { quietButtonClass } from "./business-ui";
import DgiiRegistryStatus, { registryStatusOf, useRegistryLookup } from "./DgiiRegistryStatus";

const ERROR_TONE = { color: "#9e2f39", backgroundColor: "#f6dfe0" };

export default function RncStatusBlock({ fact, flags, onEditRnc }: {
  fact?: BusinessFact<string> | null;
  flags: readonly ReviewFlag[];
  onEditRnc?: () => void;
}) {
  const { t } = useTranslation();
  const status = rncStatus(fact, flags);
  const digits = status === "unverified" && fact?.state === "known" ? fact.value.replace(/\D/g, "") : "";
  // The registry route refuses an all-zero number, and no list holds one.
  const { lookup, retry } = useRegistryLookup(digits && !/^0+$/.test(digits) ? { type: digits.length === 9 ? "rnc" : "cedula", value: digits } : null);
  const number = fact?.state === "known" && fact.value.trim() ? <p className="mb-1.5 tabular-nums">{formatRnc(fact.value)}</p> : null;
  if (status === "unverified") {
    return <div data-testid="rnc-status" data-rnc-status={status}>
      {number}
      <DgiiRegistryStatus state={lookup ? registryStatusOf(lookup) : { status: "unverified", name: null }} onRetry={retry} testId="rnc-registry" />
    </div>;
  }
  const label = t(`business.dgii.rnc_check.${status}.label`);
  return <div data-testid="rnc-status" data-rnc-status={status}>
    {number}
    <span role="status" aria-label={t("business.dgii.rnc_check.aria", { label })} className="inline-flex items-center gap-1.5 rounded-mark px-2 py-1 text-[12px] font-medium" style={ERROR_TONE}>
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />{label}
    </span>
    <p className="mt-1 text-[14px] leading-5 text-black/55 dark:text-white/55">{t(`business.dgii.rnc_check.${status}.reason`)}</p>
    {onEditRnc && (status === "missing" || status === "invalid_length") ? <button type="button" onClick={onEditRnc} className={`${quietButtonClass} mt-1 min-w-11`}>{t(`business.dgii.rnc_check.${status}.action`)}</button> : null}
  </div>;
}
