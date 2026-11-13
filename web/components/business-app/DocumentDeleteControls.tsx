"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { FileText, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { referenceCode } from "@/lib/failure-screen";
import { randomId } from "@/lib/random-id";
import type { ReceiptSummary } from "@/lib/business-api";
import { useBusiness, type BusinessPanelState } from "./BusinessWorkspace";
import { formatDay, formatMoney, UNKNOWN_VALUE } from "./business-format";
import { resolveLanguage } from "@/lib/language-features";
import { secondaryButtonClass, quietButtonClass } from "./business-ui";
import { CONFIRM_ACTION, FOCUS_RING } from "./foundation/presentation";
import { showToast } from "./foundation/toasts";

export type DeleteDocumentTarget = {
  id: string;
  name: string;
  merchant: string | null;
  date: string | null;
  amount: string | null;
  currency: string | null;
  filename: string | null;
  state: string;
  receipt?: ReceiptSummary;
};

export function receiptDeleteTarget(receipt: ReceiptSummary, state: string, unnamed: string): DeleteDocumentTarget {
  return { id: receipt.id, name: receipt.merchant || receipt.filename || unnamed, merchant: receipt.merchant, date: receipt.occurred_on, amount: receipt.amount, currency: receipt.currency, filename: receipt.filename, state, receipt };
}

function DocumentThumbnail({ receipt }: { receipt?: ReceiptSummary }) {
  const { source } = useBusiness();
  const [image, setImage] = useState<string | null>(null);
  useEffect(() => {
    if (!receipt?.media_type.startsWith("image/")) return;
    let live = true;
    void source.receiptSource(receipt.id)
      .then(blob => new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(blob);
      }))
      .then(url => { if (live) setImage(url); })
      .catch(() => undefined);
    return () => { live = false; };
  }, [receipt?.id, receipt?.media_type, source]);
  return <div className="flex h-20 w-16 shrink-0 items-center justify-center overflow-hidden rounded-item border border-black/10 bg-black/[0.03] dark:border-white/10 dark:bg-white/5">
    {image ? <Image unoptimized src={image} alt="" width={64} height={80} className="h-full w-full object-contain" /> : <FileText size={24} aria-hidden="true" />}
  </div>;
}

function DeleteFacts({ target }: { target: DeleteDocumentTarget }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const facts = {
    counterparty: target.merchant || UNKNOWN_VALUE,
    date: target.date ? formatDay(target.date, locale) : UNKNOWN_VALUE,
    total: formatMoney(target.amount, target.currency, locale) || UNKNOWN_VALUE,
    file: target.filename || UNKNOWN_VALUE,
    state: target.state,
  };
  return <div className="mt-4 flex items-start gap-3" data-testid="document-delete-facts">
    <DocumentThumbnail receipt={target.receipt} />
    <dl className="min-w-0 flex-1 space-y-2 text-[14px]">
      {Object.entries(facts).map(([key, value]) => <div key={key} className="flex flex-wrap justify-between gap-x-3"><dt className="text-[#56635e] dark:text-white/70">{t(`business.document_delete.fields.${key}`)}</dt><dd className={`min-w-0 break-words text-right ${key === "total" ? "cuadrao-amount tabular-nums" : ""}`}>{value}</dd></div>)}
    </dl>
  </div>;
}

