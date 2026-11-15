"use client";

import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/Tooltip";
import { useBusiness } from "../BusinessWorkspace";
import type { RecordRow } from "./transacciones-model";
import { previewRecordMetadata } from "./records-results-preview";
import { useTransaccionesWords } from "./transacciones-words";
import { Unknown } from "./transacciones-parts";
import palette from "./records-overview-preview.module.css";
import styles from "./transacciones-cells.module.css";

// MOCK (#2169 v2), DO NOT MERGE. Two states: Listo, or the first missing thing in the "Faltan datos" card's colour.
const WORKFLOW = "business.transactions.layout.workflow";
const MISSING = `${WORKFLOW}.missing`;
/** A reason the server names lives under `missing`; the one word the mock adds is a marked placeholder beside it. */
const reasonKey = (word: string) => word.startsWith("placeholder.") ? `${WORKFLOW}.${word}` : `${MISSING}.${word}`;
/** `missing` are locale paths, first fix first. `more` says the server named only the first of several, so the count is unknown. */
export type RecordEstado = { ready: true } | { ready: false; missing: readonly string[]; more: boolean };

/**
 * The mock maps the fields the server sends today onto the two states. The build deletes this function:
 * the server sends the state and the full list, and the card count and its filter read the same predicate.
 */
export function recordEstado(row: RecordRow, businessId: string | null): RecordEstado | null {
  const report = row.report;
  if (!report) {
    const sample = previewRecordMetadata(row, businessId);
    if (!sample) return null;
    return sample.missing ? { ready: false, missing: sample.missing.map(reasonKey), more: false } : { ready: true };
  }
  if (!report.stage) return null;
  if (report.stage === "needs_review") return { ready: false, missing: [reasonKey("placeholder.account_missing")], more: false };
  if (report.stage === "needs_fiscal_data" || report.fiscal_data === "missing") {
    const all = report.missing?.length ? report.missing : null;
    return { ready: false, missing: (all ?? [report.export_missing ?? "detail_missing"]).map(reasonKey), more: !all && Boolean(report.export_missing_several) };
  }
  return { ready: true };
}

/** `compact` is the phone card: the pill alone, no reason. */
export default function RecordWorkflowBadge({ row, compact = false }: { row: RecordRow; compact?: boolean }) {
  const { chosen } = useBusiness();
  const { t } = useTransaccionesWords();
  const { i18n } = useTranslation();
  const estado = recordEstado(row, chosen?.space_id ?? null);
  if (!estado) return <Unknown meaning={t(`${WORKFLOW}.unknown`)} />;
  if (estado.ready) return <span data-record-workflow="ready" className={styles.ready}><Check size={14} strokeWidth={2} aria-hidden="true" />{t(`${WORKFLOW}.ready`)}</span>;
  if (compact) return <span data-record-workflow="not_ready" className={`${styles.workflow} ${palette.fiscal}`}>{t(`${WORKFLOW}.not_ready`)}</span>;
  // A word the locale lacks reads as a detail missing, never a raw code.
  const words = estado.missing.map((key) => t(i18n.exists(key) ? key : `${MISSING}.detail_missing`));
  const extra = words.length > 1 ? `+${words.length - 1}` : estado.more ? "+" : null;
  return <Tooltip content={words.join(" · ") + (estado.more ? " …" : "")} side="top"><span data-record-workflow="not_ready" className={`${styles.workflow} ${styles.notReady} ${palette.fiscal}`}><span className={styles.firstMissing}>{words[0]}</span>{extra ? <span data-record-more>{extra}</span> : null}</span></Tooltip>;
}
