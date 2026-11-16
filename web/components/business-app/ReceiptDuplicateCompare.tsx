"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, Check, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { resolveBusinessDuplicate } from "@/lib/business-api";
import { BUSINESS_COMPARED_FIELDS, type BusinessComparedDocument, type BusinessComparedField, type BusinessDossier, type BusinessDuplicateCandidate, type BusinessDuplicateDecision } from "@/lib/business-dossier";
import { resolveLanguage } from "@/lib/language-features";
import { randomId } from "@/lib/random-id";
import { dangerButtonClass, dangerConfirmButtonClass, primaryButtonClass, secondaryButtonClass, useChannelLabel } from "./business-ui";
import { formatDay, formatMoney, formatTimestamp, UNKNOWN_VALUE } from "./business-format";
import ReceiptSourcePreview from "./ReceiptSourcePreview";
import { StatusChip } from "./foundation/StatusChip";
import { showToast } from "./foundation/toasts";
import { DUPLICATE_KEYS as KEYS } from "./dossier-attention";

/**
 * Which candidate the review panel compares now, if any. A candidate the server no longer lists, another draft or a
 * document that is no longer open ends the compare view on its own.
 */
export function useDuplicateCompare(dossier: BusinessDossier | null) {
  const [shown, setShown] = useState<{ draftId: string; otherId: string } | null>(null);
  // Where focus lands once the review is back: the first enabled match, in order.
  const focusAfter = useRef<string[]>([]);
  useEffect(() => {
    if (shown || !focusAfter.current.length) return;
    const targets = focusAfter.current;
    focusAfter.current = [];
    for (const selector of targets) {
      const target = Array.from(document.querySelectorAll<HTMLElement>(selector)).find((item) => !item.matches(":disabled"));
      if (target) { target.focus(); return; }
    }
  }, [shown]);
  const close = (targets: string[]) => { focusAfter.current = targets; setShown(null); };
  const candidate = shown && dossier?.draft_id === shown.draftId && dossier.review_state === "open"
    ? dossier.duplicate_candidates?.find((item) => item.draft_id === shown.otherId) ?? null
    : null;
  return {
    candidate,
    open: (otherId: string) => { if (dossier) setShown({ draftId: dossier.draft_id, otherId }); },
    back: () => close([`[data-compare="${shown?.otherId}"]`]),
    /** A decision kept the document: the review's main action, else what the top box still asks. */
    settled: () => close(["[data-review-primary]", '[data-testid="dossier-attention"] button']),
  };
}

function shownValue(field: BusinessComparedField, document: BusinessComparedDocument, locale: string): string {
  switch (field) {
    case "occurred_on": return formatDay(document.occurred_on, locale) || UNKNOWN_VALUE;
    case "amount": return formatMoney(document.amount, document.currency, locale) || document.amount || UNKNOWN_VALUE;
    default: return document[field] || UNKNOWN_VALUE;
  }
}

function fileName(document: BusinessComparedDocument): string {
  return document.file ? document.file.filename || document.file.media_type : UNKNOWN_VALUE;
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
 * The review panel turned into the compare view: the server's recommendation, a split diff of both documents' main
 * data (each column head names its file and where and when it arrived; a row the server's differences list carries the
 * Diferente chip after its name, any other a quiet check), both originals in the existing preview, and in the footer
 * Volver and the decisions the server lists for this pair, never another. `frame` places the body and the footer in the panel.
 */
export function ReceiptDuplicateCompare({ dossier, candidate, busy = false, onBack, onBusyChange, onChanged, onDeleted, frame }: {
  dossier: BusinessDossier;
  candidate: BusinessDuplicateCandidate;
  busy?: boolean;
  onBack: () => void;
  onBusyChange: (busy: boolean) => void;
  /** The decision kept the document; the compare view is done. */
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
  const channelLabel = useChannelLabel();
  const { comparison } = candidate;
  // Under each file name: this one, or the other's state, then where and when it arrived.
  const arrival = (side: "document" | "other", item: BusinessComparedDocument) => [
    side === "document" ? t(`${KEYS}.column.this`) : item.state === "accepted" ? t("business.status.pill_approved") : t(`${KEYS}.column.saved_before`),
    item.file ? channelLabel(item.file.channel) : null,
    item.received_at ? formatTimestamp(item.received_at, locale) : null,
  ].filter(Boolean).join(" · ");
  const sides = [["document", comparison.document], ["other", comparison.other]] as const;
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
      else {
        showToast({ kind: "success", text: t(`${KEYS}.marked_different`) });
        onChanged(next);
      }
    } catch (error) {
      const code = error !== null && typeof error === "object" && "code" in error ? error.code : null;
      setProblem(code === "stale_version" || code === "duplicate_evidence_changed" ? t("business.dossier.stale")
        : code === "duplicate_same_comprobante" ? t(`${KEYS}.refused_same_comprobante`)
        : t("business.dossier.refused"));
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
          <th scope="col" className="w-[36%] py-2 pr-2 font-normal"><span className="sr-only">{t(`${KEYS}.table.field`)}</span></th>
          {sides.map(([side, item]) => <th key={side} scope="col" data-compare-side={side} className="py-2 pr-2 align-bottom font-normal">
            <span data-compare-file className="block break-words font-medium text-[#172b26] dark:text-white">{fileName(item)}</span>
            <span data-compare-arrival className="mt-0.5 block text-[12px] leading-4">{arrival(side, item)}</span>
          </th>)}
        </tr>
      </thead>
      <tbody>
        {BUSINESS_COMPARED_FIELDS.map((field) => {
          const different = differs.has(field);
          return <tr key={field} data-testid="duplicate-compare-row" data-field={field} data-state={different ? "different" : "same"} className={`border-t border-[#DCE0DA] align-top dark:border-white/10 ${different ? "bg-[#fdf6ec] dark:bg-[#2a241c]" : ""}`}>
            <th scope="row" className="py-2 pl-1 pr-2 text-left font-normal text-[#56635e] dark:text-white/70">
              <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span>{t(`${KEYS}.field.${field}`)}</span>
                {different
                  ? <StatusChip tone="warning" data-compare-marker="different">{t(`${KEYS}.different`)}</StatusChip>
                  : <Check role="img" aria-label={t(`${KEYS}.same`)} data-compare-marker="same" strokeWidth={2} className="h-4 w-4 shrink-0 text-[#56635e] dark:text-white/60" />}
              </span>
            </th>
            <td className={`break-words py-2 pr-2 text-[#172b26] dark:text-white ${field === "amount" ? "cuadrao-amount tabular-nums" : ""}`}>{shownValue(field, comparison.document, locale)}</td>
            <td className={`break-words py-2 pr-2 text-[#172b26] dark:text-white ${field === "amount" ? "cuadrao-amount tabular-nums" : ""}`}>{shownValue(field, comparison.other, locale)}</td>
          </tr>;
        })}
      </tbody>
    </table>
    <div className="grid gap-4 @[40rem]:grid-cols-2">
      {sides.map(([side, item]) => <ComparedPreview key={side} label={arrival(side, item)} document={item} />)}
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
