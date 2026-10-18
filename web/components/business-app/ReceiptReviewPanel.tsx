"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ReceiptShortcutRegistration, receiptNavigationActions } from "./BusinessReviewShortcuts";
import ReceiptSeenBoundary from "./ReceiptSeenBoundary";
import ReceiptReadingControl from "./ReceiptReadingControl";
import ReceiptDossierReview from "./ReceiptDossierReview";
import ReceiptReadNotice from "./ReceiptReadNotice";
import { rebindAndPrepare } from "./receipt-rebind";
import { useReceiptReadPoll } from "./receipt-read-poll";
import ReceiptSourcePreview from "./ReceiptSourcePreview";
import ReceiptReviewFrame from "./ReceiptReviewFrame";
import { handTitleFocus } from "./bandeja-order";
import { receiptReviewAccess } from "./receipt-review-access";
import MoneyInput from "@/components/money/MoneyInput";
import { moneyProblemFromServer } from "@/lib/money-entry";
import type { ReceiptDetail, ReceiptReviewFields } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { formatBusinessName, formatDay, formatMoney, RECEIPT_CATEGORY_IDS } from "./business-format";
import {
  cardClass,
  LoadingRows,
  primaryButtonClass,
  secondaryButtonClass,
  StatusPill,
  useAttentionLabel,
  useCategoryLabel,
} from "./business-ui";

type Draft = Record<keyof ReceiptReviewFields, string>;

const FIELDS: (keyof ReceiptReviewFields)[] = [
  "merchant",
  "occurred_on",
  "amount",
  "currency",
  "category_id",
  "account_id",
];

function draftFrom(detail: ReceiptDetail): Draft {
  return Object.fromEntries(FIELDS.map((key) => [key, detail[key] ?? ""])) as Draft;
}

const inputClass =
  "mt-1.5 block min-h-11 w-full rounded-[12px] border border-black/10 bg-white px-3 text-[16px] text-black outline-none transition-colors focus-visible:border-black/30 focus-visible:ring-[0.125rem] focus-visible:ring-black/10 disabled:bg-black/[0.03] disabled:text-black/50 dark:border-white/10 dark:bg-[#141517] dark:text-white dark:disabled:bg-white/[0.03]";

