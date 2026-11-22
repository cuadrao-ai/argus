"use client";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { recordGone, referenceCode, refusedForGood } from "@/lib/failure-screen";
import { sentByName } from "@/lib/sent-by";
import { ReceiptShortcutRegistration, receiptNavigationActions, receiptPlace } from "./BusinessReviewShortcuts";
import ReceiptSeenBoundary from "./ReceiptSeenBoundary";
import type { ReceiptDetail } from "@/lib/business-api";

import { useEffect, useEffectEvent, useRef, useState, type ReactNode } from "react";
import { CircleAlert, Loader2, RotateCcw, StickyNote } from "lucide-react";
import { useTranslation } from "react-i18next";
import { factsRevision, readReviewNote, type BusinessDossier, type ReviewFlagCode, type ShownSuggestions } from "@/lib/business-dossier";
import { documentFamily } from "@/lib/counterparty-term";
import type { DgiiFields } from "@/lib/business-dgii";
import FiscalDeclarationEditor from "./FiscalDeclarationEditor";
import DossierConfirm, { type ConfirmProblem } from "./dossier/DossierConfirm";
import DossierDetails from "./dossier/DossierDetails";
import DossierDocument from "./dossier/DossierDocument";
import { DossierStatus } from "./dossier/DossierHeader";
import { DossierBare, type RowEdit } from "./dossier/DossierParts";
import { useJumpRows } from "./dossier/jump-rows";
import { businessTypedNotesAvailable, confirmationFlags, duplicateRecordId, type BusinessCaptureInput } from "@/lib/business-api";
import ManualCaptureDialog from "./ManualCaptureDialog";
import { randomId } from "@/lib/random-id";
import { useBusiness } from "./BusinessWorkspace";
import ReceiptSourcePreview from "./ReceiptSourcePreview";
import { ReceiptDuplicateCompare, useDuplicateCompare } from "./ReceiptDuplicateCompare";
import ReceiptMessages from "./ReceiptMessages";
import ReceiptRecordFacts, { type RowFlash } from "./ReceiptRecordFacts";
import { useAmountsPreview } from "./useAmountsPreview";
import ReceiptFactEditor from "./ReceiptFactEditor";
import ReceiptOwnerChoices, { shownSuggestions, type ChoicesView } from "./ReceiptOwnerChoices";
import ReceiptRowSave from "./ReceiptRowSave";
import ReceiptReviewDone from "./ReceiptReviewDone";
import { READ_FACT_ROWS, type ReviewRow } from "./receipt-fact-rows";
import { changesRecord, useReviewAutosave, useReviewRows, type SaveRow } from "./receipt-review-save";
import { FLAGGED_ROW, dossierProblems, dossierRowLabel, type DossierProblem, type DossierTab } from "./dossier-attention";
import ReceiptReviewQuestions from "./ReceiptReviewQuestions";
import ReceiptHistory from "./ReceiptHistory";
import ReceiptDocumentType from "./ReceiptDocumentType";
import ReceiptMarksCard from "./ReceiptMarksCard";
import ReceiptReviewFrame from "./ReceiptReviewFrame";
import { DeleteDocumentMenuItem, RestoreDocumentButton, useDocumentDelete } from "./DocumentDeleteControls";
import ReceiptReviewFooter, { KEY_HINT_CLASS, MenuItem, ReceiptMoreMenu, usePrimaryKeys } from "./ReceiptReviewFooter";
import { formatMoney, UNKNOWN_VALUE } from "./business-format";
import { recordsCurrencySchema } from "@/lib/business-reports-api";
import { bandejaReceipts, handTitleFocus, nextBandejaReceipt } from "./bandeja-order";
import { primaryButtonClass, secondaryButtonClass } from "./business-ui";
import { SURFACE_CARD } from "./foundation/surfaces";
import { showToast } from "./foundation/toasts";
import { useShownRecord } from "./useShownRecord";
import { ContentFade, Settle } from "./business-skeletons";
import { resolveLanguage } from "@/lib/language-features";
import { OpenRecordMissingReasons } from "./transacciones/RecordMissingReason";

/** The values a form row offers the original message to mark: its own data-match list. */
function rowValues(target: EventTarget): string[] {
  const match = target instanceof Element ? target.closest<HTMLElement>("[data-match]")?.dataset.match : undefined;
  return match ? JSON.parse(match) as string[] : [];
}

type Operation = { kind: "idle" | "approving" } | { kind: "uncertain"; version: number };
type Problem = { text: string; reference?: string };
type ApprovalRequest = { next: boolean; anyway: boolean };
/** One approve request: the suggestions it carries are the ones on screen when the person approved. */
type ApprovalSend = ApprovalRequest & { suggestions?: ShownSuggestions };
/** The step shown before accepting one revision that is not Listos: every reason the server gives, or the flags an approve request was refused for. */
type ApprovalCheck = { draftId: string; version: number; next: boolean } & ({ kind: "problems" } | { kind: "flags"; codes: ReviewFlagCode[] });

export function approvalLine(canApprove: boolean, canPrepare: boolean): "prepare_only" | null {
  return !canApprove && canPrepare ? "prepare_only" : null;
}