export function useDocumentDelete(target: DeleteDocumentTarget | null, { initialPreview = false, onClose, onView }: { initialPreview?: boolean; onClose?: () => void; onView?: () => void } = {}) {
  const { t } = useTranslation();
  const { source, reload, openPanel } = useBusiness();
  const [mode, setMode] = useState<"dialog" | "preview" | null>(initialPreview ? "preview" : null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const request = useRef<{ id: string; key: string } | null>(null);
  const inFlight = useRef(false);
  const close = () => { if (!inFlight.current) { setMode(null); setFailure(null); onClose?.(); } };
  const confirm = async () => {
    if (!target || !source.deleteDocument || inFlight.current) return;
    const command = request.current?.id === target.id ? request.current : { id: target.id, key: randomId() };
    request.current = command;
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    try {
      await source.deleteDocument(command.id, command.key);
      request.current = null;
      setMode(null);
      onClose?.();
      reload();
      openPanel({ kind: "inbox" });
    } catch (error) {
      setFailure(referenceCode(error));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };
  const error = failure ? <>{t("business.document_delete.failed")} <ReferenceCode reference={failure} /></> : null;
  const button = <button type="button" onClick={() => void confirm()} disabled={busy} style={{ backgroundColor: CONFIRM_ACTION }} className={`min-h-11 rounded-full px-4 text-[16px] font-medium text-white disabled:opacity-50 ${FOCUS_RING}`}>{t("business.document_delete.delete")}</button>;
  const dialog = target && mode === "dialog" ? <ConfirmDialog isOpen title={t("business.document_delete.title")} description={t("business.document_delete.description")} confirmLabel={t("business.document_delete.delete")} cancelLabel={t("common.cancel")} isBusy={busy} onCancel={close} onConfirm={() => void confirm()} error={error} leadingAction={onView ? <button type="button" className={quietButtonClass} disabled={busy} onClick={() => { setMode(null); onView(); }}>{t("business.document_delete.view_document")}</button> : null}><DeleteFacts target={target} /></ConfirmDialog> : null;
  const confirmBar = target && mode === "preview" ? <div data-testid="document-delete-bar" className="flex flex-wrap items-center gap-3">
    <div className="min-w-0 flex-1 text-[14px]"><p className="font-medium">{t("business.document_delete.title")}</p><p className="text-[#56635e] dark:text-white/70">{t("business.document_delete.description")}</p>{error ? <p role="alert" className="text-[#9e2f39] dark:text-[#ec9aa0]">{error}</p> : null}</div>
    <button type="button" className={secondaryButtonClass} disabled={busy} onClick={close}>{t("common.cancel")}</button>{button}
  </div> : null;
  return { busy, ask: () => { setFailure(null); setMode("dialog"); }, dialog, confirmBar };
}

export function DeleteDocumentMenuItem({ disabled, onClick }: { disabled?: boolean; onClick: () => void }) {
  const { t } = useTranslation();
  return <button type="button" data-testid="delete-document-menu" onClick={onClick} disabled={disabled} className={`flex min-h-11 w-full items-center gap-2 rounded-item px-3 text-left text-[14px] text-[#9e2f39] hover:bg-[#f6dfe0]/50 disabled:opacity-50 dark:text-[#ec9aa0] ${FOCUS_RING}`}><Trash2 size={16} aria-hidden="true" />{t("business.document_delete.menu")}</button>;
}

export function RestoreDocumentButton({ id, target, onRestored }: { id: string; target: BusinessPanelState; onRestored?: () => void }) {
  const { t } = useTranslation();
  const { source, reload, openPanel, chosen } = useBusiness();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const key = useRef<string | null>(null);
  const inFlight = useRef(false);
  const restore = async () => {
    if (!source.restoreDocument || inFlight.current) return;
    inFlight.current = true;
    key.current ??= randomId();
    setBusy(true);
    setFailure(null);
    try {
      await source.restoreDocument(id, key.current);
      key.current = null;
      reload();
      onRestored?.();
      showToast({ kind: "success", text: t("business.document_delete.restored"), action: { label: t("business.document_delete.view"), run: () => openPanel(target) } });
    } catch (error) {
      setFailure(referenceCode(error));
    } finally { inFlight.current = false; setBusy(false); }
  };
  if (!chosen?.capabilities.includes("approve") || !source.restoreDocument) return null;
  return <span className="inline-flex flex-col items-start"><button type="button" className={secondaryButtonClass} disabled={busy} onClick={() => void restore()}>{t("business.document_delete.restore")}</button>{failure ? <span role="alert" className="text-[14px] text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.document_delete.restore_failed")} <ReferenceCode reference={failure} /></span> : null}</span>;
}
