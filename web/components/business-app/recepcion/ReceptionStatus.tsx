"use client";

import { useTranslation } from "react-i18next";
import { useReceiptStateWord } from "../receipt-state-word";
import { useEmailWords } from "../BusinessEmailDeliveries";
import { receptionMatches, type ReceptionRow } from "./reception-model";
import tagStyles from "../transacciones/transacciones-cells.module.css";
import tagPalette from "../transacciones/records-overview-preview.module.css";
import styles from "./reception.module.css";

export default function ReceptionStatus({ row, full = false }: { row: ReceptionRow; full?: boolean }) {
  const { t } = useTranslation();
  const stateWord = useReceiptStateWord();
  const emailWords = useEmailWords();
  const attention = receptionMatches(row, "attention");
  const state = row.kind === "receipt" ? stateWord(row.receipt) : row.kind === "message" ? t("business.reception_preview.note_received") : row.kind === "note" ? t("business.reception_preview.note_state") : row.email.standing === "reading" ? row.email.delivery.waiting ? t("business.email.waiting_label") : t("business.inbox.row_reading") : emailWords.noReceipt(row.email.delivery);
  const tone = row.kind === "receipt" && row.receipt.status === "confirmed" ? "export" : attention ? "review" : receptionMatches(row, "processing") ? "approval" : null;
  return <span className={full ? styles.detailStatus : styles.state} title={state}>
    <span data-testid="status-pill" data-reception-status={tone ?? "neutral"} className={`${tagStyles.workflow} ${tone ? tagPalette[tone] : styles.neutralTag}`}>{attention ? t("business.status.pill_attention") : state}</span>
    {attention ? <span className={full ? styles.detailReason : styles.stateReason}>{state}</span> : row.kind === "message" ? <span className={styles.stateReason}>{t("business.reception_preview.preview_label")}</span> : null}
  </span>;
}
