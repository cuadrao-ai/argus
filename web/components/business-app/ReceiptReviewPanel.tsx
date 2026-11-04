"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CircleAlert, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { referenceCode } from "@/lib/failure-screen";
import { ReceiptShortcutRegistration, receiptNavigationActions, receiptPlace } from "./BusinessReviewShortcuts";
import ReceiptSeenBoundary from "./ReceiptSeenBoundary";
import ReceiptReadingControl from "./ReceiptReadingControl";
import ReceiptDossierReview from "./ReceiptDossierReview";
import ReceiptReadNotice from "./ReceiptReadNotice";
import ReceiptReadingState, { ReadingSheen } from "./ReceiptReadingState";
import { rebindAndPrepare } from "./receipt-rebind";
import { useReceiptReadPoll } from "./receipt-read-poll";
import ReceiptSourcePreview from "./ReceiptSourcePreview";
import ReceiptReviewFrame from "./ReceiptReviewFrame";
import { SURFACE_CARD } from "./foundation/surfaces";
import { handTitleFocus } from "./bandeja-order";
import { receiptReviewAccess } from "./receipt-review-access";
import { useReceiptStateWord } from "./receipt-state-word";
import type { ReceiptDetail } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { useBusinessConsent } from "./business-consent-context";
import { formatDay, formatMoney, UNKNOWN_VALUE } from "./business-format";
import { canAddRecords, primaryButtonClass, quietButtonClass, secondaryButtonClass, StatusPill, useTerminalRead } from "./business-ui";
import { ContentFade, Settle } from "./business-skeletons";
import { resolveLanguage } from "@/lib/language-features";

function ReceiptEntry({ receiptId }: { receiptId: string }) {
  const { t, i18n } = useTranslation();
  const stateWord = useReceiptStateWord();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const money = (amount: string | null, currency: string | null) => formatMoney(amount, currency, locale) || UNKNOWN_VALUE;
  const terminalRead = useTerminalRead();
  const { source, reload, openPanel, revision, panel, actions, chosen } = useBusiness();
  const origin = panel?.kind === "receipt" || panel?.kind === "draft" ? panel : null;
  const receiptIds = origin?.receiptIds ?? [];
  const consent = useBusinessConsent();
  const [detail, setDetail] = useState<ReceiptDetail | null>(null);
  // The reference of the last load that failed.
  const [failure, setFailure] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState<"prepare" | "rebind" | "refresh" | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [unprepared, setUnprepared] = useState(false);
  const retainReceipt = useCallback(() => setUnprepared(true), []);
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
      .catch((error: unknown) => !cancelled && setFailure(referenceCode(error)));
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
      <section className={SURFACE_CARD} data-testid="receipt-load-error">
        <p role="alert" className="flex items-start gap-2 text-[15px] leading-[22px] text-[#9e2f39] dark:text-[#ec9aa0]">
          <CircleAlert className="mt-0.5 h-[18px] w-[18px] shrink-0" aria-hidden="true" />
          {t("business.review.error", "This receipt isn't available. It may have been removed.")}
        </p>
        <button type="button" className={`${secondaryButtonClass} mt-4`} onClick={retry}>
          {t("common.retry", "Retry")}
        </button>
      </section>
    );
  }
  if (!detail) return <Settle pending layout="detail" />;
  const terminal = terminalRead(detail.attention, detail.error_code);
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
  const openReceipt = (id: string) => { handTitleFocus(id); openPanel({ kind: "receipt", receiptId: id, list: origin?.list, receiptIds }); };
  const position = receiptPlace(receiptId, receiptIds);
  const moves = busy ? {} : receiptNavigationActions(receiptId, receiptIds, openReceipt);
  const place = position ? { ...position, previous: moves.previous, next: moves.next } : null;
  const frame = (children: React.ReactNode, source: React.ReactNode = <ReceiptSourcePreview detail={detail} />, reading = false) => (
    <ContentFade><ReceiptReviewFrame
      recordId={receiptId}
      back={confirmed ? "transactions" : "inbox"}
      title={detail.merchant || (confirmed ? t("business.review.saved_title", "Saved expense") : t("business.review.title", "Review receipt"))}
      badge={<StatusPill status={detail.status} label={stateWord(detail) || undefined} />}
      amount={!reading && detail.amount && detail.currency ? formatMoney(detail.amount, detail.currency, locale) : null}
      origin={{ channel: detail.channel, receivedAt: detail.received_at }}
      place={place}
      source={source}
    >
      {children}
    </ReceiptReviewFrame></ContentFade>
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
          ? t("business.review.reading_off", "Turn on Read my receipts automatically in your WhatsApp settings, then try again.")
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
    setBusy("refresh");
    try {
      setDetail(await source.receipt(detail.id));
      setUnprepared(false);
    } catch (error) {
      setFailure(referenceCode(error));
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
        <ReadingSheen><ReceiptSourcePreview detail={detail} /></ReadingSheen>,
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
                  <div className="mt-3 flex flex-wrap gap-2">
                    {terminal.upload && uploadAnother ? (
                      <button type="button" className={primaryButtonClass} onClick={uploadAnother.run}>
                        {terminal.uploadLabel}
                      </button>
                    ) : null}
                  </div>
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
        <>
          <ReceiptSourcePreview detail={detail} />
          {detail.evidence ? (
            <details className={SURFACE_CARD}>
              <summary className="cursor-pointer text-[14px] font-medium text-black/70 dark:text-white/70">
                {t("business.review.evidence", "What the receipt says")}
              </summary>
              <dl className="mt-3 space-y-1.5 text-[13px] text-black/65 dark:text-white/65">
                {detail.evidence.merchant ? <div className="flex justify-between gap-3"><dt>{t("business.review.merchant", "Merchant")}</dt><dd className="text-right">{detail.evidence.merchant}</dd></div> : null}
                {detail.evidence.occurred_on ? <div className="flex justify-between gap-3"><dt>{t("business.review.date", "Date")}</dt><dd>{formatDay(detail.evidence.occurred_on, locale)}</dd></div> : null}
                {detail.evidence.lines.map((line, index) => (
                  <div key={index} className="flex justify-between gap-3"><dt className="truncate">{line.description}</dt><dd className="cuadrao-amount tabular-nums">{money(line.amount, detail.evidence?.currency ?? null)}</dd></div>
                ))}
                {detail.evidence.tax ? <div className="flex justify-between gap-3"><dt>{t("business.review.tax", "Tax")}</dt><dd className="cuadrao-amount tabular-nums">{money(detail.evidence.tax, detail.evidence.currency)}</dd></div> : null}
                {detail.evidence.total ? <div className="flex justify-between gap-3 font-medium text-black dark:text-white"><dt>{t("business.review.amount", "Total")}</dt><dd className="cuadrao-amount tabular-nums">{money(detail.evidence.total, detail.evidence.currency)}</dd></div> : null}
              </dl>
              <p className="mt-3 text-[12px] text-black/45 dark:text-white/45">
                {t("business.review.evidence_note", "Your corrections don't change what was read from the receipt. One receipt saves one expense for its total.")}
              </p>
            </details>
          ) : null}
        </>,
      )}
      <ReceiptSeenBoundary receipt={detail} hydrated={detail.activity?.state === "ready" && !incompleteBridge} />
    </>
  );
}

export default function ReceiptReviewPanel({ target }: { target: { kind: "receipt" | "draft"; id: string } }) {
  return target.kind === "draft" ? <ReceiptDossierReview draftId={target.id} /> : <ReceiptEntry receiptId={target.id} />;
}
