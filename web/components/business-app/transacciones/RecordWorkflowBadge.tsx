"use client";

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
  const metadata = row.report ? row.report.stage ? { workflow: WORKFLOW_OF_STAGE[row.report.stage], missing: row.report } : null : previewRecordMetadata(row, chosen?.space_id ?? null);
  if (!metadata) return <Unknown meaning={t("business.transactions.layout.workflow.unknown")} />;
  const label = metadata.workflow === "fiscal" ? t(missingKey(metadata.missing ?? {})) : t(`business.transactions.layout.workflow.${metadata.workflow}`);
  return <span data-record-workflow={metadata.workflow} className={`${styles.workflow} ${TONE[metadata.workflow]}`}>{label}</span>;
}

const MISSING = new Set(["expense_type_missing", "rnc_missing", "rnc_invalid", "ncf_invalid", "ncf_missing", "date_missing", "payment_method_missing"]);

function missingKey(report: { export_missing?: string | null; export_missing_several?: boolean }): string {
  const code = report.export_missing_several ? "several" : MISSING.has(report.export_missing ?? "") ? report.export_missing : "detail_missing";
  return `business.transactions.layout.workflow.missing.${code}`;
}
