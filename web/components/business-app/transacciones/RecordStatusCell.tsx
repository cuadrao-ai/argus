"use client";

import { cloneElement, createContext, useContext, type HTMLAttributes, type ReactElement } from "react";
import { Tooltip } from "@/components/ui/Tooltip";
import { useBusiness } from "../BusinessWorkspace";
import { StatusChip } from "../foundation/StatusChip";
import { useMissingWords } from "./RecordMissingReason";
import { previewRecordMetadata } from "./records-results-preview";
import type { RecordRow } from "./transacciones-model";
import { Unknown } from "./transacciones-parts";
import { useTransaccionesWords } from "./transacciones-words";

const StatusControlContext = createContext(false);

/** Readiness and reason order belong to the server; this cell only renders them. */
function useRecordStatus(row: RecordRow) {
  const { chosen } = useBusiness();
  const { t } = useTransaccionesWords();
  const record = row.report ?? previewRecordMetadata(row, chosen?.space_id ?? null);
  const words = useMissingWords(record?.ready === false ? record.missing : []);
  return { record, words, t };
}

/** A row control owns the status description without a nested tab stop. */
export function RecordStatusControl({ row, children }: { row: RecordRow; children: ReactElement<HTMLAttributes<HTMLElement>> }) {
  const { words } = useRecordStatus(row);
  const description = words.length ? words.join(" · ") : undefined;
  return <StatusControlContext.Provider value={true}>
    {cloneElement(children, { "aria-description": description })}
  </StatusControlContext.Provider>;
}

export default function RecordStatusCell({ row }: { row: RecordRow }) {
  const { record, words, t } = useRecordStatus(row);
  const withinControl = useContext(StatusControlContext);
  if (record?.ready === undefined) return <Unknown meaning={t("business.transactions.layout.workflow.unknown")} />;
  if (record.ready || !words.length) return null;
  const chip = <StatusChip data-record-status="missing" tone="warning">{t("business.transactions.layout.workflow.missing_count_placeholder", { count: words.length })}</StatusChip>;
  return <Tooltip content={words.join(" · ")} side="top"><span tabIndex={withinControl ? undefined : 0} className="rounded-mark">{chip}</span></Tooltip>;
}
