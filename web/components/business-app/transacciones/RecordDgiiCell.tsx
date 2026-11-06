"use client";

import { useBusiness } from "../BusinessWorkspace";
import type { Purchase606 } from "@/lib/business-reports-api";
import type { RecordRow } from "./transacciones-model";
import { previewRecordMetadata } from "./records-results-preview";
import { useTransaccionesWords } from "./transacciones-words";
import { Truncated, Unknown } from "./transacciones-parts";
import palette from "./records-overview-preview.module.css";
import styles from "./transacciones-cells.module.css";

/** The 606 answers a row carries: the server's for a live row, the sample's illustration otherwise. Undefined when no read says. */
export function record606(row: RecordRow, businessId: string | null): Purchase606 | null | undefined {
  return row.report ? row.report.dgii_606 : previewRecordMetadata(row, businessId)?.dgii606;
}

/** One 606 answer as Registros shows it: the localized DGII name, truncated with the full name on hover; the word Bandeja uses for a missing answer; a dash for a record the 606 never lists. */
export default function RecordDgiiCell({ row, field }: { row: RecordRow; field: keyof Purchase606 }) {
  const { chosen } = useBusiness();
  const { t } = useTransaccionesWords();
  const purchase = record606(row, chosen?.space_id ?? null);
  if (purchase === undefined) return <Unknown />;
  if (purchase === null) return <Unknown meaning={t("business.export.form_no_aplica")} />;
  const choice = purchase[field];
  if (!choice) return <span data-dgii-missing={field} className={`${styles.workflow} ${palette.review}`}>{t("business.dossier.standing.missing")}</span>;
  return <Truncated text={t(`business.dgii.option.${field === "expense_type" ? "category" : "payment_method"}.${choice.code}`, { defaultValue: choice.code }) || choice.code} />;
}
