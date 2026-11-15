"use client";

import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/Tooltip";
import { useBusiness } from "../BusinessWorkspace";
import type { RecordRow } from "./transacciones-model";
import { previewRecordMetadata } from "./records-results-preview";
import { useTransaccionesWords } from "./transacciones-words";
import { Unknown } from "./transacciones-parts";
import palette from "./records-overview-preview.module.css";
import styles from "./transacciones-cells.module.css";

// MOCK (#2169), DO NOT MERGE. The pill is one of four fixed words. The reason is plain text on the same line.
const WORKFLOW = "business.transactions.layout.workflow";
const MISSING = `${WORKFLOW}.missing`;
const PLACEHOLDER = `${WORKFLOW}.placeholder`;
export type EstadoStatus = "ready" | "fix" | "excluded" | "review";
/** `reasons` are locale paths, first fix first. `more` says the server named only the first of several. `note` is a reason that does not hold the row. */
export type RecordEstado = { status: EstadoStatus; reasons: readonly string[]; more?: boolean; note?: string };
const TONE: Record<EstadoStatus, string> = { ready: palette.export, fix: palette.fiscal, excluded: palette.exported, review: palette.review };

/**
 * The mock reads the proposed status from the fields the server sends today. The build moves this to the server:
 * `exported` has no writer and reads by its current verdict, and a row no 606 or 607 line carries is `excluded`.
 */
export function recordEstado(row: RecordRow, businessId: string | null): RecordEstado | null {
  const report = row.report;
  if (!report) {
    const sample = previewRecordMetadata(row, businessId);
    if (!sample) return null;
    if (sample.excluded) return { status: "excluded", reasons: [sample.excluded] };
    if (sample.workflow === "review") return { status: "review", reasons: [`${PLACEHOLDER}.review_hint`] };
    if (sample.workflow === "fiscal") return { status: "fix", reasons: (sample.missing?.all ?? [sample.missing?.export_missing ?? "detail_missing"]).map((word) => `${MISSING}.${word}`), more: !sample.missing?.all && sample.missing?.export_missing_several };
    return { status: "ready", reasons: [], note: sample.note };
  }
  if (!report.stage) return null;
  if (report.stage === "needs_review") return { status: "review", reasons: [`${PLACEHOLDER}.review_hint`] };
  if (report.stage === "needs_fiscal_data" || report.fiscal_data === "missing") return { status: "fix", reasons: [`${MISSING}.${report.export_missing ?? "detail_missing"}`], more: report.export_missing_several };
  if (report.fiscal_data === null && !report.export_line) {
    return { status: "excluded", reasons: report.personal ? ["business.marks.personal_chip"] : report.fiscal_classification === "no_comprobante" ? ["business.marks.sin_comprobante_chip"] : [] };
  }
  return { status: "ready", reasons: [] };
}

export default function RecordWorkflowBadge({ row }: { row: RecordRow }) {
  const { chosen } = useBusiness();
  const { t } = useTransaccionesWords();
  const { i18n } = useTranslation();
  const estado = recordEstado(row, chosen?.space_id ?? null);
  if (!estado) return <Unknown meaning={t(`${WORKFLOW}.unknown`)} />;
  // A word the locale lacks reads as a detail missing, never a raw code.
  const words = estado.reasons.map((key) => t(i18n.exists(key) ? key : `${MISSING}.detail_missing`));
  const first = words[0] ?? (estado.note ? t(estado.note) : null);
  const text = first === null ? null : words.length > 1 ? t(`${PLACEHOLDER}.more_count`, { reason: first, count: words.length - 1 }) : estado.more ? t(`${PLACEHOLDER}.more`, { reason: first }) : first;
  const label = estado.status === "ready" ? t(`${WORKFLOW}.ready`) : estado.status === "review" ? t(`${WORKFLOW}.review`) : estado.status === "fix" ? t(`${PLACEHOLDER}.fix`) : t(`${PLACEHOLDER}.${row.kind === "venta" ? "excluded_sale" : "excluded_purchase"}`);
  return (
    <span className={styles.estado}>
      <span data-record-workflow={estado.status} className={`${styles.workflow} ${TONE[estado.status]}`}>{label}</span>
      {text ? <Tooltip content={words.length > 1 ? words.join(" · ") : text} side="top"><span data-record-reason className={styles.reason}>{text}</span></Tooltip> : null}
    </span>
  );
}