function ReceiptEntry({ receiptId }: { receiptId: string }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const categoryLabel = useCategoryLabel();
  const attentionLabel = useAttentionLabel();
  const { source, reload, openPanel, revision, records } = useBusiness();
  const [detail, setDetail] = useState<ReceiptDetail | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState<"prepare" | "rebind" | "save" | "refresh" | null>(null);
  const [uncertainVersion, setUncertainVersion] = useState<number | null>(null);
  const inFlight = useRef(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [amountInvalid, setAmountInvalid] = useState(false);
  const [amountError, setAmountError] = useState<string | null>(null);
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
        setDraft(draftFrom(next));
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [receiptId, source, revision]);

  const { accounts, canPrepare, canApprove } = detail ? receiptReviewAccess(detail) : { accounts: [], canPrepare: false, canApprove: false };
  const currencies = [...new Set(accounts.map((account) => account.currency))];
  const missing = useMemo(
    () => (detail && draft ? detail.missing_fields.filter((key) => !draft[key]?.trim()) : []),
    [detail, draft],
  );
  const confirmed = detail?.status === "confirmed";
  // Backend state only: a read is pending when the API says so, never from the status alone.
  const waitingForAi = detail?.read_pending === true;
  const [readStalled, setReadStalled] = useState(false);
  // The read settles on the server; this page asks again until it has, so the
  // same page fills in. Fields the person typed meanwhile keep their text.
  useReceiptReadPoll({
    source,
    receiptId,
    pending: waitingForAi,
    onSettled: (next) => {
      const before = detail ? draftFrom(detail) : null;
      const fresh = draftFrom(next);
      setDetail(next);
      setDraft((current) =>
        current && before
          ? (Object.fromEntries(FIELDS.map((key) => [key, current[key] !== before[key] ? current[key] : fresh[key]])) as Draft)
          : fresh,
      );
      setAmountInvalid(false);
      setUnprepared(false);
      setReadStalled(false);
      reload();
    },
    onStalled: () => setReadStalled(true),
  });

  if (failed) {
    return (
      <p role="alert" className="text-[14px] text-black/70 dark:text-white/70">
        {t("business.review.error", "This receipt isn't available. It may have been removed.")}
      </p>
    );
  }
  if (!detail || !draft) return <LoadingRows rows={4} layout="detail" />;
  if (detail.draft_id && !unprepared) return <ReceiptDossierReview draftId={detail.draft_id} onUnprepared={retainReceipt} receipt={detail} />;
  const frame = (children: React.ReactNode, source: React.ReactNode = <ReceiptSourcePreview detail={detail} />) => (
    <ReceiptReviewFrame
      recordId={receiptId}
      back={confirmed ? "expenses" : "inbox"}
      eyebrow={detail.record_context ? formatBusinessName(detail.record_context.space_name, t("business.overview.title", "My business")) : null}
      title={confirmed ? t("business.review.saved_title", "Saved expense") : t("business.review.title", "Review receipt")}
      badge={<StatusPill status={detail.status} />}
      summary={detail.amount && detail.currency ? <p className="font-display text-[23px] font-medium tabular-nums text-black dark:text-white">{formatMoney(detail.amount, detail.currency, locale)}</p> : null}
      source={source}
    >
      {children}
    </ReceiptReviewFrame>
  );
  if (detail.activity?.state === "saved_unread" || detail.activity?.state === "reading") return frame(<><ReceiptReadingControl /><ReceiptReadNotice status={detail.status} readPending={waitingForAi} enterable={false} preparable={false} /></>);
  const incompleteBridge = unprepared || (detail.status === "review_ready" && !detail.enterable);
  const locked = confirmed || uncertainVersion !== null || !canPrepare || (detail.version === 0 && !detail.enterable);

  const changedFields = (): Partial<ReceiptReviewFields> =>
    Object.fromEntries(
      FIELDS.filter((key) => (detail[key] ?? "") !== draft[key]).map((key) => [key, draft[key] || null]),
    );

  const show = (next: ReceiptDetail) => {
    setDetail(next);
    setDraft(draftFrom(next));
    setAmountInvalid(false);
  };

  const saveProblem = (code: string | undefined, current: Draft) => {
    if (code === "stale_version") {
      return t("business.dossier.stale", "This record changed. Open the current revision and review it before taking another action.");
    }
    const account = accounts.find((item) => item.id === current.account_id);
    if (code === "currency_mismatch" && account) {
      return t("business.review.currency_mismatch", "This account uses {{account}}. Choose an account in {{receipt}} or correct the currency.", {
        account: account.currency,
        receipt: current.currency,
      });
    }
    if (code === "missing_fields") {
      return t("business.review.missing", "Fill in the details marked Needed to save this expense.");
    }
    return t("business.dossier.refused", "This action could not be completed. Check the current record before trying again.");
  };

  const prepare = async () => {
    setBusy("prepare");
    setProblem(null);
    try {
      await source.prepareReceipt(detail.id);
      show(await source.receipt(detail.id));
      setUnprepared(false);
      reload();
    } catch (error) {
      setProblem(
        (error as { code?: string }).code === "whatsapp_receipt_reading_off"
          ? t("business.review.reading_off", "Turn on Read my receipts with AI in your WhatsApp settings, then try again.")
          : t("business.review.prepare_failed", "We couldn't start preparation. Your receipt is saved. Try again."),
      );
    } finally {
      setBusy(null);
    }
  };

  const rebind = async () => {
    setBusy("rebind");
    setProblem(null);
    try {
      await rebindAndPrepare(source, detail.id, show);
      setUnprepared(false);
      reload();
    } catch {
      setProblem(t("business.review.rebind_failed", "We couldn't bind this receipt to your access. Check your permission and try again."));
    } finally {
      setBusy(null);
    }
  };

  const save = async () => {
    if (inFlight.current || busy || uncertainVersion !== null) return;
    inFlight.current = true;
    setBusy("save");
    setProblem(null);
    const submitted = draft;
    try {
      const changes = changedFields();
      const reviewed = await source.saveReview(detail.id, detail.version, changes);
      show(reviewed);
      setUnprepared(false);
      reload();
    } catch (error) {
      const { code, status } = error as { code?: string; status?: number };
      if (moneyProblemFromServer(code, submitted.currency)) setAmountError(code ?? null);
      else if (!status || status >= 500) {
        setUncertainVersion(detail.version);
        setProblem(t("business.dossier.outcome_unknown", "The action's outcome isn't known yet. Check the saved status before taking another action."));
      } else if (status === 401 || status === 403 || status === 404) {
        setFailed(true);
      } else setProblem(saveProblem(code, submitted));
      if (code === "stale_version") {
        const fresh = await source.receipt(detail.id).catch(() => null);
        if (fresh) show(fresh);
      }
    } finally {
      inFlight.current = false;
      setBusy(null);
    }
  };

  const refresh = async () => {
    setBusy("refresh");
    try {
      const next = await source.receipt(detail.id);
      show(next);
      setUnprepared(false);
      if (uncertainVersion !== null && next.version > uncertainVersion) {
        setUncertainVersion(null);
        setProblem(null);
      }
    } catch {
      setFailed(true);
    } finally {
      setBusy(null);
    }
  };

  const field = (key: keyof ReceiptReviewFields, label: string, control: React.ReactNode) => (
    <label className="block">
      <span className="flex items-center justify-between text-[13px] font-medium text-black/60 dark:text-white/60">
        {label}
        {!confirmed && missing.includes(key) ? (
          <span className="text-[12px] font-normal text-[#a8434c] dark:text-[#ec9aa0]">
            {t("business.review.needed", "Needed")}
          </span>
        ) : null}
      </span>
      {control}
    </label>
  );
  const set = (key: keyof ReceiptReviewFields) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setDraft((current) => (current ? { ...current, [key]: event.target.value } : current));

  return (
    <>
      <ReceiptShortcutRegistration actions={{
        ...(!busy && uncertainVersion === null && !Object.keys(changedFields()).length ? receiptNavigationActions(receiptId, records.inbox, (id) => { handTitleFocus(id); openPanel({ kind: "receipt", receiptId: id }); }) : {}),
        ...(!locked && !busy ? { edit: () => document.querySelector<HTMLElement>('[data-testid="receipt-review-fields"] input:not(:disabled), [data-testid="receipt-review-fields"] select:not(:disabled)')?.focus() } : {}),
      }} />
      {frame(
        <>
          {detail.email_original ? <div role="note" data-testid="receipt-email-original" className={`${cardClass} text-[14px] text-black/70 dark:text-white/70`}><p>{t("business.review.email_original", "This is the email itself. Its attachment is the receipt to review.")}</p></div> : null}
          {incompleteBridge ? <div className={`${cardClass} text-[14px] text-black/70 dark:text-white/70`}><p role="alert">{t("business.dossier.missing_draft", "The prepared record isn't available yet. Check the current receipt before continuing.")}</p>{uncertainVersion === null ? <button type="button" disabled={busy !== null} className={`${secondaryButtonClass} mt-3`} onClick={() => void refresh()}>{t("business.dossier.refresh", "Check current record")}</button> : null}</div> : null}
          {detail.status === "needs_attention" ? (
            <div role="alert" data-testid="receipt-attention" className={`${cardClass} text-[14px] text-black/75 dark:text-white/75`}>
              <p className="flex gap-2.5">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-[#d66d75]" aria-hidden="true" />
                <span>{attentionLabel(detail.attention)}</span>
              </p>
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
                    {t("business.review.retry", "Try again with AI")}
                  </button>
                </>
              ) : null}
            </div>
          ) : null}
          <ReceiptReadNotice status={detail.status} readPending={waitingForAi} enterable={detail.enterable && canPrepare && !locked} preparable={detail.preparable && canPrepare} />
          {waitingForAi && readStalled ? (
            <div role="status" data-testid="receipt-read-stalled" className={`${cardClass} text-[14px] text-black/70 dark:text-white/70`}>
              <p>{t("business.review.poll_stopped", "Still reading. Check the current record to see the latest state.")}</p>
              <button type="button" disabled={busy !== null} className={`${secondaryButtonClass} mt-3`} onClick={() => void refresh()}>{t("business.dossier.refresh", "Check current record")}</button>
            </div>
          ) : null}

          <div className={`${cardClass} space-y-4`}>
            {field(
              "merchant",
              t("business.review.merchant", "Merchant"),
              <input className={inputClass} value={draft.merchant} onChange={set("merchant")} disabled={locked} autoComplete="off" />,
            )}
            <div className="grid grid-cols-2 gap-3">
              {field(
                "occurred_on",
                t("business.review.date", "Date"),
                <input type="date" className={inputClass} value={draft.occurred_on} onChange={set("occurred_on")} disabled={locked} />,
              )}
              {field(
                "category_id",
                t("business.review.category", "Category"),
                <select className={inputClass} value={draft.category_id} onChange={set("category_id")} disabled={locked}>
                  <option value="">{categoryLabel(null)}</option>
                  {RECEIPT_CATEGORY_IDS.map((id) => (
                    <option key={id} value={id}>
                      {categoryLabel(id)}
                    </option>
                  ))}
                </select>,
              )}
            </div>
            <div className="grid grid-cols-[minmax(0,1fr)_7.5rem] items-start gap-3">
              {field(
                "amount",
                t("business.review.amount", "Total"),
                <MoneyInput
                  label={t("business.review.amount", "Total")}
                  currency={draft.currency}
                  value={draft.amount || null}
                  onValueChange={({ value, invalid }) => {
                    setDraft((current) => (current ? { ...current, amount: value ?? "" } : current));
                    setAmountInvalid(invalid);
                    setAmountError(null);
                  }}
                  serverError={amountError}
                  description={!confirmed && missing.includes("amount") ? t("business.review.needed", "Needed") : null}
                  disabled={locked}
                  testId="receipt-review-amount"
                />,
              )}
              {field(
                "currency",
                t("business.review.currency", "Currency"),
                <select className={inputClass} value={draft.currency} onChange={set("currency")} disabled={locked}>
                  <option value="">{t("business.review.choose", "Choose")}</option>
                  {currencies.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </select>,
              )}
            </div>
            {field(
              "account_id",
              t("business.review.account", "Paid from"),
              <select className={inputClass} value={draft.account_id} onChange={set("account_id")} disabled={locked}>
                <option value="">{t("business.review.choose_account", "Choose an account")}</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {`${account.nickname ?? account.type} · ${account.currency}`}
                  </option>
                ))}
              </select>,
            )}
          </div>


          {problem ? (
            <p role="alert" className="text-[14px] text-[#a8434c] dark:text-[#ec9aa0]">{problem}</p>
          ) : null}

          {confirmed ? (
            <div className={`${cardClass} flex flex-wrap items-center justify-between gap-3`}>
              <p className="text-[14px] text-black/75 dark:text-white/75">
                {t("business.review.saved_body", "Saved as one expense of {{amount}}.", { amount: formatMoney(detail.amount, detail.currency, locale) })}
              </p>
              <button type="button" className={secondaryButtonClass} onClick={() => openPanel({ kind: "expenses" })}>
                {t("business.review.view_expenses", "View expenses")}
              </button>
            </div>
          ) : canPrepare ? (
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                className={primaryButtonClass}
                disabled={busy !== null || missing.length > 0 || amountInvalid || waitingForAi || locked || !Object.keys(changedFields()).length}
                onClick={() => void save()}
              >
                {busy === "save" ? t("business.review.confirming", "Saving…") : t("business.dossier.save", "Save review details")}
              </button>
              {missing.length > 0 ? (
                <span className="text-[13px] text-black/55 dark:text-white/55">
                  {t("business.review.missing", "Fill in the details marked Needed to save this expense.")}
                </span>
              ) : null}
              {uncertainVersion !== null ? <button type="button" className={secondaryButtonClass} disabled={busy !== null} onClick={() => void refresh()}>{t("business.dossier.refresh", "Check current record")}</button> : null}
            </div>
          ) : <p className="text-[13px] text-black/65 dark:text-white/65">{t("business.dossier.read_only", "Your permission allows viewing this record.")}</p>}
        </>,
        <>
          <ReceiptSourcePreview detail={detail} />
          {detail.evidence ? (
            <details className={cardClass}>
              <summary className="cursor-pointer text-[14px] font-medium text-black/70 dark:text-white/70">
                {t("business.review.evidence", "What the receipt says")}
              </summary>
              <dl className="mt-3 space-y-1.5 text-[13px] text-black/65 dark:text-white/65">
                {detail.evidence.merchant ? <div className="flex justify-between gap-3"><dt>{t("business.review.merchant", "Merchant")}</dt><dd className="text-right">{detail.evidence.merchant}</dd></div> : null}
                {detail.evidence.occurred_on ? <div className="flex justify-between gap-3"><dt>{t("business.review.date", "Date")}</dt><dd>{formatDay(detail.evidence.occurred_on, locale)}</dd></div> : null}
                {detail.evidence.lines.map((line, index) => (
                  <div key={index} className="flex justify-between gap-3"><dt className="truncate">{line.description}</dt><dd className="tabular-nums">{formatMoney(line.amount, detail.evidence?.currency ?? null, locale)}</dd></div>
                ))}
                {detail.evidence.tax ? <div className="flex justify-between gap-3"><dt>{t("business.review.tax", "Tax")}</dt><dd className="tabular-nums">{formatMoney(detail.evidence.tax, detail.evidence.currency, locale)}</dd></div> : null}
                {detail.evidence.total ? <div className="flex justify-between gap-3 font-medium text-black dark:text-white"><dt>{t("business.review.amount", "Total")}</dt><dd className="tabular-nums">{formatMoney(detail.evidence.total, detail.evidence.currency, locale)}</dd></div> : null}
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
