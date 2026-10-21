"use client";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { rncStatus } from "@/lib/rnc-status";
import { ReceiptShortcutRegistration, receiptNavigationActions } from "./BusinessReviewShortcuts";
import ReceiptSeenBoundary from "./ReceiptSeenBoundary";
import type { ReceiptDetail } from "@/lib/business-api";

import { useEffect, useRef, useState } from "react";
import { Check, CircleAlert, Loader2, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { factsRevision, type BusinessDossier, type BusinessFactField, type BusinessFactPatch } from "@/lib/business-dossier";
import ReceiptEcfChecks from "./ReceiptEcfChecks";
import FiscalDeclarationEditor from "./FiscalDeclarationEditor";
import { approveFiscalRecord } from "@/lib/business-dgii";
import { duplicateRecordId, type BusinessCaptureInput } from "@/lib/business-api";
import ManualCaptureDialog from "./ManualCaptureDialog";
import { randomId } from "@/lib/random-id";
import { useBusiness } from "./BusinessWorkspace";
import ReceiptSourcePreview from "./ReceiptSourcePreview";
import ReceiptMessages from "./ReceiptMessages";
import ReceiptRecordFacts from "./ReceiptRecordFacts";
import ReceiptFactEditor from "./ReceiptFactEditor";
import { ACTIVITY_FIELDS, MORE_FIELDS, extractedConfirmationPatch } from "./receipt-fact-rows";
import ReceiptReviewQuestions from "./ReceiptReviewQuestions";
import ReceiptHistory from "./ReceiptHistory";
import ReceiptDocumentType from "./ReceiptDocumentType";
import ReceiptMarksCard from "./ReceiptMarksCard";
import ReceiptReviewFrame from "./ReceiptReviewFrame";
import { formatMoney } from "./business-format";
import { handTitleFocus, nextBandejaReceipt } from "./bandeja-order";
import { primaryButtonClass, secondaryButtonClass, StatusPill } from "./business-ui";
import { SURFACE_CARD } from "./foundation/surfaces";
import { ContentFade, Settle } from "./business-skeletons";
import { resolveLanguage } from "@/lib/language-features";

type Operation = { kind: "idle" } | { kind: "saving" | "approving" } | { kind: "uncertain"; action: "save" | "approve"; version: number };

export function approvalLine(canApprove: boolean, canPrepare: boolean): "prepare_only" | null {
  return !canApprove && canPrepare ? "prepare_only" : null;
}

export function ReceiptApprovalGuidance({ dossier }: { dossier: BusinessDossier }) {
  const { t } = useTranslation();
  if (!dossier.blockers.length || dossier.review_state === "accepted" && dossier.approval_result?.status === "recorded") return null;
  return <div className={`${SURFACE_CARD} text-[13px] text-black/70 dark:text-white/70`}><p className="font-medium">{t("business.dossier.before_approval", "Before approval")}</p><ul className="mt-2 space-y-2">{dossier.blockers.map((blocker, index) => <li key={`${blocker.code}-${index}`}>{t(`business.dossier.blocker.${blocker.code}`, t("business.dossier.blocker_fallback", "This record needs further review before approval."))}{blocker.field ? ` · ${t(`business.dossier.field.${blocker.field}`, blocker.field)}` : ""}</li>)}</ul></div>;
}

/** The purchases a read showed on one receipt, what this record covers of its total, and the settle action once the record is recorded. */
export function ReceiptReadPurchases({ dossier, busy, onSettle }: { dossier: BusinessDossier; busy?: boolean; onSettle?: () => void }) {
  const { t, i18n } = useTranslation();
  const purchases = dossier.read_purchases ?? [];
  if (!purchases.length) return null;
  const unrecorded = dossier.unrecorded_purchases ?? purchases.length;
  const recorded = dossier.review_state === "accepted" && dossier.facts.amount.state === "known";
  const currency = dossier.facts.currency.state === "known" ? dossier.facts.currency.value : null;
  const money = (amount: string) => (currency ? formatMoney(amount, currency, i18n.resolvedLanguage ?? resolveLanguage({})) : amount);
  const note = !recorded
    ? t("business.dossier.read_purchases_note", "The read showed more than one purchase. Complete this record with one of them; the rest stay here as evidence.")
    : unrecorded > 0 && dossier.read_total
      ? t("business.dossier.read_remainder", "Recorded {{recorded}} of a total of {{total}}. {{count}} purchases on this receipt are still unrecorded.", { recorded: money(dossier.facts.amount.state === "known" ? dossier.facts.amount.value : "0"), total: money(dossier.read_total), count: unrecorded })
      : unrecorded > 0
        ? t("business.dossier.read_unrecorded", "{{count}} purchases on this receipt are still unrecorded.", { count: unrecorded })
        : t("business.dossier.read_settled", "The rest of this receipt is settled.");
  return (
    <div className={SURFACE_CARD} data-testid="dossier-read-purchases">
      <h3 className="text-[14px] font-medium text-black dark:text-white">{t("business.dossier.read_purchases_title", "Purchases read on this receipt")}</h3>
      <p className="mb-3 mt-1 text-[13px] text-black/55 dark:text-white/55" data-testid="dossier-read-remainder">{note}</p>
      <ul className="divide-y divide-black/[0.05] dark:divide-white/[0.05]">
        {purchases.map((purchase) => (
          <li key={purchase.index} className="flex items-baseline justify-between gap-3 py-2 text-[14px]">
            <span className="min-w-0 truncate text-black/80 dark:text-white/80">{purchase.merchant ?? t("business.dossier.read_purchase", "Purchase {{index}}", { index: purchase.index })}{purchase.occurred_on ? ` · ${purchase.occurred_on}` : ""}</span>
            <span className="cuadrao-amount shrink-0 tabular-nums text-black dark:text-white">{purchase.amount ? `${purchase.amount}${purchase.currency ? ` ${purchase.currency}` : ""}` : t("business.dossier.unknown_amount", "Amount unknown")}</span>
          </li>
        ))}
      </ul>
      {recorded && unrecorded > 0 && onSettle ? <button type="button" data-testid="dossier-settle-remainder" className={`${secondaryButtonClass} mt-3`} disabled={busy} onClick={onSettle}>{t("business.dossier.settle_remainder", "The rest is already handled")}</button> : null}
    </div>
  );
}

export default function ReceiptDossierReview({ draftId, onUnprepared, receipt }: { draftId: string; onUnprepared?: () => void; receipt?: ReceiptDetail }) {
  const { t, i18n } = useTranslation();
  const { source, reload, records, openPanel } = useBusiness();
  const [dossier, setDossier] = useState<BusinessDossier | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [operation, setOperation] = useState<Operation>({ kind: "idle" });
  const [problem, setProblem] = useState<string | null>(null);
  const [editing, setEditing] = useState<BusinessFactField[]>([]);
  const [edits, setEdits] = useState<BusinessFactPatch>({});
  const [editReset, setEditReset] = useState(0);
  const [invalidFields, setInvalidFields] = useState<BusinessFactField[]>([]);
  const dirty = Object.keys(edits).length > 0;
  const [checking, setChecking] = useState(false);
  const [captureOpen, setCaptureOpen] = useState(false);
  const [captureTarget, setCaptureTarget] = useState<BusinessCaptureInput["draft"]>();
  const [captureRevision, setCaptureRevision] = useState<number>();
  const [captureRetained, setCaptureRetained] = useState(false);
  const [capturePending, setCapturePending] = useState(false);
  const [settling, setSettling] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [fiscalBusy, setFiscalBusy] = useState(false);
  const [fiscalDirty, setFiscalDirty] = useState(false);
  const [duplicate, setDuplicate] = useState<{ recordId: string | null } | null>(null);
  const [rncConfirmation, setRncConfirmation] = useState<{ draftId: string; version: number; next: boolean; status: "missing" | "invalid_length" } | null>(null);
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

  const settle = async () => {
    if (!dossier || settling || inFlight.current) return;
    setSettling(true);
    setProblem(null);
    try {
      setDossier(await source.settleRemainder(draftId, dossier.version, randomId()));
      reload();
    } catch {
      setProblem(t("business.dossier.settle_failed", "The rest could not be marked as handled. Check the current record before trying again."));
    } finally {
      setSettling(false);
    }
  };

  const refresh = async () => {
    setChecking(true);
    try {
      const next = await source.dossier(draftId);
      setDossier(next);
      setUnavailable(false);
      if (operation.kind === "uncertain") {
        const resolved = operation.action === "approve" && (next.approval_result?.status === "recorded" || next.approval_result?.status === "failed");
        if (resolved) { reviewRequest.current = null; setOperation({ kind: "idle" }); setEditing([]); setEdits({}); setInvalidFields([]); setEditReset((value) => value + 1); setProblem(null); }
        else if (operation.action === "save") setProblem(t("business.dossier.save_unconfirmed", "The current revision does not confirm that your save completed. Your edits are retained; saving and approval remain paused."));
      } else { setProblem(null); setDuplicate(null); setEditing([]); setEdits({}); setInvalidFields([]); setEditReset((value) => value + 1); }
    } catch {
      setUnavailable(true);
      setDossier(null);
    } finally { setChecking(false); }
  };

  const write = async (action: "save" | "approve", facts?: BusinessFactPatch): Promise<BusinessDossier | null> => {
    if (!dossier || inFlight.current || fiscalBusy || action === "approve" && fiscalDirty || operation.kind !== "idle" || action === "save" && !facts) return null;
    inFlight.current = true;
    setOperation({ kind: action === "save" ? "saving" : "approving" });
    setProblem(null);
    setDuplicate(null);
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
        const kind = dossier.facts.kind.value;
        next = source.mode === "live" && (kind === "income" || kind === "refund")
          ? await approveFiscalRecord(draftId, dossier.version, kind === "income" ? "record_income" : "record_refund", approvalKey.current.key)
          : await source.approveDraft(draftId, dossier.version, approvalKey.current.key);
      }
      setDossier(next);
      if (action === "save" && facts) {
        const saved = Object.keys(facts);
        setEdits((current) => Object.fromEntries(Object.entries(current).filter(([key]) => !saved.includes(key))) as BusinessFactPatch);
        setEditing((current) => current.filter((key) => !saved.includes(key)));
        setInvalidFields((current) => current.filter((key) => !saved.includes(key)));
      }
      setOperation(next.approval_result?.status === "outcome_unknown" ? { kind: "uncertain", action: "approve", version: dossier.version } : { kind: "idle" });
      reload();
      return next;
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
      } else if (code === "duplicate_comprobante") {
        setOperation({ kind: "idle" });
        setDuplicate({ recordId: duplicateRecordId(error) });
      } else if (status && status >= 400 && status < 500) {
        setOperation({ kind: "idle" });
        setProblem(t(`business.dgii.error.${code}`, t(`business.dossier.blocker.${code}`, t("business.dossier.refused", "This action could not be completed. Check the current record before trying again."))));
      } else {
        setOperation({ kind: "uncertain", action, version: dossier.version });
        setProblem(t("business.dossier.outcome_unknown", "The action's outcome isn't known yet. Check the saved status before taking another action."));
      }
      return null;
    } finally { inFlight.current = false; }
  };

  const pageOpen = useRef(true);
  useEffect(() => {
    pageOpen.current = true;
    return () => { pageOpen.current = false; };
  }, []);

  // Only a recorded approval moves on, to the next row of the Bandeja as the server lists it now,
  // and only while the owner is still on this receipt: leaving it or switching Business unmounts the page.
  const approveAndNext = async () => {
    if (!receipt) return;
    const seen = records.inbox;
    setAdvancing(true);
    try {
      const approved = await write("approve");
      if (approved?.approval_result?.status !== "recorded" || !pageOpen.current) return;
      const fresh = await source.receipts("inbox").catch(() => null);
      if (!pageOpen.current) return;
      const next = fresh ? nextBandejaReceipt(receipt.id, seen, fresh) : null;
      if (next) handTitleFocus(next);
      openPanel(next ? { kind: "receipt", receiptId: next } : { kind: "inbox" });
    } finally {
      setAdvancing(false);
    }
  };

  const captureDialog = <ManualCaptureDialog key="capture" isOpen={captureOpen} target={captureTarget} revision={captureRevision} onClose={() => setCaptureOpen(false)} onPending={setCapturePending} onRetained={setCaptureRetained} onUnavailable={() => { setUnavailable(true); setDossier(null); }} onSaved={(saved) => { setDossier(saved); setCaptureOpen(false); setUnavailable(false); reload(); }} />;
  const captureRecovery = captureRetained && !captureOpen ? <button type="button" className={`${secondaryButtonClass} mb-4`} onClick={() => setCaptureOpen(true)}>{capturePending ? t("business.capture.reopen", "Reopen unconfirmed note") : t("business.capture.reopen_retained", "Reopen retained note")}</button> : null;
  if (unavailable || !dossier && problem) return (<>
    {captureRecovery}
    <section className={SURFACE_CARD} data-testid="receipt-load-error">
      <p role="alert" className="flex items-start gap-2 text-[15px] leading-[22px] text-[#9e2f39] dark:text-[#ec9aa0]"><CircleAlert className="mt-0.5 h-[18px] w-[18px] shrink-0" aria-hidden="true" />{problem ?? t("business.dossier.unavailable", "This record isn't available with your current access.")}</p>
      <button type="button" disabled={checking} onClick={() => void refresh()} className={`${secondaryButtonClass} mt-4`}>{t("common.retry", "Retry")}</button>
    </section>{captureDialog}</>
  );
  if (!dossier) return <>{captureRecovery}<Settle pending layout="detail" />{captureDialog}</>;

  const accounts = dossier.accounts;
  const amount = dossier.facts.amount.state === "known" ? dossier.facts.amount.value : null;
  const currency = dossier.facts.currency.state === "known" ? dossier.facts.currency.value : null;
  const approval = dossier.approval_result?.status === "recorded" ? dossier.approval_result : null;
  const recorded = approval !== null;
  const supportedKind = dossier.facts.kind.state === "known" && ["expense", "income", "refund"].includes(dossier.facts.kind.value);
  const mutable = !capturePending && !captureOpen && !fiscalBusy && !fiscalDirty && dossier.review_state === "open" && !recorded && operation.kind === "idle" && dossier.approval_result?.status !== "outcome_unknown";
  const canPrepare = dossier.capabilities.includes("prepare");
  const canApprove = dossier.capabilities.includes("approve");
  const line = approvalLine(canApprove, canPrepare);
  const title = dossier.facts.counterparty.state === "known" ? dossier.facts.counterparty.value : t("business.dossier.title", "Review record");
  const attachments = dossier.sources.filter((item) => item.kind === "attachment");
  const busy = operation.kind === "saving" || operation.kind === "approving";
  const approvable = mutable && dossier.approval_available && !dirty && !fiscalDirty;
  const missingFields = [...new Set(dossier.blockers.flatMap((blocker) => blocker.code === "fact_required" && blocker.field ? [blocker.field] : []))];
  const confirmations = extractedConfirmationPatch(dossier, edits);
  const confirmationCount = Object.keys(confirmations).length;

  const requestApproval = (next = false) => {
    if (!canApprove || !supportedKind || !approvable) return;
    const status = rncStatus(dossier.facts.fiscal?.rnc);
    const showsFiscal = Boolean(dossier.facts.fiscal) || dossier.fiscal_known === true && !dossier.fiscal_value;
    if (showsFiscal && status !== "unverified") {
      setRncConfirmation({ draftId: dossier.draft_id, version: dossier.version, next, status });
    } else if (next) void approveAndNext();
    else void write("approve");
  };
  const reason = busy || supportedKind && approvable ? null
    : dirty ? t("business.dossier.edit_note", "Saving updates the review details. Approval is a separate action.")
    : dossier.facts.occurred_on.state !== "known" && dossier.blockers.some((blocker) => blocker.field === "occurred_on") ? t("business.dossier.approve_reason.date", "Add the date to approve")
    : missingFields.length ? t("business.dossier.missing_list", "Missing: {{fields}}", { fields: missingFields.map((field) => t(`business.dossier.field.${field}`, field)).join(", ") })
    : dossier.blockers.length ? t(`business.dossier.blocker.${dossier.blockers[0].code}`, t("business.dossier.blocker_fallback", "This record needs further review before approval."))
    : t("business.dossier.blocker_fallback", "This record needs further review before approval.");
  // The receipt's own status when there is one; a bare record maps only the review states a status pill can say.
  const pillStatus = receipt?.status ?? (recorded || dossier.review_state === "accepted" ? "confirmed" : dossier.review_state === "open" ? "review_ready" : null);
  const reasonId = `approve-reason-${dossier.draft_id}`;
  const approvalLabel = dossier.facts.kind.value === "income" ? t("business.dgii.approve_income", "Aprobar ingreso") : dossier.facts.kind.value === "refund" ? t("business.dgii.approve_refund", "Aprobar reembolso") : t("business.dossier.approve_action", "Approve expense");

  const canMove = mutable && !dirty && !editing.length && !advancing && !settling;
  return (<><ContentFade><>
    <ReceiptShortcutRegistration actions={{
      ...(canApprove && supportedKind && approvable ? { approve: () => requestApproval(), ...(receipt ? { approve_next: () => requestApproval(true) } : {}) } : {}),
      ...(canMove && receipt ? receiptNavigationActions(receipt.id, records.inbox, (id) => { handTitleFocus(id); openPanel({ kind: "receipt", receiptId: id }); }) : {}),
      ...(canPrepare && mutable ? { edit: () => {
        const focused = document.activeElement?.closest<HTMLElement>("[data-fact]")?.dataset.fact;
        const order = [...ACTIVITY_FIELDS, ...MORE_FIELDS];
        const field = order.find((key) => key === focused) ?? order[0];
        if (!field) return;
        const control = document.querySelector<HTMLInputElement | HTMLSelectElement>(`[data-testid="edit-${field}"] input, [data-testid="edit-${field}"] select`);
        if (control) control.focus();
        else setEditing((current) => current.includes(field) ? current : [...current, field]);
      } } : {}),
    }} />
    {captureRecovery}
    <ReceiptReviewFrame
      recordId={receipt?.id ?? draftId}
      back={recorded ? "transactions" : "inbox"}
      title={title}
      history={<ReceiptHistory history={dossier.history} accounts={accounts} sources={dossier.sources} approval={dossier.approval_result} />}
      badge={pillStatus ? <StatusPill status={pillStatus} /> : <span className="text-[13px] leading-[18px] text-[#56635e] dark:text-white/70">{t(`business.dossier.state.${dossier.review_state}`, dossier.review_state)}</span>}
      amount={amount !== null && currency !== null ? formatMoney(amount, currency, i18n.resolvedLanguage ?? resolveLanguage({})) : null}
      mark={dossier.bill_mark}
      footer={!approval && canApprove ? <div className="flex flex-wrap items-center gap-3">
        <button type="button" aria-busy={operation.kind === "approving" && !advancing} className={`${primaryButtonClass} w-full whitespace-nowrap tablet:w-auto`} aria-describedby={reason ? reasonId : undefined} disabled={!supportedKind || !approvable} onClick={() => requestApproval()}>{operation.kind === "approving" && !advancing ? <><Loader2 className="h-[18px] w-[18px] animate-spin motion-reduce:animate-none" aria-hidden="true" />{t("business.dossier.approving", "Approving…")}</> : approvalLabel}</button>
        {receipt ? <button type="button" aria-busy={operation.kind === "approving" && advancing} className={`${secondaryButtonClass} w-full whitespace-nowrap tablet:w-auto`} aria-describedby={reason ? reasonId : undefined} disabled={!supportedKind || !approvable} onClick={() => requestApproval(true)}>{operation.kind === "approving" && advancing ? <><Loader2 className="h-[18px] w-[18px] animate-spin motion-reduce:animate-none" aria-hidden="true" />{t("business.dossier.approving", "Approving…")}</> : t("business.dossier.approve_next", "Approve and next")}</button> : null}
        {reason ? <p id={reasonId} data-testid="approve-reason" className="w-full text-[13px] leading-[18px] text-[#56635e] tablet:w-auto tablet:flex-1 dark:text-white/70">{reason}</p> : null}
      </div> : undefined}
      source={<>
          {attachments.map((attachment) => <ReceiptSourcePreview key={attachment.id} detail={{ id: attachment.connection_id, filename: attachment.filename, media_type: attachment.media_type, received_at: attachment.received_at, channel: attachment.channel, email_delivery_ids: attachment.email_delivery_ids }} />)}
          <ReceiptMessages sources={dossier.sources} />
          {!attachments.length ? <div className={`${SURFACE_CARD} text-[14px] text-black/65 dark:text-white/65`}>{dossier.facts.receipt_state.state === "known" && dossier.facts.receipt_state.value === "no_receipt" ? t("business.dossier.no_receipt", "No receipt was supplied.") : t("business.dossier.no_attachment", "No receipt file is attached to this record.")}</div> : null}
          <ReceiptReadPurchases dossier={dossier} busy={settling || busy} onSettle={canApprove ? settle : undefined} />
          <ReceiptEcfChecks verification={dossier.ecf_checks ?? null} qr={dossier.dgii_qr ?? null} />
      </>}
    >
          <ReceiptDocumentType dossier={dossier} busy={busy || dirty} onChanged={setDossier} />
          <div>
            {operation.kind === "uncertain" && operation.action === "save" ? <h3 className="mb-4 font-display text-[18px] font-medium leading-6 text-[#172b26] dark:text-white">{t("business.dossier.pending_details", "Your unconfirmed edits")}</h3> : null}
            {canPrepare && confirmationCount > 0 ? <button type="button" className={`${secondaryButtonClass} mb-4`} disabled={!mutable} onClick={() => void write("save", confirmations)}>{t("business.dossier.confirm_read", { count: confirmationCount, defaultValue: "Confirm {{count}}" })}</button> : null}
            <ReceiptRecordFacts dossier={dossier} accounts={accounts} onEdit={canPrepare && mutable ? (key) => setEditing((current) => current.includes(key) ? current : [...current, key]) : undefined} editor={canPrepare ? (key) => editing.includes(key) || key === "occurred_on" && dossier.facts.occurred_on.state === "unknown" ? <ReceiptFactEditor key={`${key}-${editReset}`} field={key} autoFocus={editing.includes(key)} facts={dossier.facts} patch={edits} accounts={accounts} currencies={[...new Set([...accounts.map((account) => account.currency), ...(currency ? [currency] : [])])]} disabled={!mutable} onChange={(patch, invalid) => {
              setEdits((current) => ({ ...current, ...patch }));
              setInvalidFields((current) => invalid ? [...new Set([...current, key])] : current.filter((field) => field !== key));
            }} /> : null : undefined} />
            {dirty ? <div className="mt-4 space-y-3"><p className="text-[12px] text-black/60 dark:text-white/65">{t("business.dossier.edit_note", "Saving updates the review details. Approval is a separate action.")}</p><div className="flex flex-wrap gap-2"><button type="button" className={secondaryButtonClass} disabled={!mutable || invalidFields.length > 0} onClick={() => void write("save", edits)}>{t("business.dossier.save", "Save review details")}</button><button type="button" className={secondaryButtonClass} disabled={!mutable} onClick={() => { setEditing([]); setEdits({}); setInvalidFields([]); setEditReset((value) => value + 1); }}>{t("common.cancel", "Cancel")}</button></div></div> : null}
          </div>
          {operation.kind === "uncertain" && operation.action === "save" ? <div><h3 className="mb-4 font-display text-[18px] font-medium leading-6 text-[#172b26] dark:text-white">{t("business.dossier.saved_details", "Current saved details")}</h3><ReceiptRecordFacts dossier={dossier} accounts={accounts} /></div> : null}
          {canPrepare && mutable && !editing.length && !dirty ? <button type="button" className={secondaryButtonClass} onClick={() => { setCaptureTarget({ draft_id: dossier.draft_id, version: dossier.version }); setCaptureRevision(factsRevision(dossier)); setCaptureOpen(true); }}>{t("business.capture.append", "Add a note to this record")}</button> : null}
          <ReceiptMarksCard dossier={dossier} busy={busy || fiscalBusy || fiscalDirty} onChanged={setDossier} />
          {source.mode === "live" ? <FiscalDeclarationEditor key={`${dossier.draft_id}-${dossier.version}`} dossier={dossier} disabled={busy || dirty || capturePending || captureOpen} onBusy={setFiscalBusy} onDirty={setFiscalDirty} onChanged={(value) => { setDossier(value); reload(); }} /> : null}
          <ReceiptReviewQuestions questions={dossier.questions} />
          <ReceiptApprovalGuidance dossier={dossier} />
          {problem ? <p role="alert" className="flex items-start gap-2 text-[15px] leading-[22px] text-[#9e2f39] dark:text-[#ec9aa0]"><CircleAlert className="mt-0.5 h-[18px] w-[18px] shrink-0" aria-hidden="true" />{problem}</p> : null}
          {duplicate ? <div role="alert" data-testid="dossier-duplicate" className={SURFACE_CARD}><p className="text-[15px] leading-[22px] text-[#172b26] dark:text-white">{t("business.dossier.duplicate_recorded", "You already recorded this fiscal receipt.")}</p>{duplicate.recordId ? <button type="button" className={`${secondaryButtonClass} mt-3`} onClick={() => openPanel({ kind: "draft", draftId: duplicate.recordId as string })}>{t("business.dossier.see_recorded", "See the recorded one")}</button> : null}</div> : null}
          <div className={SURFACE_CARD}>
            {approval ? <><div role="status"><p className="flex gap-2 text-[14px] text-black/80 dark:text-white/80"><Check className="h-4 w-4 shrink-0" aria-hidden="true" />{(dossier.facts.kind.value === "income" ? t("business.dgii.recorded_income", "Se registró un ingreso después de aprobar la revisión {{version}}.", { version: approval.approved_revision }) : dossier.facts.kind.value === "refund" ? t("business.dgii.recorded_refund", "Se registró un reembolso después de aprobar la revisión {{version}}.", { version: approval.approved_revision }) : t("business.dossier.recorded", "One expense was recorded after approval of revision {{version}}.", { version: approval.approved_revision }))}</p><p className="mt-1 pl-6 text-[13px] text-black/65 dark:text-white/65">{t("business.expenses.recorded_on", "Recorded on {{when}}", { when: new Intl.DateTimeFormat(i18n.resolvedLanguage ?? resolveLanguage({}), { day: "numeric", month: "short", year: "numeric" }).format(new Date(approval.approved_at)) })}</p></div><p className="mt-3 text-[12px] text-black/55 dark:text-white/55">{t("business.dossier.approved_by", "Approved by {{name}} · permission granted by {{issuer}}", { name: approval.actor.display_name, issuer: approval.actor.issuer_display_name })}</p><p className="mt-3 text-[12px] text-black/55 dark:text-white/55">{t("business.dossier.correction_unsupported", "Corrections after recording aren't available in this first flow.")}</p></> : <>
              {line ? <p className="text-[13px] leading-relaxed text-black/65 dark:text-white/65">{t("business.dossier.prepare_only", "Your permission allows preparing this record. A person with approval permission must approve it.")}</p> : null}
              {dossier.approval_result?.status === "failed" ? <p role="alert" className="mt-3 text-[13px] text-black/70 dark:text-white/70">{t("business.dossier.approval_failed", "Approval did not finish. Check the current record before another action.")}</p> : null}
            </>}
            {operation.kind === "uncertain" || dossier.approval_result?.status === "outcome_unknown" || dossier.review_state === "accepting" ? <p role="status" className="mt-3 text-[13px] text-black/70 dark:text-white/70">{t("business.dossier.outcome_unknown", "The action's outcome isn't known yet. Check the saved status before taking another action.")}</p> : null}
            <button type="button" disabled={busy || checking} onClick={() => void refresh()} className={`${secondaryButtonClass} mt-4`}><RotateCcw className="h-4 w-4" aria-hidden="true" />{t("business.dossier.refresh", "Check current record")}</button>
          </div>
    </ReceiptReviewFrame>
    {rncConfirmation ? <ConfirmDialog
      isOpen
      title={t(`business.dgii.rnc_check.${rncConfirmation.status}.approval_title`)}
      description={t(`business.dgii.rnc_check.${rncConfirmation.status}.approval_body`)}
      confirmLabel={rncConfirmation.next ? t("business.dossier.approve_next", "Approve and next") : approvalLabel}
      cancelLabel={t("common.cancel", "Cancel")}
      isBusy={busy}
      onCancel={() => setRncConfirmation(null)}
      onConfirm={() => {
        setRncConfirmation(null);
        if (!canApprove || !supportedKind || !approvable || rncConfirmation.draftId !== dossier.draft_id || rncConfirmation.version !== dossier.version) return;
        if (rncConfirmation.next) void approveAndNext();
        else void write("approve");
      }}
    /> : null}
    {receipt ? <ReceiptSeenBoundary receipt={receipt} hydrated={dossier.draft_id === receipt.draft_id && dossier.version === receipt.version} /> : null}
  </></ContentFade>
    {/* Every branch returns a fragment holding the keyed note dialog, so a denied save that hides the record keeps the typed text. */}
    {captureDialog}
  </>
  );
}
