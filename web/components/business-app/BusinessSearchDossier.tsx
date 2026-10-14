"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessAccount, BusinessCapture, BusinessExpense, ReceiptDetail, ReceiptSummary } from "@/lib/business-api";
import { factsRevision, type BusinessDossier } from "@/lib/business-dossier";
import type { BusinessDataSource } from "./business-data";
import ReceiptMessages from "./ReceiptMessages";
import ReceiptRecordFacts from "./ReceiptRecordFacts";
import ReceiptSourcePreview from "./ReceiptSourcePreview";
import { formatDay, formatMoney, formatTimestamp } from "./business-format";
import { cardClass, LoadingRows, StatusPill, useCategoryLabel } from "./business-ui";

export type BusinessSearchRecord =
  | { kind: "receipt"; receipt: ReceiptSummary }
  | { kind: "expense"; expense: BusinessExpense }
  | { kind: "note"; note: BusinessCapture };

/**
 * The record behind a search hit, beside the results. What the hit already
 * carries renders at once; the saved receipt or draft fills in when it loads.
 */
export default function BusinessSearchDossier({ record, source, accounts }: { record: BusinessSearchRecord; source: BusinessDataSource; accounts: readonly BusinessAccount[] }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  if (record.kind === "note") return <NotePreview note={record.note} source={source} accounts={accounts} />;
  const summary = record.kind === "receipt" ? record.receipt : record.expense;
  const receiptId = record.kind === "receipt" ? record.receipt.id : record.expense.receipt_id;
  return <section aria-label={t("business.search.region", "Business records")} className="space-y-5">
    <h2 className="font-display text-2xl font-medium">{summary.merchant ?? (record.kind === "receipt" ? record.receipt.filename : null) ?? t(record.kind === "receipt" ? "business.receipt.untitled" : "business.expenses.no_merchant", record.kind === "receipt" ? "Receipt" : "Expense")}</h2>
    {record.kind === "receipt" ? <StatusPill status={record.receipt.status} /> : null}
    {summary.amount ? <p className="text-3xl font-medium tabular-nums">{formatMoney(summary.amount, summary.currency, locale)}</p> : null}
    <Field label={t("business.review.date", "Date")}>{summary.occurred_on ? formatDay(summary.occurred_on, locale) : t("business.dossier.unknown", "Unknown")}</Field>
    <Field label={t("business.review.category", "Category")}><CategoryName id={summary.category_id} /></Field>
    {receiptId ? <ReceiptPreview receiptId={receiptId} source={source} /> : <p className="text-sm text-black/55 dark:text-white/55">{t("business.dossier.no_attachment", "No receipt file is attached to this record.")}</p>}
  </section>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="text-sm"><dt className="text-black/45 dark:text-white/45">{label}</dt><dd>{children}</dd></div>;
}

function CategoryName({ id }: { id: string | null }) {
  const category = useCategoryLabel();
  return <>{category(id)}</>;
}

function ReceiptPreview({ receiptId, source }: { receiptId: string; source: BusinessDataSource }) {
  const { t, i18n } = useTranslation();
  const [detail, setDetail] = useState<ReceiptDetail | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    setDetail(null);
    setFailed(false);
    source.receipt(receiptId).then((value) => active && setDetail(value)).catch(() => active && setFailed(true));
    return () => { active = false; };
  }, [receiptId, source]);
  if (failed) return <p role="alert" className="text-sm">{t("business.review.error", "This receipt isn't available. It may have been removed.")}</p>;
  if (!detail) return <LoadingRows rows={3} />;
  return <>
    <Field label={t("business.review.source", "Original receipt")}><span className="break-all">{detail.filename ?? detail.media_type}</span></Field>
    {detail.evidence?.lines.length ? <div className={cardClass}><h3 className="mb-3 text-sm font-medium">{t("business.review.evidence", "What the receipt says")}</h3><ul className="space-y-2 text-sm">{detail.evidence.lines.map((line, index) => <li key={index} className="flex justify-between gap-3"><span>{line.description}</span><span>{formatMoney(line.amount, detail.evidence?.currency ?? null, i18n.resolvedLanguage ?? "en")}</span></li>)}</ul></div> : null}
    <ReceiptSourcePreview detail={detail} />
  </>;
}

function NotePreview({ note, source, accounts }: { note: BusinessCapture; source: BusinessDataSource; accounts: readonly BusinessAccount[] }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const [dossier, setDossier] = useState<BusinessDossier | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    setDossier(null);
    setFailed(false);
    source.dossier(note.draft_id).then((value) => active && setDossier(value)).catch(() => active && setFailed(true));
    return () => { active = false; };
  }, [note.draft_id, source]);
  return <section aria-label={t("business.capture.saved_note", "Saved original note")} className="space-y-5">
    <div>
      <p className="mb-2 text-xs uppercase tracking-wide text-black/45 dark:text-white/45">{t("business.capture.saved_note", "Saved original note")} · {formatTimestamp(note.received_at, locale)}</p>
      <blockquote className="whitespace-pre-wrap break-words border-l-2 border-black/10 pl-3 text-[15px] leading-relaxed text-black/80 dark:border-white/15 dark:text-white/80">{note.text}</blockquote>
    </div>
    <p className="text-sm text-black/55 dark:text-white/55">{t("business.dossier.revision", "Revision {{version}}", { version: dossier ? factsRevision(dossier) : note.revision })} · {t(`business.dossier.state.${note.review_state}`, note.review_state)}</p>
    {failed ? <p role="alert" className="text-sm">{t("business.search.record_unavailable", "This record isn't available.")}</p> : dossier ? <>
      <ReceiptRecordFacts dossier={dossier} accounts={[...accounts]} />
      <ReceiptMessages sources={dossier.sources} />
    </> : <LoadingRows rows={4} />}
  </section>;
}
