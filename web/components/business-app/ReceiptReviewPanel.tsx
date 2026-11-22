"use client";

import { useCallback, useEffect, useEffectEvent, useState, type ReactNode } from "react";
import { AlertCircle, CircleAlert, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { recordGone, referenceCode } from "@/lib/failure-screen";
import { ReceiptShortcutRegistration, receiptNavigationActions, receiptPlace } from "./BusinessReviewShortcuts";
import ReceiptSeenBoundary from "./ReceiptSeenBoundary";
import ReceiptReadingControl from "./ReceiptReadingControl";
import ReceiptDossierReview from "./ReceiptDossierReview";
import ReceiptReadNotice from "./ReceiptReadNotice";
import ReceiptReadingState from "./ReceiptReadingState";
import { rebindAndPrepare } from "./receipt-rebind";
import { useReceiptReadPoll } from "./receipt-read-poll";
import type { DossierTab } from "./dossier-attention";
import DossierDetails from "./dossier/DossierDetails";
import DossierDocument from "./dossier/DossierDocument";
import { DossierStatus } from "./dossier/DossierHeader";
import { DossierBare } from "./dossier/DossierParts";
import { useJumpRows } from "./dossier/jump-rows";
import ReceiptReviewFrame from "./ReceiptReviewFrame";
import { DeleteDocumentMenuItem, RestoreDocumentButton, receiptDeleteTarget, useDocumentDelete } from "./DocumentDeleteControls";
import ReceiptReviewFooter, { ReceiptMoreMenu } from "./ReceiptReviewFooter";
import { SURFACE_CARD } from "./foundation/surfaces";
import { showToast } from "./foundation/toasts";
import { handTitleFocus } from "./bandeja-order";
import { receiptReviewAccess } from "./receipt-review-access";
import { useShownRecord } from "./useShownRecord";
import type { ReceiptDetail } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { useBusinessConsent } from "./business-consent-context";
import { formatMoney, UNKNOWN_VALUE } from "./business-format";
import { sentByName } from "@/lib/sent-by";
import { canAddRecords, dangerButtonClass, primaryButtonClass, quietButtonClass, secondaryButtonClass, useTerminalRead } from "./business-ui";
import { ContentFade, Settle } from "./business-skeletons";
import { resolveLanguage } from "@/lib/language-features";

function ReceiptEntry({ receiptId }: { receiptId: string }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const money = (amount: string | null, currency: string | null) => formatMoney(amount, currency, locale) || UNKNOWN_VALUE;
  const terminalRead = useTerminalRead();
  const { source, reload, openPanel, revision, panel, actions, chosen } = useBusiness();
  const origin = panel?.kind === "receipt" || panel?.kind === "draft" ? panel : null;
  const reviewList = origin?.reviewList;
  const receiptIds = reviewList?.receiptIds ?? [];
  const consent = useBusinessConsent();
  const [detail, setDetail] = useState<ReceiptDetail | null>(null);
  // The reference of the last load that failed.
  const [failure, setFailure] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState<"prepare" | "rebind" | "refresh" | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [unprepared, setUnprepared] = useState(false);
  const [tab, setTab] = useState<DossierTab>("general");
  const jumpList = useJumpRows(receiptIds);
  const canDelete = detail?.delete_available === true && chosen?.capabilities.includes("approve") === true && !!source.deleteDocument;
  const deletion = useDocumentDelete(canDelete && detail ? receiptDeleteTarget(detail, detail.bandeja_group?.label ? t(`business.bandeja.label.${detail.bandeja_group.label}`) : t("business.document_delete.deleted_state"), t("business.document_delete.unnamed")) : null, { initialPreview: origin?.confirmDelete === true });
  const retainReceipt = useCallback(() => setUnprepared(true), []);
  const shown = useShownRecord(receiptId);
  // A receipt that is gone closes onto its list, so a dead link never leaves a panel whose Reintentar cannot work.
  const loadFailed = (error: unknown) => {
    if (!recordGone(error)) {
      setFailure(referenceCode(error));
      return;
    }
    openPanel({ kind: origin?.list ?? "inbox" });
    showToast({ kind: "info", text: t("business.review.gone") });
  };
  const onLoadFailed = useEffectEvent(loadFailed);
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    source
      .receipt(receiptId, controller.signal)
      .then((next) => {
        if (cancelled) return;
        setDetail(next);
        setFailure(null);
      })
      .catch((error: unknown) => {
        if (!cancelled) onLoadFailed(error);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [receiptId, source, revision, attempt]);

  const { canPrepare, canApprove } = detail ? receiptReviewAccess(detail) : { canPrepare: false, canApprove: false };
  const confirmed = detail?.status === "confirmed";
  // Backend state only: the receipt is being read when the server's Bandeja flag says so, never from the status.
  const waitingForAi = detail?.bandeja?.leyendo === true;
  const [readStalled, setReadStalled] = useState(false);
  // The read settles on the server; this page asks again until it has, so the same page moves on.
  useReceiptReadPoll({
    source,
    receiptId,
    pending: waitingForAi,
    onSettled: (next) => {
      setDetail(next);
      setUnprepared(false);
      setReadStalled(false);
      reload();
    },
    onStalled: () => setReadStalled(true),
  });

  const retry = () => { setFailure(null); setAttempt((value) => value + 1); };
  const openDraft = unprepared ? null : detail?.draft_id ?? null;
  // An open dossier stays mounted through a failed refetch: its rows hold what the person typed.
  if (failure !== null && !openDraft) {
    return (
      <DossierBare><section className={SURFACE_CARD} data-testid="receipt-load-error">
        <p role="alert" className="flex items-start gap-2 text-[15px] leading-[22px] text-[#9e2f39] dark:text-[#ec9aa0]">
          <CircleAlert className="mt-0.5 h-[18px] w-[18px] shrink-0" aria-hidden="true" />
          {t("common.refresh_failed", "We couldn't update.")}
        </p>
        <div className="mt-1 text-[#9e2f39] dark:text-[#ec9aa0]"><ReferenceCode reference={failure} /></div>
        <button type="button" className={`${secondaryButtonClass} mt-4`} onClick={retry}>
          {t("common.retry", "Retry")}
        </button>
      </section></DossierBare>
    );
  }
  if (!detail) return <DossierBare><Settle pending layout="detail" /></DossierBare>;
  const terminal = terminalRead(detail.attention);
  const uploadAnother = canAddRecords(chosen) ? actions.create.find((action) => action.id === "upload_receipt") : null;
  if (openDraft) {
    const notice = failure === null ? null : (
      <div role="alert" data-testid="receipt-refetch-failed" className="text-[15px] leading-[22px] text-[#9e2f39] dark:text-[#ec9aa0]">
        <p className="flex items-start gap-2"><CircleAlert className="mt-0.5 h-[18px] w-[18px] shrink-0" aria-hidden="true" />{t("common.refresh_failed", "We couldn't update.")}</p>
        <div className="flex flex-wrap items-center gap-x-3">
          <ReferenceCode reference={failure} />
          <button type="button" className={quietButtonClass} onClick={retry}>{t("common.retry", "Retry")}</button>
        </div>
      </div>
    );
    return <ReceiptDossierReview draftId={openDraft} onUnprepared={retainReceipt} receipt={detail} notice={notice} />;
  }
  const openReceipt = (id: string) => {
    handTitleFocus(id);
    openPanel({ kind: "receipt", receiptId: id, ...(reviewList ? { list: origin?.list, reviewList } : {}) });
  };
  const position = receiptPlace(receiptId, receiptIds);
  const moves = busy ? {} : receiptNavigationActions(receiptId, receiptIds, openReceipt);
  const place = position ? { ...position, previous: moves.previous, next: moves.next } : null;
  const frame = (children: ReactNode, reading = false) => (
    <ContentFade><ReceiptReviewFrame
      recordId={receiptId}
      back={confirmed ? "transactions" : "inbox"}
      // A receipt nobody named yet goes by its file.
      title={detail.merchant || detail.filename || (confirmed ? t("business.review.saved_title", "Saved expense") : t("business.review.title", "Review receipt"))}
      status={<DossierStatus label={detail.bandeja_group?.label} deleted={Boolean(detail.deleted)} />}
      place={place}
      jump={place ? { title: origin?.list === "transactions" ? t("business.nav.transactions", "Transactions") : t("business.nav.inbox", "Inbox"), rows: jumpList.rows, onOpen: jumpList.load, onPick: busy ? () => {} : openReceipt } : null}
      tab={tab}
      onTab={setTab}
      tabs={[
        { key: "general", content: children },
        { key: "detalles", content: <DossierDetails origin={{ channel: detail.channel, sentBy: detail.sent_by ? sentByName(t, detail.sent_by) : null, receivedAt: detail.received_at, filename: detail.filename, sizeBytes: detail.size_bytes }} /> },
      ]}
      document={<DossierDocument file={detail} reading={reading} />}
      footer={deletion.confirmBar ?? (canDelete ? <ReceiptReviewFooter actions={<ReceiptMoreMenu groups={[<DeleteDocumentMenuItem key="delete" disabled={busy !== null || deletion.busy} onClick={deletion.ask} />]} />} /> : detail.restore_available ? <RestoreDocumentButton id={detail.draft_id ?? detail.id} target={{ kind: "receipt", receiptId: detail.id, list: "inbox" }} /> : undefined)}
    />{deletion.dialog}</ContentFade>
  );
  if (!waitingForAi && (detail.activity?.state === "saved_unread" || detail.activity?.state === "reading")) return frame(<><ReceiptReadingControl /><ReceiptReadNotice receipt={detail} preparable={false} /></>);
  const incompleteBridge = unprepared || (detail.status === "review_ready" && !detail.enterable);

  const prepare = async () => {
    if (!consent.accepted) {
      consent.reopen();
      return;
    }
    setBusy("prepare");
    setProblem(null);
    try {
      await source.prepareReceipt(detail.id);
      setDetail(await source.receipt(detail.id));
      setUnprepared(false);
      reload();
    } catch (error) {
      setProblem(
        (error as { code?: string }).code === "whatsapp_receipt_reading_off"
          ? t("business.review.reading_off")
          : t("business.review.prepare_failed", "We couldn't start preparation. Your receipt is saved. Try again."),
      );
    } finally {
      setBusy(null);
    }
  };

  const rebind = async () => {
    if (!consent.accepted) {
      consent.reopen();
      return;
    }
    setBusy("rebind");
    setProblem(null);
    try {
      await rebindAndPrepare(source, detail.id, setDetail);
      setUnprepared(false);
      reload();
    } catch {
      setProblem(t("business.review.rebind_failed", "We couldn't bind this receipt to your access. Check your permission and try again."));
    } finally {
      setBusy(null);
    }
  };

  const refresh = async () => {
    const asked = receiptId;
    setBusy("refresh");
    try {
      const next = await source.receipt(detail.id);
      if (!shown(asked)) return;
      setDetail(next);
      setUnprepared(false);
    } catch (error) {
      if (shown(asked)) loadFailed(error);
    } finally {
      setBusy(null);
    }
  };

  // A read the backend says is running shows the reading state until it settles; the poll then swaps in the filled fields at once.
  if (waitingForAi) {
    return <>
      <ReceiptShortcutRegistration actions={moves} />
      {frame(
        <ReceiptReadingState>
          {readStalled ? (
            <div role="status" data-testid="receipt-read-stalled" className="text-[15px] leading-[22px] text-[#56635e] dark:text-white/70">
              <p>{t("business.review.poll_stopped", "Still reading. Check the current record to see the latest state.")}</p>
              <button type="button" disabled={busy !== null} className={`${secondaryButtonClass} mt-3`} onClick={() => void refresh()}>{t("business.dossier.refresh", "Check current record")}</button>
            </div>
          ) : null}
          {detail.activity?.state === "reading" ? <ReceiptReadingControl /> : null}
        </ReceiptReadingState>,
        true,
      )}
    </>;
  }
  return (
    <>
      <ReceiptShortcutRegistration actions={moves} />
      {frame(
        <>
          {detail.email_original ? <div role="note" data-testid="receipt-email-original" className={`${SURFACE_CARD} text-[14px] text-black/70 dark:text-white/70`}><p>{t("business.review.email_original", "This is the email itself. Its attachment is the receipt to review.")}</p></div> : null}
          {incompleteBridge ? <div className={`${SURFACE_CARD} text-[14px] text-black/70 dark:text-white/70`}><p role="alert">{t("business.dossier.missing_draft", "The prepared record isn't available yet. Check the current receipt before continuing.")}</p><button type="button" disabled={busy !== null} className={`${secondaryButtonClass} mt-3`} onClick={() => void refresh()}>{t("business.dossier.refresh", "Check current record")}</button></div> : null}
          {detail.status === "needs_attention" ? (
            <div role="alert" data-testid="receipt-attention" className={`${SURFACE_CARD} text-[14px] text-black/75 dark:text-white/75`}>
              {terminal ? (
                <>
                  <p className="flex gap-2.5">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-[#d66d75]" aria-hidden="true" />
                    <span>
                      <span className="block font-medium">{terminal.title}</span>
                      <span className="mt-1 block">{terminal.body}</span>
                    </span>
                  </p>
                  {(terminal.upload && uploadAnother) || (terminal.discard && canDelete) ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {terminal.upload && uploadAnother ? (
                        <button type="button" className={primaryButtonClass} onClick={uploadAnother.run}>
                          {terminal.uploadLabel}
                        </button>
                      ) : null}
                      {terminal.discard && canDelete ? (
                        <button type="button" className={dangerButtonClass} disabled={busy !== null || deletion.busy} onClick={deletion.ask}>
                          {t("business.document_delete.menu")}
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </>
              ) : (
                <p className="flex gap-2.5">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-[#d66d75]" aria-hidden="true" />
                  <span>{t(`business.attention_short.${detail.attention}`)}</span>
                </p>
              )}
              {detail.duplicate_of ? (
                <button type="button" data-testid="receipt-duplicate-original" className={`${secondaryButtonClass} mt-3`} onClick={() => openPanel({ kind: "receipt", receiptId: detail.duplicate_of as string })}>
                  {t("business.review.see_original", "See the receipt already saved")}
                </button>
              ) : null}
              {detail.error_code === "business_record_not_found" && canApprove ? (
                <>
                  <p className="mt-3 text-[13px] text-black/55 dark:text-white/55">{t("business.review.rebind_note", "The access that prepared this receipt is no longer valid. Bind it to your current access, then prepare it again.")}</p>
                  <button type="button" data-testid="receipt-rebind" disabled={busy !== null} onClick={() => void rebind()} className={`${secondaryButtonClass} mt-3`}>
                    {t("business.review.rebind", "Bind to my current access")}
                  </button>
                </>
              ) : null}
              {detail.preparable && canPrepare ? (
                <>
                  <p className="mt-3 text-[13px] text-black/55 dark:text-white/55">
                    {t("business.review.retry_consent", "Trying again sends this receipt to our AI provider.")}
                  </p>
                  <button type="button" disabled={busy !== null} onClick={() => void prepare()} className={`${secondaryButtonClass} mt-3`}>
                    <RotateCcw className="h-4 w-4" aria-hidden="true" />
                    {t("business.review.retry", "Read again")}
                  </button>
                </>
              ) : null}
            </div>
          ) : null}
          <ReceiptReadNotice receipt={detail} preparable={detail.preparable && canPrepare} />
          {problem ? (
            <p role="alert" className="flex items-start gap-2 text-[15px] leading-[22px] text-[#9e2f39] dark:text-[#ec9aa0]"><CircleAlert className="mt-0.5 h-[18px] w-[18px] shrink-0" aria-hidden="true" />{problem}</p>
          ) : null}

          {confirmed ? (
            <div className={`${SURFACE_CARD} flex flex-wrap items-center justify-between gap-3`}>
              <p className="text-[14px] text-black/75 dark:text-white/75">
                {t("business.review.saved_body", "Saved as one expense of {{amount}}.", { amount: money(detail.amount, detail.currency) })}
              </p>
              <button type="button" className={secondaryButtonClass} onClick={() => openPanel({ kind: "transactions" })}>
                {t("business.review.view_expenses", "View expenses")}
              </button>
            </div>
          ) : canPrepare ? null : <p className="text-[13px] text-black/65 dark:text-white/65">{t("business.dossier.read_only", "Your permission allows viewing this record.")}</p>}
        </>,
      )}
      <ReceiptSeenBoundary receipt={detail} hydrated={detail.activity?.state === "ready" && !incompleteBridge} />
    </>
  );
}

export default function ReceiptReviewPanel({ target }: { target: { kind: "receipt" | "draft"; id: string } }) {
  return target.kind === "draft" ? <ReceiptDossierReview draftId={target.id} /> : <ReceiptEntry receiptId={target.id} />;
}
