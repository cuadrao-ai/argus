"use client";

import type { TFunction } from "i18next";
import { useBusiness } from "../BusinessWorkspace";
import type { Purchase606 } from "@/lib/business-reports-api";
import type { RecordRow } from "./transacciones-model";
import { previewRecordMetadata } from "./records-results-preview";
import { useTransaccionesWords } from "./transacciones-words";
import { Truncated, Unknown } from "./transacciones-parts";
import palette from "./records-overview-preview.module.css";
import chip from "../foundation/status-chip.module.css";

/** The 606 answers a row carries: the server's for a live row, the sample's illustration otherwise. Undefined when no read says. */
export function record606(row: RecordRow, businessId: string | null): Purchase606 | null | undefined {
  return row.report ? row.report.dgii_606 : previewRecordMetadata(row, businessId)?.dgii606;
}

/** One answer of a purchase the 606 lists, in words: the localized DGII name, or the word Bandeja uses for a missing answer. */
export function dgiiAnswerText(t: TFunction, purchase: Purchase606, field: keyof Purchase606): string {
  const choice = purchase[field];
  if (!choice) return t("business.dossier.standing.missing");
  return t(`business.dgii.option.${field === "expense_type" ? "category" : "payment_method"}.${choice.code}`, { defaultValue: choice.code }) || choice.code;
}

/** Registros reports missing answers in Estado. Search and review name them beside the field. */
export function DgiiAnswer({ purchase, field, missingDisplay = "label" }: {
  purchase: Purchase606 | null | undefined;
  field: keyof Purchase606;
  missingDisplay?: "label" | "dash";
}) {
  const { t } = useTransaccionesWords();
  if (purchase === undefined) return <Unknown />;
  if (purchase === null) return <Unknown meaning={t("business.export.form_no_aplica")} />;
  if (!purchase[field]) {
    if (missingDisplay === "dash") return <Unknown />;
    return <span className={`${chip.workflow} ${palette.review}`}>{dgiiAnswerText(t, purchase, field)}</span>;
  }
  return <Truncated text={dgiiAnswerText(t, purchase, field)} />;
}

export default function RecordDgiiCell({ row, field }: { row: RecordRow; field: keyof Purchase606 }) {
  const { chosen } = useBusiness();
  return <DgiiAnswer purchase={record606(row, chosen?.space_id ?? null)} field={field} missingDisplay="dash" />;
}
