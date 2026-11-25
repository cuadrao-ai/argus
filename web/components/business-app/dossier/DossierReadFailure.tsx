"use client";

import { FileX2, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { ReceiptAttention } from "@/lib/business-api";
import { dangerButtonClass } from "../business-ui";
import { useRecordTray } from "../record-tray";
import styles from "./dossier.module.css";

const explanations: Partial<Record<ReceiptAttention, string>> = {
  not_a_receipt: "business.file_read.not_a_receipt_body",
  outcome_unknown: "business.file_read.outcome_unknown_body",
  read_deadline_passed: "business.file_read.read_deadline_passed_body",
  unreadable: "business.file_read.unreadable_body",
};

export default function DossierReadFailure({ reason, retry, problem, children }: { reason: ReceiptAttention; retry: boolean; problem: string | null; children?: ReactNode }) {
  const { t } = useTranslation();
  const title = reason === "not_a_receipt" || reason === "unreadable" ? `business.file_read.${reason}_title` : `business.attention_short.${reason}`;
  const body = explanations[reason];
  return <section role="alert" aria-label={t("business.bandeja.label.cant_read")} className={`rounded-surface ${styles.failedRead}`} data-testid="receipt-attention">
    <span className={`rounded-item ${styles.failedIcon}`}><FileX2 size={22} aria-hidden="true" /></span>
    <h3>{t(title)}</h3>
    {body ? <p>{t(body)}</p> : null}
    {retry ? <p className={styles.retryConsent}>{t("business.review.retry_consent")}</p> : null}
    {children}
    {problem ? <p>{problem}</p> : null}
  </section>;
}

export function ReadStateDelete({ onClick, disabled }: { onClick: () => void; disabled: boolean }) {
  const { t } = useTranslation();
  const tray = useRecordTray();
  const narrow = tray ? tray.narrow === true : true;
  const label = t("business.document_delete.menu");
  return <button type="button" title={narrow ? label : undefined} aria-label={label} disabled={disabled} onClick={onClick}
    className={`${dangerButtonClass} ${narrow ? "w-11 px-0" : ""}`}>
    <Trash2 size={16} aria-hidden="true" />{narrow ? null : label}
  </button>;
}