/** The purchases a read showed on one receipt, what this record covers of its total, and the settle action once the record is recorded. */
export function ReceiptReadPurchases({ dossier, busy, onSettle }: { dossier: BusinessDossier; busy?: boolean; onSettle?: () => void }) {
  const { t, i18n } = useTranslation();
  const purchases = dossier.read_purchases ?? [];
  if (!purchases.length) return null;
  const unrecorded = dossier.unrecorded_purchases ?? purchases.length;
  const recorded = dossier.review_state === "accepted" && dossier.facts.amount.state === "known";
  const currency = dossier.facts.currency.state === "known" ? dossier.facts.currency.value : null;
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const money = (amount: string, own: string | null = currency) => formatMoney(amount, own, locale) || UNKNOWN_VALUE;
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
            <span className="cuadrao-amount shrink-0 tabular-nums text-black dark:text-white">{purchase.amount ? money(purchase.amount, purchase.currency) : t("business.dossier.unknown_amount", "Amount unknown")}</span>
          </li>
        ))}
      </ul>
      {recorded && unrecorded > 0 && onSettle ? <button type="button" data-testid="dossier-settle-remainder" className={`${secondaryButtonClass} mt-3`} disabled={busy} onClick={onSettle}>{t("business.dossier.settle_remainder", "The rest is already handled")}</button> : null}
    </div>
  );
}

