"use client";

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessDossier } from "@/lib/business-dossier";
import type { RowShown } from "./ReceiptEditRow";
import { FACT_LABEL_CLASS, FACT_ROW_CLASS } from "./ReceiptRecordFacts";
import { DOCUMENT_TYPE_LABELS } from "./receipt-fact-rows";

/**
 * Compra or Venta on one record, as a fact row. `row` is the shared edit row on
 * a draft whose type can still change; after approval it is fixed. A type read
 * from the document says so, so a wrong guess is easy to spot and fix.
 */
export default function ReceiptDocumentType({ dossier, row, note }: {
  dossier: BusinessDossier;
  row?: (shown: RowShown) => ReactNode;
  /** The row's save state. */
  note?: ReactNode;
}) {
  const { t } = useTranslation();
  const current = dossier.document_type;
  if (!current) return null;
  const label = t("business.dossier.type_label", "Type");
  const value = t(DOCUMENT_TYPE_LABELS[current]);
  const detected = dossier.document_type_detected
    ? current === "venta"
      ? t("business.dossier.type_detected_venta", "We read it as a sale from your business's RNC. Add the client's RNC.")
      : t("business.dossier.type_detected_recibo", "We read it as a purchase. Change it if it is a sale.")
    : null;

  return (
    <div data-testid="receipt-document-type" data-fact="document_type" data-type={current} data-detected={dossier.document_type_detected ? "true" : undefined} className={FACT_ROW_CLASS}>
      <dt className={FACT_LABEL_CLASS}>{label}</dt>
      <dd className="min-w-0 break-words py-[7px] text-[15px] leading-[22px] text-[#172b26] dark:text-white">
        {row ? row({ label, value }) : value}
        {detected ? <p className="mt-1 text-[13px] leading-[18px] text-[#56635e] dark:text-white/70">{detected}</p> : null}
        {note}
      </dd>
    </div>
  );
}
