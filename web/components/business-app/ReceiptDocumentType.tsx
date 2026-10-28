"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessDossier } from "@/lib/business-dossier";
import { randomId } from "@/lib/random-id";
import { useBusiness } from "./BusinessWorkspace";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { FACT_LABEL_CLASS, FACT_ROW_CLASS } from "./ReceiptRecordFacts";

type DocumentType = NonNullable<BusinessDossier["document_type"]>;

/**
 * Compra or Venta on one record. While the draft is open and the person can
 * prepare, the server says it can change; after approval it is fixed. A type
 * read from the document says so, so a wrong guess is easy to spot and fix.
 */
export default function ReceiptDocumentType({ dossier, busy = false, onChanged }: { dossier: BusinessDossier; busy?: boolean; onChanged: (next: BusinessDossier) => void }) {
  const { t } = useTranslation();
  const { source, reload } = useBusiness();
  const [pending, setPending] = useState<DocumentType | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const current = dossier.document_type;
  if (!current) return null;
  const label = (type: DocumentType) => t(type === "venta" ? "business.intake.type_venta" : "business.intake.type_recibo", type === "venta" ? "Sale" : "Purchase");

  const change = async (next: DocumentType) => {
    if (next === current || pending) return;
    setPending(next);
    setProblem(null);
    try {
      onChanged(await source.setDocumentType(dossier.draft_id, dossier.version, next, randomId()));
      reload();
    } catch (error) {
      const code = (error as { code?: string }).code;
      setProblem(code === "stale_version"
        ? t("business.dossier.stale", "This record changed. Open the current revision and review it before taking another action.")
        : code === "document_type_locked"
          ? t("business.dossier.type_locked", "This record is approved. Its type no longer changes.")
          : t("business.dossier.type_failed", "We couldn't change the type. Try again."));
    } finally {
      setPending(null);
    }
  };

  const note = dossier.document_type_detected
    ? current === "venta"
      ? t("business.dossier.type_detected_venta", "We read it as a sale from your business's RNC. Add the client's RNC.")
      : t("business.dossier.type_detected_recibo", "We read it as a purchase. Change it if it is a sale.")
    : null;

  return (
    <div data-testid="receipt-document-type" data-fact="document_type" data-type={current} data-detected={dossier.document_type_detected ? "true" : undefined} className={FACT_ROW_CLASS}>
      <dt className={FACT_LABEL_CLASS}>{t("business.dossier.type_label", "Type")}</dt>
      <dd className="min-w-0 py-1">
        {dossier.document_type_editable ? (
          <SegmentedControl
            testId="receipt-document-type-control"
            label={t("business.dossier.type_label", "Type")}
            segments={[{ key: "recibo" as const, label: label("recibo") }, { key: "venta" as const, label: label("venta") }]}
            value={pending ?? current}
            disabled={busy || pending !== null}
            onChange={(next) => void change(next)}
          />
        ) : (
          <p className="py-[3px] text-[15px] leading-[22px] text-[#172b26] dark:text-white">{label(current)}</p>
        )}
        {note ? <p className="mt-1 text-[13px] text-[#56635e] dark:text-white/70">{note}</p> : null}
        {problem ? <p role="alert" className="mt-1 text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{problem}</p> : null}
      </dd>
    </div>
  );
}
