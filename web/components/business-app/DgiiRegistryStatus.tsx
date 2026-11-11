"use client";

import { useCallback, useContext, useEffect, useId, useState } from "react";
import { AlertCircle, Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { RegistryAnswer, TaxId } from "@/lib/business-dgii";
import { referenceCode } from "@/lib/failure-screen";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { BusinessContext } from "./BusinessWorkspace";
import { quietButtonClass } from "./business-ui";

/** The registry check of the tax id on screen. */
export type RegistryLookup = { status: "checking" } | { status: "failed"; reference: string } | { status: "done"; answer: RegistryAnswer };

/** What the registry says of one tax id, in the block's words. */
export type RegistryStatus =
  | { status: "checking" }
  | { status: "failed"; reference: string; name: string | null }
  | { status: "verified"; name: string }
  | { status: "inactive"; name: string; registryStatus: string }
  | { status: "unverified"; name: string | null };

/** `pending` is a listed name nobody has confirmed yet; only a screen that stores a confirmation shows it. */
export type RegistryStatusState = RegistryStatus | { status: "pending"; name: string };

/**
 * Asks the workspace's registry about one tax id. `lookup` is null when there is nothing to ask:
 * no tax id, or a source with no registry (the sample and the local preview).
 * An answer for an earlier tax id never lands on the current one.
 */
export function useRegistryLookup(taxId: TaxId | null): { lookup: RegistryLookup | null; retry: () => void } {
  const source = useContext(BusinessContext)?.source.lookupRegistry;
  const type = taxId?.type;
  const value = taxId?.value;
  const key = source && type && value ? `${type}:${value}` : null;
  const [settled, setSettled] = useState<{ key: string; lookup: RegistryLookup } | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!source || !type || !value) return;
    const asked = `${type}:${value}`;
    const controller = new AbortController();
    setSettled(null);
    source({ type, value }, controller.signal)
      .then((answer) => { if (!controller.signal.aborted) setSettled({ key: asked, lookup: { status: "done", answer } }); })
      .catch((error: unknown) => { if (!controller.signal.aborted) setSettled({ key: asked, lookup: { status: "failed", reference: referenceCode(error) } }); });
    return () => controller.abort();
  }, [source, type, value, attempt]);
  const retry = useCallback(() => setAttempt((count) => count + 1), []);
  if (!key) return { lookup: null, retry };
  return { lookup: settled?.key === key ? settled.lookup : { status: "checking" }, retry };
}

export function registryStatusOf(lookup: RegistryLookup): RegistryStatus {
  if (lookup.status === "checking") return lookup;
  if (lookup.status === "failed") return { status: "failed", reference: lookup.reference, name: null };
  const { verification, record } = lookup.answer;
  if (!record || verification === "sin_verificar") return { status: "unverified", name: null };
  if (verification === "no_activo") return { status: "inactive", name: record.name, registryStatus: record.status };
  return { status: "verified", name: record.name };
}

const TAGS = {
  verified: "bg-[#E3EFE8] text-[#2f5a49] dark:bg-[#8fcbb0]/15 dark:text-[#8fcbb0]",
  neutral: "bg-[#EDECE6] text-[#56635e] dark:bg-white/10 dark:text-white/80",
  inactive: "bg-[#F6EBD4] text-[#7a5512] dark:bg-[#f6e7c1]/15 dark:text-[#f6e7c1]",
} as const;

/**
 * The one rendering of a registry check: the pulse while it waits, the failure with its reference and retry,
 * and the tag with the DGII source line and the registered name.
 * With a `label` it is a form field (label and tag, name, source). Without one it sits under a number (tag, source, name).
 */
export default function DgiiRegistryStatus({ state, onRetry, testId, label }: { state: RegistryStatusState; onRetry: () => void; testId: string; label?: string }) {
  const { t } = useTranslation();
  const labelId = useId();
  const heading = label ? <span id={labelId} className="text-[15px] font-medium">{label}</span> : null;
  if (state.status === "checking") {
    return <div data-testid={testId} data-legal-name-status="checking" aria-busy="true" aria-labelledby={label ? labelId : undefined} className="space-y-1">{heading}<div aria-hidden="true" className="h-5 w-2/3 animate-pulse rounded-item bg-black/5 dark:bg-white/10" /></div>;
  }
  const name = state.name
    ? <p data-testid={`${testId}-value`} className={`${label ? "text-[16px]" : "text-[14px] leading-5"} [overflow-wrap:anywhere]`}>{state.name}</p>
    : null;
  if (state.status === "failed") {
    return <div data-testid={testId} data-legal-name-status="failed" className="min-w-0 space-y-1">{heading}
      {name}
      <div role="alert" className="flex items-start gap-2 text-[14px] leading-relaxed text-[#9e2f39] dark:text-[#ec9aa0]">
        <AlertCircle className="mt-[3px] h-4 w-4 shrink-0" aria-hidden="true" />
        <div className="min-w-0"><p>{t("common.error_occurred")} <ReferenceCode reference={state.reference} /></p><button type="button" onClick={onRetry} className={`${quietButtonClass} -ml-1`}>{t("common.retry")}</button></div>
      </div>
    </div>;
  }
  const tag = state.status === "verified"
    ? <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-medium ${TAGS.verified}`}><Check className="h-3 w-3" aria-hidden="true" />{t("business.dgii.legal_name.tag_verified")}</span>
    : state.status === "inactive"
      ? <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[12px] font-medium ${TAGS.inactive}`}><span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />{t("business.dgii.legal_name.tag_inactive")}</span>
      : <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[12px] font-medium ${TAGS.neutral}`}>{t(state.status === "pending" ? "business.dgii.legal_name.tag_pending" : "business.dgii.legal_name.tag_unverified")}</span>;
  // Sin verificar names no source: the registry copy is loaded by hand and can be stale.
  const sourceText = state.status === "unverified" ? null : state.status === "inactive" ? t("business.dgii.legal_name.source_status", { status: state.registryStatus }) : t("business.dgii.legal_name.source");
  const source = sourceText ? <p className={`${label ? "text-[14px]" : "text-[13px] leading-5"} text-[#56635e] dark:text-white/70`}>{sourceText}</p> : null;
  return <div data-testid={testId} data-legal-name-status={state.status} aria-live="polite" className="min-w-0 space-y-1">
    {heading ? <><div className="flex flex-wrap items-center gap-2">{heading}{tag}</div>{name ?? <p className="text-[16px] text-[#56635e] dark:text-white/70">-</p>}{source}</> : <><div className="flex">{tag}</div>{source}{name}</>}
  </div>;
}
