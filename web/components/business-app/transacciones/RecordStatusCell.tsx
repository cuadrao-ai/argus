"use client";

import { Tooltip } from "@/components/ui/Tooltip";
import { useBusiness } from "../BusinessWorkspace";
import { StatusChip } from "../foundation/StatusChip";
import { useMissingWords } from "./RecordMissingReason";
import { previewRecordMetadata } from "./records-results-preview";
import type { RecordRow } from "./transacciones-model";
import { Unknown } from "./transacciones-parts";
import { useTransaccionesWords } from "./transacciones-words";

/** Readiness and reason order belong to the server; this cell only renders them. */
export default function RecordStatusCell({ row }: { row: RecordRow }) {
  const { chosen } = useBusiness();
  const { t } = useTransaccionesWords();
  const record = row.report ?? previewRecordMetadata(row, chosen?.space_id ?? null);
  const words = useMissingWords(record?.ready === false ? record.missing : []);
  if (record?.ready === undefined) return <Unknown meaning={t("business.transactions.layout.workflow.unknown")} />;
  if (record.ready || !words.length) return null;
  const chip = <StatusChip data-record-status="missing" tone="warning">{words.length === 1 ? words[0] : t("business.transactions.layout.workflow.missing_count_placeholder", { count: words.length })}</StatusChip>;
  return words.length === 1 ? chip : <Tooltip content={words.join(" · ")} side="top"><span tabIndex={0} className="rounded-mark">{chip}</span></Tooltip>;
}
