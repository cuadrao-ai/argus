"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, CircleAlert, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { resolveBusinessDuplicate } from "@/lib/business-api";
import { BUSINESS_COMPARED_FIELDS, type BusinessComparedDocument, type BusinessComparedField, type BusinessDossier, type BusinessDuplicateCandidate, type BusinessDuplicateDecision } from "@/lib/business-dossier";
import { resolveLanguage } from "@/lib/language-features";
import { randomId } from "@/lib/random-id";
import { dangerButtonClass, dangerConfirmButtonClass, primaryButtonClass, secondaryButtonClass } from "./business-ui";
import { formatDay, formatMoney, UNKNOWN_VALUE } from "./business-format";
import ReceiptSourcePreview from "./ReceiptSourcePreview";

const KEYS = "business.receipts.duplicate_resolution";

/**
 * Which candidate the review panel compares now, if any. A candidate the server no longer lists, another draft or a
 * document that is no longer open ends the compare view on its own.
 */
export function useDuplicateCompare(dossier: BusinessDossier | null) {
  const [shown, setShown] = useState<{ draftId: string; otherId: string } | null>(null);
  const candidate = shown && dossier?.draft_id === shown.draftId && dossier.review_state === "open"
    ? dossier.duplicate_candidates?.find((item) => item.draft_id === shown.otherId) ?? null
    : null;
  return {
    candidate,
    open: (otherId: string) => { if (dossier) setShown({ draftId: dossier.draft_id, otherId }); },
    back: () => {
      const otherId = shown?.otherId;
      setShown(null);
      requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-compare="${otherId}"]`)?.focus());
    },
  };
}

/** The amber "Parece repetido" box: why, as the server says it, and Comparar. It decides nothing. */
export function ReceiptDuplicateResolution({ dossier, busy = false, onCompare }: {
  dossier: BusinessDossier;
  busy?: boolean;
  onCompare: (otherId: string) => void;
}) {
  const { t } = useTranslation();
  const candidates = dossier.duplicate_candidates ?? [];
  if (!candidates.length || dossier.review_state !== "open") return null;
  return <section data-testid="receipt-duplicate-resolution" aria-labelledby="duplicate-resolution-title" className="rounded-surface border border-[#e6c9a8] bg-[#fdf6ec] px-4 py-3 dark:border-[#6b5235] dark:bg-[#2a241c]">
    <h3 id="duplicate-resolution-title" className="flex items-center gap-2 text-[14px] font-medium leading-5 text-[#172b26] dark:text-white">
      <CircleAlert className="h-4 w-4 shrink-0 text-[#9a5b13] dark:text-[#e8b26f]" aria-hidden="true" />
      {t(`${KEYS}.title`)}
    </h3>
    {candidates.map((candidate) => <div key={candidate.draft_id} className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <p data-testid="duplicate-basis" className="min-w-0 flex-1 basis-48 text-[14px] leading-5 text-[#172b26] dark:text-white">{t(`${KEYS}.basis.${candidate.basis}`)}</p>
      <button type="button" data-compare={candidate.draft_id} className={secondaryButtonClass} disabled={busy} onClick={() => onCompare(candidate.draft_id)}>{t(`${KEYS}.compare`)}</button>
    </div>)}
  </section>;
}

function shownValue(field: BusinessComparedField, document: BusinessComparedDocument, locale: string): string {
  switch (field) {
    case "occurred_on": return formatDay(document.occurred_on, locale) || UNKNOWN_VALUE;
    case "amount": return formatMoney(document.amount, document.currency, locale) || document.amount || UNKNOWN_VALUE;
    case "file": return document.file ? document.file.filename || document.file.media_type : UNKNOWN_VALUE;
    default: return document[field] || UNKNOWN_VALUE;
  }
}

function ComparedPreview({ label, document }: { label: string; document: BusinessComparedDocument }) {
  const { t } = useTranslation();
  return <div className="min-w-0 space-y-2" data-testid="duplicate-compare-document">
    <h4 className="text-[13px] font-medium leading-[18px] text-[#56635e] dark:text-white/70">{label}</h4>
    {document.file
      ? <ReceiptSourcePreview initialExpanded showArrivalContext={false} detail={{ id: document.file.connection_id, filename: document.file.filename, media_type: document.file.media_type }} />
      : <p className="text-[14px] text-[#56635e] dark:text-white/70">{t(`${KEYS}.no_file`)}</p>}
  </div>;
}

/** A decision's look: the recommended one is the screen's primary; a delete stays red either way. */
function decisionClass(decision: BusinessDuplicateDecision, recommended: boolean): string {
  if (decision === "same_purchase") return recommended ? dangerConfirmButtonClass : dangerButtonClass;
  return recommended ? primaryButtonClass : secondaryButtonClass;
}

/**
 * The review panel turned into the compare view: the server's recommendation, the main data of both documents marked
 * Igual or Diferente by the server's differences, both originals in the existing preview, and in the footer Volver
 * and the decisions the server lists for this pair, never another. `frame` places the body and the footer in the panel.
 */
export function ReceiptDuplicateCompare({ dossier, candidate, busy = false, onBack, onBusyChange, onChanged, onDeleted, frame }: {
  dossier: BusinessDossier;
  candidate: BusinessDuplicateCandidate;
  busy?: boolean;
  onBack: () => void;
  onBusyChange: (busy: boolean) => void;
  onChanged: (next: BusinessDossier) => void;
  /** The reviewed document went to Eliminados. */
  onDeleted: (gone: BusinessDossier) => void;
  frame: (body: ReactNode, footer: ReactNode) => ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const [working, setWorking] = useState<BusinessDuplicateDecision | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const inFlight = useRef(false);
  const request = useRef<{ draftId: string; version: number; otherId: string; otherVersion: number; decision: BusinessDuplicateDecision; key: string } | null>(null);
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => { title.current?.focus(); }, []);
  const { comparison } = candidate;
  const differs = new Set(comparison.differences);
  const recommended = comparison.recommendation;
  const decisions = [...candidate.decisions.filter((item) => item !== recommended), ...candidate.decisions.filter((item) => item === recommended)];
  const locked = busy || working !== null;

  const decide = async (decision: BusinessDuplicateDecision) => {
    if (inFlight.current || busy || !candidate.decisions.includes(decision)) return;
    inFlight.current = true;
    setWorking(decision);
    onBusyChange(true);
    setProblem(null);
    const saved = request.current;
    // A retry of the same request keeps its key, so the server answers it once.
    const command = saved?.draftId === dossier.draft_id && saved.version === dossier.version && saved.otherId === candidate.draft_id && saved.otherVersion === candidate.version && saved.decision === decision
      ? saved
      : { draftId: dossier.draft_id, version: dossier.version, otherId: candidate.draft_id, otherVersion: candidate.version, decision, key: randomId() };
    request.current = command;
    try {
      const next = await resolveBusinessDuplicate(command.draftId, command.version, command.otherId, command.otherVersion, decision, command.key);
      request.current = null;
      if (next.deleted) onDeleted(next);
      else onChanged(next);
    } catch (error) {
      const code = error !== null && typeof error === "object" && "code" in error ? error.code : null;
      setProblem(code === "stale_version" || code === "duplicate_evidence_changed" ? t("business.dossier.stale") : t("business.dossier.refused"));
    } finally {
      inFlight.current = false;
      setWorking(null);
      onBusyChange(false);
    }
  };

  const body = <div data-testid="duplicate-compare" aria-busy={working !== null} className="@container space-y-5">
    <div>
      <h3 ref={title} tabIndex={-1} data-testid="duplicate-compare-title" className="rounded-mark text-[16px] font-medium leading-6 text-[#172b26] focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-white">{t(`${KEYS}.title`)}</h3>
      {recommended ? <p data-testid="duplicate-recommendation" className="mt-1 text-[15px] leading-[22px] text-[#172b26] dark:text-white">{t(`${KEYS}.recommendation.${recommended}`)}</p> : null}
    </div>
    <table className="w-full table-fixed border-collapse text-[14px] leading-5">
      <caption className="sr-only">{t(`${KEYS}.table.caption`)}</caption>
      <thead>
        <tr className="text-left text-[13px] leading-[18px] text-[#56635e] dark:text-white/70">
          <th scope="col" className="w-[22%] py-2 pr-2 font-normal"><span className="sr-only">{t(`${KEYS}.table.field`)}</span></th>
          <th scope="col" className="py-2 pr-2 font-medium">{t(`${KEYS}.documents.this`)}</th>
          <th scope="col" className="py-2 pr-2 font-medium">{t(`${KEYS}.documents.other`)}</th>
          <th scope="col" className="w-[24%] py-2 font-normal"><span className="sr-only">{t(`${KEYS}.table.state`)}</span></th>
        </tr>
      </thead>
      <tbody>
        {BUSINESS_COMPARED_FIELDS.map((field) => {
          const different = differs.has(field);
          return <tr key={field} data-testid="duplicate-compare-row" data-field={field} data-state={different ? "different" : "same"} className={`border-t border-[#DCE0DA] align-top dark:border-white/10 ${different ? "bg-[#fdf6ec] dark:bg-[#2a241c]" : ""}`}>
            <th scope="row" className="py-2 pl-1 pr-2 text-left font-normal text-[#56635e] dark:text-white/70">{t(`${KEYS}.field.${field}`)}</th>
            <td className={`break-words py-2 pr-2 text-[#172b26] dark:text-white ${field === "amount" ? "cuadrao-amount tabular-nums" : ""}`}>{shownValue(field, comparison.document, locale)}</td>
            <td className={`break-words py-2 pr-2 text-[#172b26] dark:text-white ${field === "amount" ? "cuadrao-amount tabular-nums" : ""}`}>{shownValue(field, comparison.other, locale)}</td>
            <td className={`py-2 pr-1 text-right text-[13px] ${different ? "font-medium text-[#9a5b13] dark:text-[#e8b26f]" : "text-[#56635e] dark:text-white/70"}`}>{t(`${KEYS}.${different ? "different" : "same"}`)}</td>
          </tr>;
        })}
      </tbody>
    </table>
    <div className="grid gap-4 @[40rem]:grid-cols-2">
      <ComparedPreview label={t(`${KEYS}.documents.this`)} document={comparison.document} />
      <ComparedPreview label={t(`${KEYS}.documents.other`)} document={comparison.other} />
    </div>
  </div>;

  const footer = <div className="flex flex-wrap items-center justify-between gap-2">
    {problem ? <p role="alert" className="basis-full text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{problem}</p> : null}
    <button type="button" className={secondaryButtonClass} disabled={locked} onClick={onBack}><ArrowLeft className="h-4 w-4" aria-hidden="true" />{t("common.back")}</button>
    {decisions.length ? <div className="flex flex-wrap items-center justify-end gap-2">
      {decisions.map((decision) => <button key={decision} type="button" aria-busy={working === decision} className={`${decisionClass(decision, decision === recommended)} whitespace-nowrap`} disabled={locked} onClick={() => void decide(decision)}>
        {working === decision ? <Loader2 className="h-[18px] w-[18px] animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
        {t(`${KEYS}.decision.${decision}`)}
      </button>)}
    </div> : null}
  </div>;

  return frame(body, footer);
}
