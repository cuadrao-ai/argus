"use client";

import { useTranslation } from "react-i18next";
import { useEmailWords } from "../BusinessEmailDeliveries";
import ReceptionCutText from "./ReceptionCutText";
import { BANDEJA_REASON_KEY, receptionTag } from "./reception-status";
import type { ReceptionRow } from "./reception-model";
import tagStyles from "../transacciones/transacciones-cells.module.css";
import styles from "./reception.module.css";

const TONE = { reading: styles.tagReading, attention: styles.tagAttention, approved: styles.tagApproved, listo: styles.tagNeutral, dismissed: styles.tagNeutral } as const;

/** Todos shows the soft tag. Necesitan atención is already the state, so it shows only the reason, as plain text. */
export default function ReceptionStatus({ row, reasonOnly }: { row: ReceptionRow; reasonOnly: boolean }) {
  const { t } = useTranslation();
  const emailWords = useEmailWords();
  const state = receptionTag(row);
  const label = {
    reading: t(row.kind === "email" && row.email.delivery.waiting ? "business.email.waiting_label" : "business.inbox.row_reading"),
    attention: t("business.status.pill_attention"),
    listo: t("business.reception_preview.placeholder.tag_listo"),
    approved: t("business.status.pill_approved"),
    dismissed: t("business.status.dismissed"),
  }[state.tag];
  if (!reasonOnly) return <span className={styles.state}><span data-testid="status-pill" data-tag={state.tag} className={`${tagStyles.workflow} ${TONE[state.tag]}`}>{label}</span></span>;
  const reason = state.tag !== "attention" ? null : row.kind === "email" ? emailWords.noReceipt(row.email.delivery) : state.reason && BANDEJA_REASON_KEY[state.reason] ? t(BANDEJA_REASON_KEY[state.reason]) : null;
  return <span className={styles.state}><ReceptionCutText text={reason ?? label} className={styles.stateReason} data-testid={reason ? "reception-reason" : undefined} /></span>;
}
