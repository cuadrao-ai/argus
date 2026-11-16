"use client";

import { useBusiness } from "../BusinessWorkspace";
import type { RecordRow } from "./transacciones-model";
import { previewRecordMetadata } from "./records-results-preview";
import { useTransaccionesWords } from "./transacciones-words";
import { Unknown } from "./transacciones-parts";
import { StatusChip } from "../foundation/StatusChip";

/** The server owns readiness; legacy stage and missing reasons never choose the chip. */
export default function RecordWorkflowBadge({ row }: { row: RecordRow }) {
  const { chosen } = useBusiness();
  const { t } = useTransaccionesWords();
  const ready = (row.report ?? previewRecordMetadata(row, chosen?.space_id ?? null))?.ready;
  if (ready === undefined) return <Unknown meaning={t("business.transactions.layout.workflow.unknown")} />;
  return <StatusChip data-record-workflow={ready ? "ready" : "not_ready"} tone={ready ? "ready" : "warning"}>{t(`business.transactions.layout.workflow.${ready ? "ready" : "not_ready"}`)}</StatusChip>;
}
