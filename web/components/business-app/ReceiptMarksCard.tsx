"use client";

import { useEffect, useState } from "react";
import { ArrowRightLeft, ReceiptText, UserRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { personName } from "@/lib/person-name";
import type { BusinessDossier } from "@/lib/business-dossier";
import { useBusiness } from "./BusinessWorkspace";
import { primaryButtonClass, quietButtonClass, secondaryButtonClass } from "./business-ui";
import { SURFACE_CARD } from "./foundation/surfaces";
import { dismissToast, showToast } from "./foundation/toasts";
import { MenuCheckItem, useCloseMoreMenu } from "./ReceiptReviewFooter";
import { Switch } from "@/components/ui/Switch";

/**
 * What the record is marked as, and the two decisions that are people's:
 * the owner or anyone holding prepare marks a receipt as personal or takes
 * the mark back (a new revision each way), so the owner can always undo
 * someone else's mark in one tap; a prepare-holder who is not the owner
 * answers whether a personal receipt with a fiscal number goes into the 606,
 * when the server says the caller may. The owner reads that answer; the app never gives it.
 * In Más a third switch says whether the record is a sale, when the server allows that change.
 */
export default function ReceiptMarksCard({ dossier, busy = false, onBusyChange, onChanged, bare = false, retype }: { dossier: BusinessDossier; busy?: boolean; onBusyChange?: (busy: boolean) => void; onChanged: (next: BusinessDossier) => void; /** As rows of the footer's Más menu: a switch per decision, the 606 only under Personal, no chips and no words for an open answer. */ bare?: boolean; /** The Venta switch of Más, for a record whose type the server lets this person change. `confirm` answers whether the change goes ahead. */ retype?: { confirm: () => Promise<boolean> } }) {
  const { t } = useTranslation();
  const { source, chosen, reload } = useBusiness();
  const closeMenu = useCloseMoreMenu();
  const [undoToast, setUndoToast] = useState<number | null>(null);
  useEffect(() => {
    if (busy && undoToast !== null) dismissToast(undoToast);
  }, [busy, undoToast]);
  useEffect(() => () => {
    if (undoToast !== null) dismissToast(undoToast);
  }, [dossier.draft_id, undoToast]);
  const [working, setLocalWorking] = useState(false);
  const setWorking = (value: boolean) => { setLocalWorking(value); onBusyChange?.(value); };
  const [problem, setProblem] = useState<string | null>(null);
  const [retry, setRetry] = useState<(() => void) | null>(null);
  const canPrepare = dossier.capabilities.includes("prepare");
  const owner = !chosen || chosen.role === "owner";
  // The server reads the marks; the card shows them as given.
  const personal = dossier.personal === true;
  const inclusion = dossier.include_606 ?? null;
  const answeredBy = dossier.include_606_by ? personName(t, dossier.include_606_by) : "";

  // A failed change says so here, beside the work, with Reintentar.
  const fail = (text: string, again: () => void) => {
    setProblem(text);
    setRetry(() => again);
  };
  const run = async (call: () => Promise<BusinessDossier>, failure: string) => {
    setWorking(true);
    setProblem(null);
    try {
      onChanged(await call());
      reload();
    } catch {
      fail(failure, () => void run(call, failure));
    } finally {
      setWorking(false);
    }
  };
  const disabled = busy || working;
  // Flips first; a refusal rolls the switch back and says so. A done change offers Deshacer.
  const markPersonal = async (next: boolean) => {
    setProblem(null);
    try {
      const marked = await source.markPersonal(dossier.draft_id, dossier.version, next, crypto.randomUUID());
      onChanged(marked);
      reload();
      setUndoToast(showToast({
        kind: "success",
        text: next ? t("business.marks.marked_personal", "Marked as personal. It does not count in the Business totals.") : t("business.marks.unmarked_personal", "No longer personal. It counts in the totals again."),
        action: { label: t("business.marks.undo", "Undo"), run: () => void run(() => source.markPersonal(dossier.draft_id, marked.version, !next, crypto.randomUUID()), t("business.marks.mark_failed", "We could not save the change. Try again.")) },
      }));
    } catch (error) {
      fail(t("business.marks.mark_failed", "We could not save the change. Try again."), () => void markPersonal(next).catch(() => undefined));
      throw error;
    }
  };
  const problemLine = problem ? (
    <p role="alert" data-testid="receipt-marks-problem" className={`flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-[#9e2f39] dark:text-[#ec9aa0] ${bare ? "px-3 py-2" : "mt-3"}`}>
      {problem}
      {retry ? <button type="button" role={bare ? "menuitem" : undefined} disabled={disabled} onClick={retry} className={quietButtonClass}>{t("common.retry", "Retry")}</button> : null}
    </p>
  ) : null;

  if (bare) {
    // In Más the two decisions are rows; one change at a time, and the 606 answer flips first like Personal.
    const once = (change: (next: boolean) => Promise<void>) => async (next: boolean) => {
      setWorking(true);
      try {
        await change(next);
      } finally {
        setWorking(false);
      }
    };
    const decide606 = async (next: boolean) => {
      setProblem(null);
      try {
        onChanged(await source.decideFiscalInclusion(dossier.draft_id, dossier.version, next, crypto.randomUUID()));
        reload();
      } catch (error) {
        fail(t("business.marks.decide_failed", "We could not save the answer. Try again."), () => void once(decide606)(next).catch(() => undefined));
        throw error;
      }
    };
    const sale = dossier.document_type === "venta";
    // The type changes through the one command that owns it; Deshacer sends the other type on the revision this change left.
    const markSale = async (next: boolean) => {
      setProblem(null);
      if (!retype || !(await retype.confirm())) return;
      const failed = t("business.marks.mark_failed", "We could not save the change. Try again.");
      const type = (on: boolean) => on ? "venta" as const : "recibo" as const;
      try {
        const typed = await source.setDocumentType(dossier.draft_id, dossier.version, type(next), crypto.randomUUID());
        onChanged(typed);
        reload();
        closeMenu();
        setUndoToast(showToast({
          kind: "success",
          text: next ? t("business.marks.marked_sale") : t("business.marks.marked_purchase"),
          action: { label: t("business.marks.undo", "Undo"), run: () => void run(() => source.setDocumentType(dossier.draft_id, typed.version, type(!next), crypto.randomUUID()), failed) },
        }));
      } catch (error) {
        fail(failed, () => void once(markSale)(next).catch(() => undefined));
        throw error;
      }
    };
    return (
      <>
        <MenuCheckItem icon={UserRound} testId="receipt-mark-personal" label={t("business.marks.mark_personal", "Personal")} hint={t("business.marks.personal_help", "It does not count in the Business totals.")} checked={personal} disabled={disabled || !canPrepare} onChange={once(markPersonal)} />
        {personal && dossier.fiscal_question_applies === true ? (
          <MenuCheckItem icon={ReceiptText} testId="receipt-606" label={sale ? t("business.marks.include_607") : t("business.marks.include_606", "Include in the 606")} checked={inclusion === true} disabled={disabled || !canPrepare || !dossier.fiscal_inclusion_available} onChange={once(decide606)} />
        ) : null}
        {retype ? <MenuCheckItem icon={ArrowRightLeft} testId="receipt-mark-sale" label={t("business.marks.mark_sale")} hint={sale ? t("business.marks.sale_help_on") : t("business.marks.sale_help_off")} checked={sale} disabled={disabled} onChange={once(markSale)} /> : null}
        {problemLine}
      </>
    );
  }

  return (
    <div className={SURFACE_CARD} data-testid="receipt-marks-card">
      {canPrepare ? (
        <div className="flex items-center justify-between gap-4 mt-4 border-t border-[#DCE0DA] pt-4 dark:border-white/10">
          <span className="min-w-0">
            <span className="block text-[15px] font-medium text-[#172b26] dark:text-white">{t("business.marks.mark_personal", "Personal")}</span>
            <span className="block text-[13px] text-[#56635e] dark:text-white/70">{t("business.marks.personal_help", "It does not count in the Business totals.")}</span>
          </span>
          <Switch testId="receipt-mark-personal" label={t("business.marks.mark_personal", "Personal")} checked={personal} disabled={disabled} onChange={markPersonal} />
        </div>
      ) : null}
      {dossier.fiscal_question_applies === true ? (
        <div className="mt-4 border-t border-[#DCE0DA] pt-4 dark:border-white/10" data-testid="receipt-606">
          {inclusion === null && dossier.fiscal_inclusion_available ? (
            <>
              <p className="text-[14px] font-medium text-black dark:text-white">{t("business.marks.question_606", "Include in the 606?")}</p>
              <div className="mt-3 flex gap-2">
                <button type="button" data-testid="receipt-606-yes" disabled={disabled} onClick={() => void run(() => source.decideFiscalInclusion(dossier.draft_id, dossier.version, true, crypto.randomUUID()), t("business.marks.decide_failed", "We could not save the answer. Try again."))} className={primaryButtonClass}>{t("business.marks.yes", "Yes")}</button>
                <button type="button" data-testid="receipt-606-no" disabled={disabled} onClick={() => void run(() => source.decideFiscalInclusion(dossier.draft_id, dossier.version, false, crypto.randomUUID()), t("business.marks.decide_failed", "We could not save the answer. Try again."))} className={secondaryButtonClass}>{t("business.marks.no", "No")}</button>
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
      {problemLine}
    </div>
  );
}
