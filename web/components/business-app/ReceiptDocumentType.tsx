"use client";

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessDossier } from "@/lib/business-dossier";
import { DossierRow, type RowEdit } from "./dossier/DossierParts";
import { DOCUMENT_TYPE_LABELS } from "./receipt-fact-rows";

/**
 * Compra or Venta on one record, as a row of the form. `edit` is the shared
 * row edit on a draft whose type can still change; after approval it is fixed.
 * While the record is open, a sale read from the business's RNC asks for the
 * client's RNC.
 */
export default function ReceiptDocumentType({ dossier, edit, note }: {
  dossier: BusinessDossier;
  edit?: RowEdit;
  /** The row's save state. */
  note?: ReactNode;
}) {
  const { t } = useTranslation();
  const current = dossier.document_type;
  if (!current) return null;
  const detected = dossier.document_type_detected && dossier.review_state === "open" && current === "venta"
    ? t("business.dossier.type_detected_venta", "We read it as a sale from your business's RNC. Add the client's RNC.")
    : null;
  return (
    <DossierRow row="document_type" testId="receipt-document-type" data={{ "data-type": current, "data-detected": dossier.document_type_detected ? "true" : undefined }} label={t("business.dossier.type_label", "Type")} value={t(DOCUMENT_TYPE_LABELS[current])} edit={edit} below={detected || note ? <>{detected ? <p>{detected}</p> : null}{note}</> : undefined} />
  );
}