export default function ReceiptDossierReview({ draftId, onUnprepared, receipt, notice }: { draftId: string; onUnprepared?: () => void; receipt?: ReceiptDetail; notice?: ReactNode }) {
  const { t } = useTranslation();
  const primaryKeys = usePrimaryKeys();
  const { source, reload, records, openPanel, guardPanel, panel, chosen } = useBusiness();
  const origin = panel?.kind === "receipt" || panel?.kind === "draft" ? panel : null;
  const receiptIds = origin?.receiptIds ?? [];
  const [dossier, setDossier] = useState<BusinessDossier | null>(null);
  const canDelete = dossier?.delete_available === true && chosen?.capabilities.includes("approve") === true && !!source.deleteDocument;
  const deletion = useDocumentDelete(canDelete && dossier ? {
    id: draftId,
    name: dossier.facts.counterparty.value || receipt?.filename || t("business.document_delete.unnamed"),
    merchant: dossier.facts.counterparty.value,
    family: documentFamily(dossier.document_type),
    date: dossier.facts.occurred_on.value,
    amount: dossier.facts.amount.value,
    currency: dossier.facts.currency.value,
    filename: receipt?.filename ?? dossier.sources.find(item => item.kind === "attachment")?.filename ?? null,
    state: dossier.bandeja_group?.label ? t(`business.bandeja.label.${dossier.bandeja_group.label}`) : t("business.document_delete.previous.attention"),
    receipt,
  } : null, { initialPreview: origin?.confirmDelete === true });
  const [unavailable, setUnavailable] = useState(false);
  const [operation, setOperation] = useState<Operation>({ kind: "idle" });
  const [problem, setProblem] = useState<Problem | null>(null);
  const [fields, setFields] = useState<DgiiFields | null>(null);
  const [fieldsFailed, setFieldsFailed] = useState(false);
  const [fieldsAttempt, setFieldsAttempt] = useState(0);
  const [tab, setTab] = useState<DossierTab>("general");
  const [flash, setFlash] = useState<RowFlash | null>(null);
  const [checking, setChecking] = useState(false);
  const [captureOpen, setCaptureOpen] = useState(false);
  const [captureTarget, setCaptureTarget] = useState<BusinessCaptureInput["draft"]>();
  const [captureRevision, setCaptureRevision] = useState<number>();
  const [captureRetained, setCaptureRetained] = useState(false);
  const [capturePending, setCapturePending] = useState(false);
  const [settling, setSettling] = useState(false);
  const [reopening, setReopening] = useState<"asking" | "sending" | null>(null);
  const [duplicateBusy, setDuplicateBusy] = useState(false);
  const duplicateCompare = useDuplicateCompare(dossier);
  const [advancing, setAdvancing] = useState(false);
  const [finished, setFinished] = useState(false);
  const [fiscalBusy, setFiscalBusy] = useState(false);
  const [fiscalDirty, setFiscalDirty] = useState(false);
  const [fiscalSaved, setFiscalSaved] = useState<BusinessDossier | null>(null);
  const [duplicate, setDuplicate] = useState<{ recordId: string | null } | null>(null);
  const [highlight, setHighlight] = useState<string[]>([]);
  const [approvalCheck, setApprovalCheck] = useState<ApprovalCheck | null>(null);
  const [leaving, setLeaving] = useState<{ proceed: () => void } | null>(null);
  const [retyping, setRetyping] = useState(false);
  const releaseGuard = useRef<(() => void) | null>(null);
  const inFlight = useRef(false);
  // One key per request body: a retry repeats it, and approving anyway is a different request with its own key.
  const approvalKey = useRef<{ version: number; anyway: boolean; suggestions: string; key: string } | null>(null);

  // A draft that is gone closes onto its list, so a dead link never leaves a panel whose Reintentar cannot work.
  // Only a refusal says the person's access; any other failure can pass, so it offers Reintentar.
  const loadFailed = (error: unknown) => {
    if (recordGone(error)) {
      openPanel({ kind: origin?.list ?? "inbox" });
      showToast({ kind: "info", text: t("business.review.gone") });
      return;
    }
    const { code, status } = (error ?? {}) as { code?: string; status?: number };
    const refused = status === 401 || status === 403 || code === "permission_denied" || refusedForGood(error);
    setProblem({ text: refused ? t("business.dossier.unavailable", "This record isn't available with your current access.") : t("common.refresh_failed", "We couldn't update."), reference: referenceCode(error) });
    setUnavailable(refused);
    setDossier(null);
  };
  const onLoadFailed = useEffectEvent(loadFailed);
  const shown = useShownRecord(draftId);
  useEffect(() => {
    let cancelled = false;
    source.dossier(draftId).then((next) => { if (!cancelled) setDossier(next); }).catch((error: unknown) => {
      if (cancelled) return;
      if ((error as { code?: string }).code === "draft_not_prepared") {
        if (onUnprepared) onUnprepared();
        else setProblem({ text: t("business.dossier.missing_draft", "The prepared record isn't available yet. Check the current receipt before continuing.") });
      } else {
        onLoadFailed(error);
      }
    });
    return () => { cancelled = true; };
  }, [draftId, onUnprepared, source, t]);

  useEffect(() => {
    let live = true;
    source.dgiiFields().then((value) => { if (live) { setFields(value); setFieldsFailed(false); } }).catch(() => { if (live) setFieldsFailed(true); });
    return () => { live = false; };
  }, [fieldsAttempt, source]);

  const rowName = (row: SaveRow) => dossierRowLabel(t, row, dossier);
  const autosave = useReviewAutosave({
    source, draftId, dossier, fields, label: rowName,
    onSaved: (next) => { setDossier(next); reload(); },
    onLost: (reference) => {
      setProblem({ text: t("business.dossier.unavailable", "This record isn't available with your current access."), reference });
      setDossier(null);
      setUnavailable(true);
    },
  });

  const rows = useReviewRows({ dossier, autosave, currencies: recordsCurrencySchema.options });
  const amountsPreview = useAmountsPreview(dossier, rows.rows, source.previewAmounts);
  const dirty = rows.unsaved.length > 0;

  const jumpList = useJumpRows(receiptIds);

  const holdsEdits = dirty || fiscalDirty;
  const receiptId = receipt?.id;
  useEffect(() => {
    if (!holdsEdits) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    const release = guardPanel((next, proceed) => {
      const same = next.kind === "draft" ? next.draftId === draftId : next.kind === "receipt" && next.receiptId === receiptId;
      if (same) proceed();
      else setLeaving({ proceed });
    });
    releaseGuard.current = release;
    return () => { window.removeEventListener("beforeunload", warn); release(); };
  }, [draftId, guardPanel, holdsEdits, receiptId]);

  const settle = async () => {
    if (!dossier || settling || inFlight.current) return;
    setSettling(true);
    setProblem(null);
    try {
      setDossier(await source.settleRemainder(draftId, dossier.version, randomId()));
      reload();
    } catch (error) {
      setProblem({ text: t("business.dossier.settle_failed", "The rest could not be marked as handled. Check the current record before trying again."), reference: referenceCode(error) });
    } finally {
      setSettling(false);
    }
  };

  /** The confirmed reopen. The server reverses the money row and answers the open draft, so this screen becomes its review. */
  const reopen = async () => {
    if (!dossier || reopening !== "asking" || inFlight.current) return;
    setReopening("sending");
    setProblem(null);
    try {
      const next = await source.reopenDraft(draftId, dossier.version, randomId());
      setReopening(null);
      setDossier(next);
      reload();
    } catch (error) {
      const code = (error as { code?: string }).code;
      const refused = code === "business_record_matched" || code === "business_refund_linked" ? t(`business.dossier.reopen_refused.${code}`) : null;
      setReopening(null);
      setProblem({ text: refused ?? t("business.dossier.reopen_failed", "This receipt could not be reopened. Check the current record before trying again."), reference: referenceCode(error) });
    }
  };

  const refresh = async () => {
    const asked = draftId;
    setChecking(true);
    try {
      const next = await source.dossier(draftId);
      if (!shown(asked)) return;
      setDossier(next);
      setUnavailable(false);
      if (operation.kind !== "uncertain") { setProblem(null); setDuplicate(null); rows.clear(); }
      else if (next.approval_result?.status === "recorded" || next.approval_result?.status === "failed") { setOperation({ kind: "idle" }); rows.clear(); setProblem(null); }
    } catch (error) {
      if (shown(asked)) loadFailed(error);
    } finally { setChecking(false); }
  };

  const approveRecord = async (request: ApprovalSend): Promise<BusinessDossier | null> => {
    const approval = dossier?.approval_action;
    if (!dossier || !approval || inFlight.current || duplicateBusy || fiscalBusy || fiscalDirty || dirty || autosave.busy || autosave.failed || operation.kind !== "idle") return null;
    inFlight.current = true;
    setOperation({ kind: "approving" });
    setProblem(null);
    setDuplicate(null);
    try {
      const previous = approvalKey.current;
      const suggestions = approval === "record_expense" ? request.suggestions : undefined;
      const body = JSON.stringify(suggestions ?? null);
      const sent = previous?.version === dossier.version && previous.anyway === request.anyway && previous.suggestions === body ? previous : { version: dossier.version, anyway: request.anyway, suggestions: body, key: randomId() };
      approvalKey.current = sent;
      const next = await source.approveDraft(draftId, dossier.version, sent.key, approval, request.anyway, suggestions);
      setDossier(next);
      setOperation(next.approval_result?.status === "outcome_unknown" ? { kind: "uncertain", version: dossier.version } : { kind: "idle" });
      reload();
      return next;
    } catch (error) {
      const { code, status } = error as { code?: string; status?: number };
      const flagged = request.anyway ? [] : confirmationFlags(error);
      const reference = referenceCode(error);
      if (code === "stale_version" || code === "suggestion_stale") {
        setOperation({ kind: "idle" });
        setProblem({ text: t("business.dossier.stale", "This record changed. Open the current revision and review it before taking another action."), reference });
        setDossier(null);
      } else if (status === 401 || status === 403 || status === 404 || code === "permission_denied") {
        setOperation({ kind: "idle" });
        setProblem({ text: t("business.dossier.unavailable", "This record isn't available with your current access."), reference });
        setDossier(null);
        setUnavailable(true);
      } else if (code === "duplicate_comprobante") {
        setOperation({ kind: "idle" });
        setDuplicate({ recordId: duplicateRecordId(error) });
      } else if (flagged.length) {
        setOperation({ kind: "idle" });
        setApprovalCheck({ draftId: dossier.draft_id, version: dossier.version, next: request.next, kind: "flags", codes: flagged });
      } else if (status && status >= 400 && status < 500) {
        setOperation({ kind: "idle" });
        setProblem({ text: t(`business.dgii.error.${code}`, "") || t(`business.dossier.blocker.${code}`, "") || t("business.dossier.refused", "This action could not be completed. Check the current record before trying again."), reference });
      } else {
        setOperation({ kind: "uncertain", version: dossier.version });
        setProblem({ text: t("business.dossier.outcome_unknown", "The action's outcome isn't known yet. Check the saved status before taking another action."), reference });
      }
      return null;
    } finally { inFlight.current = false; }
  };

  const pageOpen = useRef(true);
  useEffect(() => {
    pageOpen.current = true;
    return () => { pageOpen.current = false; };
  }, []);

  const approveAndNext = async (request: ApprovalSend) => {
    if (!receipt) return;
    const seen = origin?.receiptIds?.map(id => ({ id })) ?? records.inbox;
    setAdvancing(true);
    try {
      const approved = await approveRecord(request);
      if (approved?.approval_result?.status !== "recorded" || !pageOpen.current) return;
      const fresh = await source.receipts("inbox").catch(() => null);
      if (!pageOpen.current) return;
      const freshById = new Map(fresh?.map(item => [item.id, item]));
      const ordered = origin?.receiptIds?.flatMap(id => freshById.get(id) ?? []) ?? fresh;
      const next = ordered ? nextBandejaReceipt(receipt.id, seen, ordered) : null;
      if (next) handTitleFocus(next);
      if (!next && fresh && !bandejaReceipts(fresh).some((item) => item.id !== receipt.id)) setFinished(true);
      else openPanel(next ? { kind: "receipt", receiptId: next, ...(origin?.receiptIds ? { list: origin.list, receiptIds: origin.receiptIds } : {}) } : { kind: "inbox" });
    } finally {
      setAdvancing(false);
    }
  };

  const captureDialog = <ManualCaptureDialog key="capture" isOpen={captureOpen} target={captureTarget} revision={captureRevision} onClose={() => setCaptureOpen(false)} onPending={setCapturePending} onRetained={setCaptureRetained} onUnavailable={() => { setUnavailable(true); setDossier(null); }} onSaved={(saved) => { setDossier(saved); setCaptureOpen(false); setUnavailable(false); reload(); }} />;
  const captureRecovery = businessTypedNotesAvailable(records.workspace) && captureRetained && !captureOpen ? <button type="button" className={`${secondaryButtonClass} mb-4`} onClick={() => setCaptureOpen(true)}>{capturePending ? t("business.capture.reopen", "Reopen unconfirmed note") : t("business.capture.reopen_retained", "Reopen retained note")}</button> : null;
  if (unavailable || !dossier && problem) return (<><DossierBare>
    {captureRecovery}
    <section className={SURFACE_CARD} data-testid="receipt-load-error">
      <p role="alert" className="flex items-start gap-2 text-[15px] leading-[22px] text-[#9e2f39] dark:text-[#ec9aa0]"><CircleAlert className="mt-0.5 h-[18px] w-[18px] shrink-0" aria-hidden="true" />{problem?.text ?? t("business.dossier.unavailable", "This record isn't available with your current access.")}</p>
      {problem?.reference ? <div className="mt-1 text-[#9e2f39] dark:text-[#ec9aa0]"><ReferenceCode reference={problem.reference} /></div> : null}
      <button type="button" disabled={checking} onClick={() => void refresh()} className={`${secondaryButtonClass} mt-4`}>{t("common.retry", "Retry")}</button>
    </section></DossierBare>{captureDialog}</>
  );
  if (!dossier) return <><DossierBare>{captureRecovery}<Settle pending layout="detail" /></DossierBare>{captureDialog}</>;
  if (finished) return <DossierBare><ReceiptReviewDone onBack={() => openPanel({ kind: "inbox" })} /></DossierBare>;

  const accounts = dossier.accounts;
  const approval = dossier.approval_result?.status === "recorded" ? dossier.approval_result : null;
  const recorded = approval !== null;
  // The server names the approve action; without one there is nothing this screen may approve.
  const supportedKind = Boolean(dossier.approval_action);
  const settled = !duplicateBusy && !capturePending && !captureOpen && !fiscalBusy && dossier.review_state === "open" && !recorded && operation.kind === "idle" && dossier.approval_result?.status !== "outcome_unknown";
  const mutable = settled && !fiscalDirty;
  const canPrepare = dossier.capabilities.includes("prepare");
  const canApprove = dossier.capabilities.includes("approve");
  const line = approvalLine(canApprove, canPrepare);
  const attachments = dossier.sources.filter((item) => item.kind === "attachment");
  // Line one is who issued it; a record nobody named yet goes by its file.
  const title = dossier.facts.counterparty.state === "known" ? dossier.facts.counterparty.value : receipt?.filename ?? attachments[0]?.filename ?? t("business.dossier.title", "Review record");
  const busy = duplicateBusy || autosave.busy || operation.kind === "approving";
  const saveHolds = autosave.busy || autosave.failed || dirty;
  const approvable = mutable && dossier.approval_available && !saveHolds;
  const reviewing = dossier.review_state === "open" && !recorded;
  const problems = dossierProblems(dossier, t);
  /** A problem's way to its fix: Parece repetido opens Comparar; any other switches to its tab and washes its row. */
  const goProblem = (problem: Pick<DossierProblem, "tab" | "row" | "compare">) => {
    // Comparar waits while the form holds an edit: the compare view could neither save nor drop it.
    if (problem.compare) { if (!(busy || dirty || fiscalDirty || capturePending || captureOpen)) duplicateCompare.open(problem.compare); return; }
    setTab(problem.tab);
    if (problem.row) setFlash((current) => ({ row: problem.row as ReviewRow, n: (current?.n ?? 0) + 1 }));
  };

  const flags = dossier.review_flags ?? [];
  const confirmCodes = flags.filter((flag) => flag.confirm).map((flag) => flag.code);
  // Approval needs no 606 data, so a recorded purchase keeps these choices.
  const showsChoices = (reviewing || dossier.review_state === "accepted") && !dossier.sin_comprobante && (dossier.declaration_editable === true || dossier.dgii?.form === "606");
  const choicesView: ChoicesView | null = showsChoices ? { dossier, fields, failed: fieldsFailed, readOnly: !reviewing && !canPrepare } : null;
  const approve = ({ next, anyway }: ApprovalRequest) => {
    const request = { next, anyway, suggestions: choicesView ? shownSuggestions(choicesView) : undefined };
    if (next) void approveAndNext(request);
    else void approveRecord(request);
  };
  // A record that is not Listos is accepted through one confirm that names every reason.
  const requestApproval = (next = false) => {
    if (!canApprove || !supportedKind || !approvable) return;
    const at = { draftId: dossier.draft_id, version: dossier.version, next };
    if (problems.length) setApprovalCheck({ ...at, kind: "problems" });
    else if (confirmCodes.length) setApprovalCheck({ ...at, kind: "flags", codes: confirmCodes });
    else approve({ next, anyway: false });
  };
  /** A step opened for an older revision, or one that can no longer be approved, approves nothing. */
  const confirmApproval = (check: ApprovalCheck, anyway: boolean) => {
    setApprovalCheck(null);
    if (!canApprove || !supportedKind || !approvable || check.draftId !== dossier.draft_id || check.version !== dossier.version) return;
    approve({ next: check.next, anyway });
  };
  const unsavedNames = [...rows.unsaved.map(rowName), ...(fiscalDirty ? [t("business.dossier.tab.fiscal")] : [])];
  const reason = unsavedNames.length ? t("business.dossier.placeholder.save_first", { fields: unsavedNames.join(", "), defaultValue: "Save or cancel {{fields}} to approve." })
    : autosave.failed && !busy ? t("business.dossier.blocker_unsaved", "A change didn't save. Save it again to approve.")
    : null;
  const reviewNote = readReviewNote(dossier.review_note);
  const reasonId = `approve-reason-${dossier.draft_id}`;
  const approvalLabel = dossier.approval_action === "record_income" ? t("business.dgii.approve_income", "Approve income") : dossier.approval_action === "record_refund" ? t("business.dgii.approve_refund", "Approve refund") : t("business.dossier.approve_action", "Approve expense");

  const canMove = settled && !autosave.busy && !advancing && !settling;
  const moves = canMove && receipt ? receiptNavigationActions(receipt.id, receiptIds, (id) => { handTitleFocus(id); openPanel({ kind: "receipt", receiptId: id, list: origin?.list, receiptIds }); }) : {};
  const position = receipt ? receiptPlace(receipt.id, receiptIds) : null;
  // The last document of a run has one verb. A receipt opened with no list still offers the next one waiting in the Bandeja.
  const lastInList = position ? position.index >= position.total : !receipt;
  const firstSource = dossier.sources[0];
  const fiscalFacts = dossier.facts.fiscal;
  const fiscalEdit: Record<"rnc" | "fiscal_number" | "itbis", { name: "rnc" | "ncf" | "itbis"; value: string }> = {
    rnc: { name: "rnc", value: fiscalFacts?.rnc.value ?? "" },
    fiscal_number: { name: "ncf", value: fiscalFacts?.ecf.value ?? fiscalFacts?.ncf.value ?? "" },
    itbis: { name: "itbis", value: fiscalFacts?.itbis.value ?? "" },
  };
  // The server drops the whole declaration on a new type.
  const retypeClears = Boolean(dossier.dgii?.category || dossier.dgii?.payment_method);
  const rowEdit = (row: ReviewRow): RowEdit => {
    const open = rows.rows[row];
    const edit = open?.edit;
    const facts = edit?.change.write === "facts" ? edit.change.facts : edit?.change.write === "montos" ? { net_amount: edit.change.montos.net_amount, legal_tip: edit.change.montos.legal_tip } : row === "net_amount" && dossier.net_amount?.amount != null ? { net_amount: { state: "known" as const, value: dossier.net_amount.amount } } : {};
    const fiscal = row === "rnc" || row === "fiscal_number" || row === "itbis" ? fiscalEdit[row] : null;
    const typed = edit?.change.write === "fiscal" && fiscal ? edit.change.fiscal[fiscal.name] ?? "" : fiscal?.value;
    const save = autosave.saves[row];
    const saving = save?.state === "saving";
    const retypes = row !== "document_type" || dossier.document_type_editable === true;
    const montosEditable = row !== "net_amount" && row !== "legal_tip" || Boolean(source.reviewMontos);
    return {
      open: Boolean(open),
      saving,
      locked: save?.state === "failed" && save.unknown,
      onOpen: reviewing && canPrepare && mutable && retypes && montosEditable ? () => rows.open(row) : undefined,
      onSave: () => { if (edit?.change.write === "type" && retypeClears && !saving && changesRecord(dossier, edit.change)) setRetyping(true); else rows.save(row); },
      onCancel: () => rows.cancel(row),
      editor: (
        <ReceiptFactEditor
          fiscalForm={!dossier.sin_comprobante ? dossier.dgii?.form ?? (dossier.document_type === "venta" ? "607" : "606") : undefined}
          field={row}
          tried={open?.tried === true}
          facts={dossier.facts}
          patch={facts}
          fiscal={typed}
          documentType={edit?.change.write === "type" ? edit.change.documentType : dossier.document_type}
          uploadYear={dossier.upload_year ?? null}
          yearToCheck={dossier.year_to_check === true}
          accounts={accounts}
          currencies={recordsCurrencySchema.options}
          disabled={!mutable || saving}
          onChange={(patch, invalid) => rows.hold(row, { change: row === "net_amount" || row === "legal_tip" ? { write: "montos", montos: { [row]: patch[row] } } : { write: "facts", facts: { ...facts, ...patch } }, invalid: row === "amount" && !patch.amount ? edit?.invalid ?? false : invalid })}
          onFiscalChange={(value, invalid) => { if (fiscal) rows.hold(row, { change: { write: "fiscal", fiscal: { [fiscal.name]: value || null } }, invalid }); }}
          onDocumentTypeChange={(documentType) => rows.hold(row, { change: { write: "type", documentType }, invalid: false })}
        />
      ),
    };
  };
  const rowNote = (row: ReviewRow) => <ReceiptRowSave save={autosave.saves[row]?.state === "saving" ? undefined : autosave.saves[row]} onRetry={() => rows.retry(row)} />;
  // Where it came from: the receipt's own row when there is one, else the record's first source.
  const cameFrom = receipt
    ? { channel: receipt.channel, sentBy: receipt.sent_by ? sentByName(t, receipt.sent_by) : null, receivedAt: receipt.received_at, filename: receipt.filename, sizeBytes: receipt.size_bytes }
    : firstSource ? { channel: firstSource.channel, receivedAt: firstSource.received_at, filename: firstSource.kind === "attachment" ? firstSource.filename : null } : {};
  const head = {
    recordId: receipt?.id ?? draftId,
    back: recorded ? "transactions" as const : "inbox" as const,
    title,
    // The server's Bandeja label and its reasons: the list and its dossier say the same thing. An accepted record has no pill.
    status: <DossierStatus label={dossier.bandeja_group?.label} deleted={Boolean(dossier.deleted)} problems={problems} onProblem={goProblem}>{dossier.bill_mark ? <span data-testid="bill-mark" className="text-[13px] leading-[18px] text-[#56635e] dark:text-white/70">{dossier.bill_mark}</span> : null}</DossierStatus>,
  };
  const openReceipt = (id: string) => { handTitleFocus(id); openPanel({ kind: "receipt", receiptId: id, list: origin?.list, receiptIds }); };
  const confirmProblems: ConfirmProblem[] = approvalCheck?.kind === "flags" ? approvalCheck.codes.map((code) => ({ key: code, title: t(`business.dossier.review_flag.${code}.title`, { defaultValue: "" }) || dossierRowLabel(t, FLAGGED_ROW[code], dossier), text: t(`business.dossier.review_flag.${code}.text`, { defaultValue: "" }) || t("business.dossier.placeholder.gap.review_flag.text") })) : problems;
  // Comparar turns this same panel into the compare view; it shows both documents itself, so the frame has no source column.
  if (duplicateCompare.candidate) return (<><ContentFade>
    {captureRecovery}
    <ReceiptDuplicateCompare
      dossier={dossier}
      candidate={duplicateCompare.candidate}
      busy={busy || dirty || fiscalDirty || capturePending || captureOpen}
      onBack={duplicateCompare.back}
      onBusyChange={setDuplicateBusy}
      onChanged={(next) => { setDossier(next); duplicateCompare.settled(); reload(); }}
      onDeleted={() => { reload(); openPanel({ kind: "inbox" }); }}
      frame={(body, footer) => <ReceiptReviewFrame {...head} tabs={[{ key: "general", content: body }]} tab="general" onTab={setTab} footer={footer} />}
    />
  </ContentFade>{captureDialog}</>);
  const noSource = !attachments.length && !dossier.sources.some((item) => item.kind === "message" || item.kind === "agent_proposal");
  const [original, ...supporting] = attachments;
  const acceptAria = reason ? reasonId : undefined;
  const accepting = <><Loader2 className="h-[18px] w-[18px] animate-spin motion-reduce:animate-none" aria-hidden="true" />{t("business.dossier.approving", "Approving…")}</>;
  return (<><ContentFade><>
    <ReceiptShortcutRegistration actions={{
      ...(canApprove && supportedKind && approvable && !Object.keys(rows.rows).length ? { approve: () => requestApproval(), ...(receipt ? { approve_next: () => requestApproval(true) } : {}) } : {}),
      ...moves,
      ...(canPrepare && mutable ? { edit: () => {
        const focused = document.activeElement?.closest<HTMLElement>("[data-fact]")?.dataset.fact;
        const row = READ_FACT_ROWS.find((key) => key === focused) ?? READ_FACT_ROWS[0];
        const control = document.querySelector<HTMLInputElement | HTMLSelectElement>(`[data-testid="edit-${row}"] input, [data-testid="edit-${row}"] select`);
        setTab("general");
        if (control) control.focus();
        else rows.open(row);
      } } : {}),
    }} />
    <ReceiptReviewFrame
      {...head}
      place={position ? { ...position, previous: moves.previous, next: moves.next } : null}
      jump={position ? { title: origin?.list === "transactions" ? t("business.nav.transactions", "Transactions") : t("business.nav.inbox", "Inbox"), rows: jumpList.rows, onOpen: jumpList.load, onPick: canMove ? openReceipt : () => {} } : null}
      tab={tab}
      onTab={setTab}
      tabs={[
        { key: "general", count: problems.filter((problem) => problem.tab === "general").length, content: <>
          {captureRecovery}
          {notice}
          <OpenRecordMissingReasons />
          {/* The row in focus or under the pointer marks its value where the message says it verbatim. */}
          <div
            className="contents"
            onFocus={(event) => setHighlight(rowValues(event.target))}
            onMouseOver={(event) => setHighlight(rowValues(event.target))}
            onMouseLeave={() => setHighlight([])}
            onBlur={() => setHighlight([])}
          >
            <ReceiptRecordFacts dossier={dossier} accounts={accounts} problems={problems} flash={flash} choices={choicesView ? <ReceiptOwnerChoices {...choicesView} disabled={!dossier.declaration_editable || (reviewing && !mutable)} saves={autosave.saves} onChoose={(choice, value) => void autosave.save(choice, { write: "purchase", purchase: { [choice]: value } })} onRetry={(choice) => void autosave.retry(choice)} onCancel={autosave.clear} onReload={() => setFieldsAttempt((value) => value + 1)} /> : undefined} typeRow={dossier.document_type ? <ReceiptDocumentType dossier={dossier} edit={reviewing ? rowEdit("document_type") : undefined} note={reviewing ? rowNote("document_type") : undefined} /> : undefined} review={reviewing ? {
              amountsPreview,
              onEdit: canPrepare && mutable ? rows.open : undefined,
              edit: rowEdit,
              note: rowNote,
              noReceipt: {
                onMark: canPrepare && mutable ? (marked) => void autosave.save("receipt_state", { write: "facts", facts: { receipt_state: marked ? { state: "known", value: "no_receipt" } : { state: "unknown", value: null } } }) : undefined,
                busy: autosave.busy,
                note: <ReceiptRowSave save={autosave.saves.receipt_state} onRetry={() => void autosave.retry("receipt_state")} onCancel={() => autosave.clear("receipt_state")} />,
              },
            } : undefined} />
          </div>
          <ReceiptReviewQuestions questions={dossier.questions} />
          {problem ? <div role="alert" className="text-[15px] leading-[22px] text-[#9e2f39] dark:text-[#ec9aa0]"><p className="flex items-start gap-2"><CircleAlert className="mt-0.5 h-[18px] w-[18px] shrink-0" aria-hidden="true" />{problem.text}</p>{problem.reference ? <ReferenceCode reference={problem.reference} /> : null}</div> : null}
          {duplicate ? <div role="alert" data-testid="dossier-duplicate" className={SURFACE_CARD}><p className="text-[15px] leading-[22px] text-[#172b26] dark:text-white">{t("business.dossier.duplicate_recorded", "You already recorded this fiscal receipt.")}</p>{duplicate.recordId ? <button type="button" className={`${secondaryButtonClass} mt-3`} onClick={() => openPanel({ kind: "draft", draftId: duplicate.recordId as string })}>{t("business.dossier.see_recorded", "See the recorded one")}</button> : null}</div> : null}
          {/* An unsettled action keeps its way out in view, not only behind Más. */}
          {!approval && (dossier.approval_result?.status === "failed" || operation.kind === "uncertain" || dossier.approval_result?.status === "outcome_unknown" || dossier.review_state === "accepting") ? <div className={SURFACE_CARD}>
            {dossier.approval_result?.status === "failed" ? <p role="alert" className="text-[13px] text-black/70 dark:text-white/70">{t("business.dossier.approval_failed", "Approval did not finish. Check the current record before another action.")}</p> : null}
            {operation.kind === "uncertain" || dossier.approval_result?.status === "outcome_unknown" || dossier.review_state === "accepting" ? <p role="status" className="mt-3 text-[13px] text-black/70 first:mt-0 dark:text-white/70">{t("business.dossier.outcome_unknown", "The action's outcome isn't known yet. Check the saved status before taking another action.")}</p> : null}
            <button type="button" disabled={busy || checking} onClick={() => void refresh()} className={`${secondaryButtonClass} mt-4`}><RotateCcw className="h-4 w-4" aria-hidden="true" />{t("business.dossier.refresh", "Check current record")}</button>
          </div> : null}
          <ReceiptReadPurchases dossier={dossier} busy={settling || busy} onSettle={canApprove ? settle : undefined} />
        </> },
        { key: "fiscal", content: <FiscalDeclarationEditor key={`${dossier.draft_id}-${dossier.version}`} dossier={dossier} fields={fields} disabled={busy || dirty || capturePending || captureOpen} reviewFiscal={source.reviewFiscal} previewLinks={source.previewAmounts} onBusy={setFiscalBusy} onDirty={setFiscalDirty} saved={fiscalSaved === dossier} onChanged={(value) => { setFiscalSaved(value); setDossier(value); reload(); }} /> },
        { key: "detalles", content: <DossierDetails origin={cameFrom} /> },
        { key: "historial", content: <ReceiptHistory documentType={dossier.document_type} history={dossier.history} accounts={accounts} sources={dossier.sources} approval={dossier.approval_result} dgiiFields={fields} /> },
      ]}
      document={
        <DossierDocument
          file={original ? { id: original.connection_id, filename: original.filename, media_type: original.media_type, channel: original.channel, email_delivery_ids: original.email_delivery_ids } : null}
          extra={supporting.length || !noSource && !original || dossier.sources.some((item) => item.kind !== "attachment") ? <>
            {supporting.map((attachment) => <ReceiptSourcePreview key={attachment.id} initialExpanded detail={{ id: attachment.connection_id, filename: attachment.filename, media_type: attachment.media_type, received_at: attachment.received_at, channel: attachment.channel, email_delivery_ids: attachment.email_delivery_ids }} />)}
            <ReceiptMessages sources={dossier.sources} highlight={highlight} />
          </> : undefined}
        >
          {/* A message is the original; only a record with nothing at all says so, quietly. */}
          {noSource ? <p data-testid="receipt-no-source" className="m-auto text-[14px] text-[#56635e] dark:text-white/70">{dossier.facts.receipt_state.state === "known" && dossier.facts.receipt_state.value === "no_receipt" ? t("business.dossier.no_receipt", "No receipt was supplied.") : t("business.dossier.no_attachment", "No receipt file is attached to this record.")}</p> : null}
        </DossierDocument>
      }
      footer={deletion.confirmBar ?? <ReceiptReviewFooter
        reviewNote={reviewNote}
        status={approval ? null
          : !canApprove ? line ? <p>{t("business.dossier.prepare_only", "Your permission allows preparing this record. A person with approval permission must approve it.")}</p> : null
          : reason ? <p id={reasonId} data-testid="approve-reason">{reason}</p>
          : null}
        actions={<>
          <ReceiptMoreMenu groups={[
            businessTypedNotesAvailable(records.workspace) && canPrepare && mutable && !Object.keys(rows.rows).length ? <MenuItem key="note" icon={StickyNote} label={t("business.capture.add_note", "Add note")} onSelect={() => { setCaptureTarget({ draft_id: dossier.draft_id, version: dossier.version }); setCaptureRevision(factsRevision(dossier)); setCaptureOpen(true); }} /> : null,
            <ReceiptMarksCard key="marks" dossier={dossier} busy={busy || fiscalBusy || fiscalDirty} onChanged={setDossier} bare />,
            canDelete ? <DeleteDocumentMenuItem key="delete" disabled={busy || dirty || fiscalBusy || fiscalDirty || deletion.busy} onClick={deletion.ask} /> : null,
          ]} />
          {dossier.restore_available ? <RestoreDocumentButton id={draftId} onRestored={() => void refresh()} target={receipt ? { kind: "receipt", receiptId: receipt.id, list: "inbox" } : { kind: "draft", draftId, list: "inbox" }} /> : null}
          {approval && dossier.reopen_available === true ? <button type="button" data-testid="reopen-record" aria-busy={reopening === "sending"} className={`${secondaryButtonClass} whitespace-nowrap`} disabled={reopening !== null || busy || fiscalBusy || fiscalDirty} onClick={() => { setProblem(null); setReopening("asking"); }}>{reopening === "sending" ? <><Loader2 className="h-[18px] w-[18px] animate-spin motion-reduce:animate-none" aria-hidden="true" />{t("business.dossier.reopening", "Reopening…")}</> : t("business.dossier.reopen", "Reopen")}</button> : null}
          {!approval && canApprove ? receipt && !lastInList ? <>
            <button type="button" aria-busy={operation.kind === "approving" && !advancing} className={`${secondaryButtonClass} whitespace-nowrap`} aria-describedby={acceptAria} disabled={!supportedKind || !approvable} onClick={() => requestApproval()}>{operation.kind === "approving" && !advancing ? accepting : approvalLabel}</button>
            <button type="button" data-review-primary="" aria-busy={operation.kind === "approving" && advancing} className={`${primaryButtonClass} ${KEY_HINT_CLASS} whitespace-nowrap`} data-keys={primaryKeys} aria-describedby={acceptAria} aria-keyshortcuts="Meta+Enter Control+Enter" disabled={!supportedKind || !approvable} onClick={() => requestApproval(true)}>{operation.kind === "approving" && advancing ? accepting : t("business.dossier.approve_next", "Approve and next")}</button>
          </> : (
            <button type="button" data-review-primary="" aria-busy={operation.kind === "approving"} className={`${primaryButtonClass} ${KEY_HINT_CLASS} whitespace-nowrap`} data-keys={primaryKeys} aria-describedby={acceptAria} aria-keyshortcuts="Meta+Enter Control+Enter" disabled={!supportedKind || !approvable} onClick={() => requestApproval(Boolean(receipt))}>{operation.kind === "approving" ? accepting : approvalLabel}</button>
          ) : null}
        </>}
      />}
    />
    {deletion.dialog}
    {reopening ? <ConfirmDialog
      isOpen
      tone="primary"
      title={t("business.dossier.reopen_title", "Reopen this receipt?")}
      description={t("business.dossier.reopen_body", "It goes back to the Inbox so you can correct it. It leaves your records until you approve it again.")}
      confirmLabel={t("business.dossier.reopen", "Reopen")}
      cancelLabel={t("common.cancel", "Cancel")}
      isBusy={reopening === "sending"}
      onCancel={() => { if (reopening === "asking") setReopening(null); }}
      onConfirm={() => void reopen()}
    /> : null}
    {approvalCheck && confirmProblems.length ? <DossierConfirm
      problems={confirmProblems}
      onClose={() => setApprovalCheck(null)}
      onFix={() => {
        setApprovalCheck(null);
        const first = approvalCheck.kind === "flags" ? { tab: "general" as const, row: FLAGGED_ROW[approvalCheck.codes[0]] } : problems[0];
        if (first) goProblem(first);
      }}
      onAcceptAnyway={() => confirmApproval(approvalCheck, true)}
    /> : null}
    {leaving ? <ConfirmDialog
      isOpen
      tone="primary"
      title={t("business.settings.profile_discard_title", "Discard your changes?")}
      description={t("business.settings.profile_discard_detail", "Changes in this section haven't been saved.")}
      confirmLabel={t("business.settings.profile_discard", "Discard changes")}
      cancelLabel={t("business.settings.profile_keep_editing", "Keep editing")}
      onCancel={() => { setLeaving(null); requestAnimationFrame(() => document.querySelector<HTMLElement>("[data-row-open] input, [data-row-open] select")?.focus()); }}
      onConfirm={() => { releaseGuard.current?.(); setLeaving(null); leaving.proceed(); }}
    /> : null}
    {retyping ? <ConfirmDialog
      isOpen
      tone="primary"
      title={t("business.dossier.type_label", "Type")}
      description={t("business.dossier.type_clears_choices", "Changing the type clears the expense type and payment form.")}
      confirmLabel={t("common.save", "Save")}
      cancelLabel={t("common.cancel", "Cancel")}
      onCancel={() => setRetyping(false)}
      onConfirm={() => { setRetyping(false); rows.save("document_type"); }}
    /> : null}
    {receipt ? <ReceiptSeenBoundary receipt={receipt} hydrated={dossier.draft_id === receipt.draft_id && dossier.version === receipt.version} /> : null}
  </></ContentFade>
    {/* Every branch returns a fragment holding the keyed note dialog, so a denied save that hides the record keeps the typed text. */}
    {captureDialog}
  </>
  );
}
