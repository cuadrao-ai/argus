"use client";

import { useBusiness } from "../BusinessWorkspace";
import type { RecordRow } from "./transacciones-model";
import { previewRecordMetadata } from "./records-results-preview";
import { useTransaccionesWords } from "./transacciones-words";
import { Unknown } from "./transacciones-parts";
import palette from "./records-overview-preview.module.css";
import styles from "./transacciones-cells.module.css";

export default function RecordWorkflowBadge({ row }: { row: RecordRow }) {
  const { chosen } = useBusiness();
  const { t } = useTransaccionesWords();
  if (row.report?.stage === "needs_fiscal_data") return <span data-record-workflow="fiscal" className={`${styles.workflow} ${palette.review}`}>{t(missingKey(row.report))}</span>;
  const workflow = row.report?.stage ? ({ needs_review: "review", awaiting_approval: "approval", ready_for_export: "ready" } as const)[row.report.stage as "needs_review" | "awaiting_approval" | "ready_for_export"] : undefined;
  const metadata = workflow ? { workflow } : row.report ? null : previewRecordMetadata(row, chosen?.space_id ?? null);
  if (!metadata) return <Unknown meaning={t("business.transactions.layout.workflow.unknown")} />;
  const tone = metadata.workflow === "ready" ? "export" : metadata.workflow;
  return <span data-record-workflow={metadata.workflow} className={`${styles.workflow} ${palette[tone]}`}>{t(`business.transactions.layout.workflow.${metadata.workflow}`)}</span>;
}

const MISSING = new Set(["expense_type_missing", "rnc_missing", "rnc_invalid", "ncf_invalid", "ncf_missing", "date_missing", "payment_method_missing"]);

function missingKey(report: { export_missing?: string | null; export_missing_several?: boolean }): string {
  const code = report.export_missing_several ? "several" : MISSING.has(report.export_missing ?? "") ? report.export_missing : "detail_missing";
  return `business.transactions.layout.workflow.missing.${code}`;
}
