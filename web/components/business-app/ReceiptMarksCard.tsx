"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessDossier } from "@/lib/business-dossier";
import { useBusiness } from "./BusinessWorkspace";
import { cardClass, RecordMarks } from "./business-ui";

/**
 * What the record is marked as, and the two decisions that are people's:
 * the owner or anyone holding prepare marks a receipt as personal or takes
 * the mark back (a new revision each way), so the owner can always undo
 * someone else's mark in one tap; a prepare-holder who is not the owner
 * answers whether a personal receipt with a fiscal number goes into the 606.
 * The owner reads that answer; the app never gives it.
 */
export default function ReceiptMarksCard({ dossier, busy = false, onChanged }: { dossier: BusinessDossier; busy?: boolean; onChanged: (next: BusinessDossier) => void }) {
  const { t } = useTranslation();
  const { source, chosen, reload } = useBusiness();
  const [working, setWorking] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const canPrepare = dossier.capabilities.includes("prepare");
  const owner = !chosen || chosen.role === "owner";
  // The server reads the marks; the card shows them as given.
  const personal = dossier.personal === true;
  const fiscalValue = dossier.fiscal_value ?? null;
  const inclusion = dossier.include_606 ?? null;
  const answeredBy = dossier.history.at(-1)?.actor.display_name ?? "";
  const markedBy = dossier.personal_marked_by ?? null;

  const run = async (call: () => Promise<BusinessDossier>, failure: string) => {
    setWorking(true);
    setProblem(null);
    try {
      onChanged(await call());
      reload();
    } catch {
      setProblem(failure);
    } finally {
      setWorking(false);
    }
  };
  const disabled = busy || working;
  const answer = "inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border px-4 text-[14px] font-medium transition-colors disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40";

  return (
    <div className={cardClass} data-testid="receipt-marks-card">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <RecordMarks personal={personal} fiscalValue={fiscalValue} known markedBy={markedBy} />
        {canPrepare ? (
          <button
            type="button"
            data-testid="receipt-mark-personal"
            aria-pressed={personal}
            disabled={disabled}
            onClick={() => void run(() => source.markPersonal(dossier.draft_id, dossier.version, !personal, crypto.randomUUID()), t("business.marks.mark_failed", "We could not save the change. Try again."))}
            className={`inline-flex min-h-11 items-center rounded-full border px-4 text-[13px] font-medium transition-colors disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40 ${personal ? "border-[var(--cuadrao-green)] bg-[var(--cuadrao-green)] text-[var(--cuadrao-cream)]" : "border-black/15 text-black/75 hover:bg-black/[0.04] dark:border-white/20 dark:text-white/80 dark:hover:bg-white/[0.06]"}`}
          >
            {personal ? t("business.marks.unmark_personal_label", "No longer personal") : t("business.marks.mark_personal_label", "Mark as personal")}
          </button>
        ) : null}
      </div>
      {personal && fiscalValue ? (
        <div className="mt-4 border-t border-black/[0.06] pt-4 dark:border-white/[0.08]" data-testid="receipt-606">
          {inclusion === null && !owner && canPrepare ? (
            <>
              <p className="text-[14px] font-medium text-black dark:text-white">{t("business.marks.question_606", "Include in the 606?")}</p>
              <div className="mt-3 flex gap-2">
                <button type="button" data-testid="receipt-606-yes" disabled={disabled} onClick={() => void run(() => source.decideFiscalInclusion(dossier.draft_id, dossier.version, true, crypto.randomUUID()), t("business.marks.decide_failed", "We could not save the answer. Try again."))} className={`${answer} border-[var(--cuadrao-green)] bg-[var(--cuadrao-green)] text-[var(--cuadrao-cream)] hover:opacity-85`}>{t("business.marks.yes", "Yes")}</button>
                <button type="button" data-testid="receipt-606-no" disabled={disabled} onClick={() => void run(() => source.decideFiscalInclusion(dossier.draft_id, dossier.version, false, crypto.randomUUID()), t("business.marks.decide_failed", "We could not save the answer. Try again."))} className={`${answer} border-black/15 text-black/80 hover:bg-black/[0.04] dark:border-white/20 dark:text-white/85 dark:hover:bg-white/[0.06]`}>{t("business.marks.no", "No")}</button>
              </div>
            </>
          ) : (
            <p className="text-[14px] text-black/75 dark:text-white/80" data-testid="receipt-606-state">
              {inclusion === true
                ? (owner ? t("business.marks.included_606", "Included in the 606") : t("business.marks.included_606_by", "Included in the 606 by {{name}}", { name: answeredBy }))
                : inclusion === false
                  ? (owner ? t("business.marks.excluded_606", "Not included in the 606") : t("business.marks.excluded_606_by", "Left out of the 606 by {{name}}", { name: answeredBy }))
                  : t("business.marks.pending_606", "Waiting for the accountant")}
            </p>
          )}
        </div>
      ) : null}
      {problem ? <p role="alert" className="mt-3 text-[13px] text-black/70 dark:text-white/70">{problem}</p> : null}
    </div>
  );
}
