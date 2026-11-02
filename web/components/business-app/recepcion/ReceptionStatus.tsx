"use client";

import { useTranslation } from "react-i18next";
import { useEmailWords } from "../BusinessEmailDeliveries";
import { BANDEJA_REASON_KEY, receptionTag } from "./reception-status";
import type { ReceptionRow } from "./reception-model";
import tagStyles from "../transacciones/transacciones-cells.module.css";
import tagPalette from "../transacciones/records-overview-preview.module.css";
import styles from "./reception.module.css";

const TONE = { reading: "approval", attention: "review", approved: "export", listo: null, dismissed: null } as const;

export default function ReceptionStatus({ row, full = false }: { row: ReceptionRow; full?: boolean }) {
  const { t } = useTranslation();
  const emailWords = useEmailWords();
  const state = receptionTag(row);
  const reason = state.tag !== "attention" ? null : row.kind === "email" ? emailWords.noReceipt(row.email.delivery) : state.reason && BANDEJA_REASON_KEY[state.reason] ? t(BANDEJA_REASON_KEY[state.reason]) : null;
  const label = {
    reading: t(row.kind === "email" && row.email.delivery.waiting ? "business.email.waiting_label" : "business.inbox.row_reading"),
    attention: t("business.status.pill_attention"),
    listo: t("business.reception_preview.placeholder.tag_listo"),
    approved: t("business.status.pill_approved"),
    dismissed: t("business.status.dismissed"),
  }[state.tag];
  const tone = TONE[state.tag];
  return <span className={full ? styles.detailStatus : styles.state} title={reason ?? label}>
    <span data-testid="status-pill" data-reception-status={tone ?? "neutral"} data-tag={state.tag} className={`${tagStyles.workflow} ${tone ? tagPalette[tone] : styles.neutralTag}`}>{label}</span>
    {reason ? <span className={full ? styles.detailReason : styles.stateReason} data-testid="reception-reason">{reason}</span> : null}
  </span>;
}
