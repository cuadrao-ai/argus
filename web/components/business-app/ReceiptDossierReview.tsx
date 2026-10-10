"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Check, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { BusinessDossier, BusinessFactPatch } from "@/lib/business-dossier";
import { randomId } from "@/lib/random-id";
import { useBusiness } from "./BusinessWorkspace";
import ReceiptSourcePreview from "./ReceiptSourcePreview";
import ReceiptMessages from "./ReceiptMessages";
import ReceiptRecordFacts from "./ReceiptRecordFacts";
import ReceiptFactEditor from "./ReceiptFactEditor";
import ReceiptReviewQuestions from "./ReceiptReviewQuestions";
import ReceiptHistory from "./ReceiptHistory";
import { formatMoney } from "./business-format";
import { cardClass, LoadingRows, primaryButtonClass, secondaryButtonClass } from "./business-ui";

type Operation = { kind: "idle" } | { kind: "saving" | "approving" } | { kind: "uncertain"; action: "save" | "approve"; version: number };

export default function ReceiptDossierReview({ draftId, onUnprepared }: { draftId: string; onUnprepared?: () => void }) {
  const { t, i18n } = useTranslation();
  const { source, openPanel, reload } = useBusiness();
  const [dossier, setDossier] = useState<BusinessDossier | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [operation, setOperation] = useState<Operation>({ kind: "idle" });
  const [problem, setProblem] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [checking, setChecking] = useState(false);
  const inFlight = useRef(false);
  const reviewRequest = useRef<{ version: number; facts: BusinessFactPatch; key: string } | null>(null);
  const approvalKey = useRef<{ version: number; key: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    source.dossier(draftId).then((next) => { if (!cancelled) setDossier(next); }).catch((error: unknown) => {
      if (cancelled) return;
      if ((error as { code?: string }).code === "draft_not_prepared") {
        if (onUnprepared) onUnprepared();
        else setProblem(t("business.dossier.missing_draft", "The prepared record isn't available yet. Check the current receipt before continuing."));
      } else setUnavailable(true);
    });
    return () => { cancelled = true; };
  }, [draftId, onUnprepared, source, t]);

  const refresh = async () => {
    setChecking(true);
    try {
      const next = await source.dossier(draftId);
      setDossier(next);
      setUnavailable(false);
      if (operation.kind === "uncertain") {
        const resolved = operation.action === "approve" && (next.approval_result?.status === "recorded" || next.approval_result?.status === "failed");
        if (resolved) { reviewRequest.current = null; setOperation({ kind: "idle" }); setEditing(false); setDirty(false); setProblem(null); }
        else if (operation.action === "save") setProblem(t("business.dossier.save_unconfirmed", "The current revision does not confirm that your save completed. Your edits are retained; saving and approval remain paused."));
      } else { setProblem(null); setEditing(false); setDirty(false); }
    } catch {
      setUnavailable(true);
      setDossier(null);
    } finally { setChecking(false); }
  };

  const write = async (action: "save" | "approve", facts?: BusinessFactPatch) => {
    if (!dossier || inFlight.current || operation.kind !== "idle" || action === "save" && !facts) return;
    inFlight.current = true;
    setOperation({ kind: action === "save" ? "saving" : "approving" });
    setProblem(null);
    try {
      let next: BusinessDossier;
      if (action === "save" && facts) {
        reviewRequest.current = { version: dossier.version, facts, key: randomId() };
        const request = reviewRequest.current;
        next = await source.reviewDraft(draftId, request.version, request.facts, request.key);
        reviewRequest.current = null;
      }
      else {
        if (approvalKey.current?.version !== dossier.version) approvalKey.current = { version: dossier.version, key: randomId() };
        next = await source.approveDraft(draftId, dossier.version, approvalKey.current.key);
      }
      setDossier(next);
      setEditing(false);
      setDirty(false);
      setOperation(next.approval_result?.status === "outcome_unknown" ? { kind: "uncertain", action: "approve", version: dossier.version } : { kind: "idle" });
      reload();
    } catch (error) {
      const { code, status } = error as { code?: string; status?: number };
      if (status && status >= 400 && status < 500) reviewRequest.current = null;
      if (code === "stale_version") {
        setOperation({ kind: "idle" });
        setProblem(t("business.dossier.stale", "This record changed. Open the current revision and review it before taking another action."));
        setDossier(null);
      } else if (status === 401 || status === 403 || status === 404 || code === "permission_denied") {
        setOperation({ kind: "idle" });
        setDossier(null);
        setUnavailable(true);
      } else if (status && status >= 400 && status < 500) {
        setOperation({ kind: "idle" });
        setProblem(t(`business.dossier.blocker.${code}`, t("business.dossier.refused", "This action could not be completed. Check the current record before trying again.")));
      } else {
        setOperation({ kind: "uncertain", action, version: dossier.version });
        setProblem(t("business.dossier.outcome_unknown", "The action's outcome isn't known yet. Check the saved status before taking another action."));
      }
    } finally { inFlight.current = false; }
  };

  if (unavailable || !dossier && problem) return (
    <section className={cardClass}>
      <p role="alert" className="text-[14px] text-black/75 dark:text-white/75">{problem ?? t("business.dossier.unavailable", "This record isn't available with your current access.")}</p>
      <button type="button" disabled={checking} onClick={() => void refresh()} className={`${secondaryButtonClass} mt-4`}><RotateCcw className="h-4 w-4" aria-hidden="true" />{t("business.dossier.refresh", "Check current record")}</button>
    </section>
  );
  if (!dossier) return <LoadingRows rows={4} />;

  const accounts = dossier.accounts;
  const amount = dossier.facts.amount.state === "known" ? dossier.facts.amount.value : null;
  const currency = dossier.facts.currency.state === "known" ? dossier.facts.currency.value : null;
  const recorded = dossier.approval_result?.status === "recorded";
  const expense = dossier.facts.kind.state === "known" && dossier.facts.kind.value === "expense";
  const mutable = dossier.review_state === "open" && !recorded && operation.kind === "idle" && dossier.approval_result?.status !== "outcome_unknown";
  const canPrepare = dossier.capabilities.includes("prepare");
  const canApprove = dossier.capabilities.includes("approve");
  const title = dossier.facts.counterparty.state === "known" ? dossier.facts.counterparty.value : t("business.dossier.title", "Review record");
  const attachments = dossier.sources.filter((item) => item.kind === "attachment");
  const busy = operation.kind === "saving" || operation.kind === "approving";

  return (
    <section aria-labelledby="receipt-review-title" data-testid="business-record-review">
      <button type="button" onClick={() => openPanel({ kind: recorded ? "expenses" : "inbox" })} className="mb-4 flex min-h-11 items-center gap-1.5 rounded-full pr-3 text-[14px] text-black/65 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20 dark:text-white/65"><ArrowLeft className="h-4 w-4" aria-hidden="true" />{recorded ? t("business.nav.expenses", "Expenses") : t("business.nav.inbox", "Inbox")}</button>
      <header className="mb-5">
        <p className="mb-2 text-[13px] text-black/55 dark:text-white/55">{dossier.space_name}</p>
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="receipt-review-title" className="min-w-0 break-words font-display text-[25px] font-medium tracking-tight text-black dark:text-white">{title}</h2><span className="rounded-full bg-black/5 px-3 py-1.5 text-[12px] text-black/70 dark:bg-white/10 dark:text-white/70">{t(`business.dossier.state.${dossier.review_state}`, dossier.review_state)}</span></div>
        <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1"><p className="font-display text-[23px] font-medium tabular-nums text-black dark:text-white">{amount === null ? t("business.dossier.amount_unknown", "Amount unknown") : currency === null ? `${amount} · ${t("business.dossier.currency_unknown", "Currency unknown")}` : formatMoney(amount, currency, i18n.resolvedLanguage ?? "en")}</p><span className="text-[12px] text-black/50 dark:text-white/50">{t("business.dossier.revision", "Revision {{version}}", { version: dossier.version })}</span></div>
      </header>
      <div className="grid items-start gap-4 desktop:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          {attachments.map((attachment) => <ReceiptSourcePreview key={attachment.id} detail={{ id: attachment.connection_id, filename: attachment.filename, media_type: attachment.media_type, received_at: attachment.received_at, channel: attachment.channel }} />)}
          <ReceiptMessages sources={dossier.sources} />
          {!attachments.length ? <div className={`${cardClass} text-[14px] text-black/65 dark:text-white/65`}>{dossier.facts.receipt_state.state === "known" && dossier.facts.receipt_state.value === "no_receipt" ? t("business.dossier.no_receipt", "No receipt was supplied.") : t("business.dossier.no_attachment", "No receipt file is attached to this record.")}</div> : null}
          <ReceiptHistory history={dossier.history} accounts={accounts} />
        </div>
        <div className="space-y-4">
          <div className={cardClass}>
            <div className="mb-5 flex items-center justify-between gap-3"><h3 className="text-[14px] font-medium text-black dark:text-white">{(operation.kind === "uncertain" && operation.action === "save" ? t("business.dossier.pending_details", "Your unconfirmed edits") : t("business.dossier.current_details", "Current details"))}</h3>{canPrepare && mutable && !editing ? <button type="button" onClick={() => setEditing(true)} className="min-h-11 rounded-full px-2 text-[13px] font-medium text-black/65 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20 dark:text-white/65">{t("business.dossier.edit", "Edit details")}</button> : null}</div>
            {editing && canPrepare ? <ReceiptFactEditor key={operation.kind === "uncertain" && operation.action === "save" ? operation.version : dossier.version} facts={dossier.facts} accounts={accounts} currencies={[...new Set([...accounts.map((account) => account.currency), ...(currency ? [currency] : [])])]} disabled={!mutable} onChange={setDirty} onSave={(facts) => void write("save", facts)} onCancel={() => { setEditing(false); setDirty(false); }} /> : <ReceiptRecordFacts dossier={dossier} accounts={accounts} />}
          </div>
          {editing && operation.kind === "uncertain" && operation.action === "save" ? <div className={cardClass}><h3 className="mb-5 text-[14px] font-medium text-black dark:text-white">{t("business.dossier.saved_details", "Current saved details")}</h3><ReceiptRecordFacts dossier={dossier} accounts={accounts} /></div> : null}
          <ReceiptReviewQuestions questions={dossier.questions} />
          {dossier.blockers.length ? <div className={`${cardClass} text-[13px] text-black/70 dark:text-white/70`}><p className="font-medium">{t("business.dossier.before_approval", "Before approval")}</p><ul className="mt-2 space-y-2">{dossier.blockers.map((blocker, index) => <li key={`${blocker.code}-${index}`}>{t(`business.dossier.blocker.${blocker.code}`, t("business.dossier.blocker_fallback", "This record needs further review before approval."))}{blocker.field ? ` · ${t(`business.dossier.field.${blocker.field}`, blocker.field)}` : ""}</li>)}</ul></div> : null}
          {problem ? <p role="alert" className="text-[14px] text-[#a8434c] dark:text-[#ec9aa0]">{problem}</p> : null}
          <div className={cardClass}>
            {recorded ? <><p role="status" className="flex gap-2 text-[14px] text-black/80 dark:text-white/80"><Check className="h-4 w-4 shrink-0" aria-hidden="true" />{t("business.dossier.recorded", "One expense was recorded after approval of revision {{version}}.", { version: dossier.approval_result?.reviewed_version })}</p><p className="mt-3 text-[12px] text-black/55 dark:text-white/55">{dossier.approval_result?.status === "recorded" ? t("business.dossier.approved_by", "Approved by {{name}} · permission granted by {{issuer}}", { name: dossier.approval_result.actor.display_name, issuer: dossier.approval_result.actor.issuer_display_name }) : null}</p><p className="mt-3 text-[12px] text-black/55 dark:text-white/55">{t("business.dossier.correction_unsupported", "Corrections after recording aren't available in this first flow.")}</p></> : <>
              {canApprove && expense ? <button type="button" className={primaryButtonClass} disabled={!mutable || !dossier.approval_available || dirty || editing || !expense} onClick={() => void write("approve")}>{operation.kind === "approving" ? t("business.dossier.approving", "Approving…") : t("business.dossier.approve", "Approve expense")}</button> : null}
              <p className={`${canApprove ? "mt-3 " : ""}text-[13px] leading-relaxed text-black/65 dark:text-white/65`}>{canApprove && expense ? t("business.dossier.approval_effect", "Approval records this revision as one expense. Saving review details does not record it.") : canPrepare ? t("business.dossier.prepare_only", "Your permission allows preparing this record. A person with approval permission must approve it.") : t("business.dossier.read_only", "Your permission allows viewing this record.")}</p>
              {dossier.approval_result?.status === "failed" ? <p role="alert" className="mt-3 text-[13px] text-black/70 dark:text-white/70">{t("business.dossier.approval_failed", "Approval did not finish. Check the current record before another action.")}</p> : null}
            </>}
            {operation.kind === "uncertain" || dossier.approval_result?.status === "outcome_unknown" || dossier.review_state === "accepting" ? <p role="status" className="mt-3 text-[13px] text-black/70 dark:text-white/70">{t("business.dossier.outcome_unknown", "The action's outcome isn't known yet. Check the saved status before taking another action.")}</p> : null}
            <button type="button" disabled={busy || checking} onClick={() => void refresh()} className={`${secondaryButtonClass} mt-4`}><RotateCcw className="h-4 w-4" aria-hidden="true" />{checking ? t("common.loading", "Loading") : t("business.dossier.refresh", "Check current record")}</button>
          </div>
        </div>
      </div>
    </section>
  );
}
