"use client";

import { useBusiness } from "../BusinessWorkspace";
import type { RecordRow } from "./transacciones-model";
import { previewRecordMetadata } from "./records-results-preview";
import { useTransaccionesWords } from "./transacciones-words";
import { Unknown } from "./transacciones-parts";
import { RECORDS_COLUMN_LAYOUT } from "./records-view-preferences";
import palette from "./records-overview-preview.module.css";
import styles from "./transacciones-cells.module.css";

/** The server owns readiness; legacy stage and missing reasons never choose the chip. */
export default function RecordWorkflowBadge({ row }: { row: RecordRow }) {
  const { chosen } = useBusiness();
  const { t } = useTransaccionesWords();
  const ready = (row.report ?? previewRecordMetadata(row, chosen?.space_id ?? null))?.ready;
  if (ready === undefined) return <Unknown meaning={t("business.transactions.layout.workflow.unknown")} />;
  return <span data-record-workflow={ready ? "ready" : "not_ready"} style={{ width: RECORDS_COLUMN_LAYOUT.stage.chipWidth }} className={`${styles.workflow} ${styles.stage} ${ready ? palette.export : palette.fiscal}`}>{t(`business.transactions.layout.workflow.${ready ? "ready" : "not_ready"}`)}</span>;
}
