"use client";

import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/Tooltip";
import { useBusiness } from "../BusinessWorkspace";
import type { RecordRow } from "./transacciones-model";
import { previewRecordMetadata, type PreviewWorkflow } from "./records-results-preview";
import { useTransaccionesWords } from "./transacciones-words";
import { Unknown } from "./transacciones-parts";
import palette from "./records-overview-preview.module.css";
import styles from "./transacciones-cells.module.css";

const WORKFLOW_OF_STAGE = { needs_review: "review", needs_fiscal_data: "fiscal", ready_for_export: "ready", exported: "exported" } as const;
const TONE: Record<PreviewWorkflow, string> = { review: palette.review, fiscal: palette.fiscal, ready: palette.export, exported: palette.exported };

export default function RecordWorkflowBadge({ row }: { row: RecordRow }) {
  const { chosen } = useBusiness();
  const { t } = useTransaccionesWords();
  const { i18n } = useTranslation();
  const metadata = row.report ? row.report.stage ? { workflow: WORKFLOW_OF_STAGE[row.report.stage], missing: row.report } : null : previewRecordMetadata(row, chosen?.space_id ?? null);
  if (!metadata) return <Unknown meaning={t("business.transactions.layout.workflow.unknown")} />;
  const label = metadata.workflow === "fiscal" ? t(missingKey(metadata.missing ?? {}, (key) => i18n.exists(key))) : t(`business.transactions.layout.workflow.${metadata.workflow}`);
  return <Tooltip content={label} side="top"><span data-record-workflow={metadata.workflow} className={`${styles.workflow} ${styles.stage} ${TONE[metadata.workflow]}`}>{label}</span></Tooltip>;
}

/** The server names what holds the row; the locale owns its words. A word the locale lacks reads as a detail missing, never a raw code. */
function missingKey(report: { export_missing?: string | null; export_missing_several?: boolean }, known: (key: string) => boolean): string {
  const path = "business.transactions.layout.workflow.missing";
  if (report.export_missing_several) return `${path}.several`;
  const key = `${path}.${report.export_missing}`;
  return report.export_missing && report.export_missing !== "several" && known(key) ? key : `${path}.detail_missing`;
}
