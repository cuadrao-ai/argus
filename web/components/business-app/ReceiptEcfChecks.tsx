"use client";

import { AlertCircle, CheckCircle2, CircleDashed } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { EcfCheck, EcfVerification } from "@/lib/business-dossier";
import { formatTimestamp } from "./business-format";
import { cardClass } from "./business-ui";

/**
 * What the e-CF file proved by itself, one line per check, in words that never
 * overreach: a verified signature says the content has not changed since it was
 * signed, never who signed; DGII acceptance and the issuing authority are named
 * as not checked. A line marked Review never blocks approval.
 */

type T = (key: string, fallback: string, options?: Record<string, unknown>) => string;

const UNSUPPORTED = new Set(["unsupported_algorithm", "reference_unsupported", "unsupported_transform", "unsupported_key"]);

function reason(code: string | null, t: T): string {
  if (code === "no_signature") return t("business.dossier.ecf_reason_no_signature", "the file carries no signature");
  if (code === "several_signatures") return t("business.dossier.ecf_reason_several_signatures", "it carries more than one signature");
  if (code && UNSUPPORTED.has(code)) return t("business.dossier.ecf_reason_unsupported", "signature form not supported");
  return t("business.dossier.ecf_reason_unreadable", "the signature could not be read");
}

export function ecfCheckLine(check: EcfCheck, t: T): string {
  const { name, state, code, detail } = check;
  switch (name) {
    case "signature_integrity":
      if (state === "verified") return t("business.dossier.ecf_integrity_verified", "Content unchanged since it was signed");
      if (state === "failed") return t("business.dossier.ecf_integrity_failed", "Review: the content changed after it was signed");
      return t("business.dossier.ecf_integrity_not_checked", "Signature not checked: {{reason}}", { reason: reason(code, t) });
    case "totals_arithmetic":
      if (state === "verified") return t("business.dossier.ecf_totals_verified", "The totals add up");
      if (state === "failed" && code === "items_mismatch") return t("business.dossier.ecf_totals_items_failed", "Review: the lines do not add up to the base (lines {{items}})", { items: detail.sum_of_items ?? "" });
      if (state === "failed") return t("business.dossier.ecf_totals_failed", "Review: the totals do not add up (total {{total}}, sum {{sum}})", { total: detail.monto_total ?? "", sum: detail.sum_of_parts ?? "" });
      return t("business.dossier.ecf_totals_not_checked", "Totals not checked");
    case "read_matches_xml":
      if (state === "verified") return t("business.dossier.ecf_read_verified", "The read matches the XML");
      if (state === "failed") {
        const fields = Object.keys(detail).map((field) => t(`business.dossier.ecf_field_${field}`, field)).join(", ");
        return t("business.dossier.ecf_read_failed", "Review: the read differs from the XML in {{fields}}", { fields });
      }
      return t("business.dossier.ecf_read_not_checked", "Read not compared with the XML");
    case "certificate_validity":
      if (state === "verified") return t("business.dossier.ecf_validity_verified", "Certificate valid when signed ({{signed_at}}); revocation not checked", { signed_at: detail.signed_at ?? "" });
      if (state === "failed") return t("business.dossier.ecf_validity_failed", "Review: the certificate was not valid when signed ({{signed_at}})", { signed_at: detail.signed_at ?? "" });
      return t("business.dossier.ecf_validity_not_checked", "Certificate validity not checked");
    case "certificate_issuer":
      return detail.issuer ? t("business.dossier.ecf_issuer_not_checked", "Certificate issuer not checked: {{issuer}}", { issuer: detail.issuer }) : t("business.dossier.ecf_issuer_unknown", "Certificate issuer not checked");
    case "subject_rnc":
      if (state === "verified") return t("business.dossier.ecf_subject_verified", "The certificate belongs to the issuer's RNC");
      if (state === "failed") return t("business.dossier.ecf_subject_failed", "Review: the certificate does not belong to the issuer's RNC ({{serial}})", { serial: detail.subject_serial ?? "" });
      return t("business.dossier.ecf_subject_not_checked", "Certificate RNC not checked");
    case "dgii_accepted":
      return t("business.dossier.ecf_dgii_not_checked", "DGII acceptance not looked up");
    case "security_code":
      return detail.expected ? t("business.dossier.ecf_security_expected", "Expected security code: {{code}}", { code: detail.expected }) : t("business.dossier.ecf_security_unavailable", "Security code not available");
  }
}

const STATE_ICON = {
  verified: { Icon: CheckCircle2, className: "text-[#2f8f5b]" },
  failed: { Icon: AlertCircle, className: "text-[#d66d75]" },
  not_checked: { Icon: CircleDashed, className: "text-black/40 dark:text-white/40" },
} as const;

export default function ReceiptEcfChecks({ verification }: { verification: EcfVerification | null }) {
  const { t, i18n } = useTranslation();
  if (!verification) return null;
  const locale = i18n.resolvedLanguage ?? "en";
  const typeLabel = verification.tipo_ecf ? t(`business.dossier.ecf_type_${verification.tipo_ecf}`, "") : "";
  const document = verification.encf
    ? typeLabel
      ? t("business.dossier.ecf_document", "e-CF {{encf}} · type {{tipo}}, {{label}}", { encf: verification.encf, tipo: verification.tipo_ecf, label: typeLabel })
      : t("business.dossier.ecf_document_untyped", "e-CF {{encf}} · type {{tipo}}", { encf: verification.encf, tipo: verification.tipo_ecf ?? "" })
    : null;
  return (
    <section className={cardClass} aria-labelledby="receipt-ecf-checks-title" data-testid="receipt-ecf-checks">
      <h3 id="receipt-ecf-checks-title" className="text-[14px] font-medium text-black dark:text-white">{t("business.dossier.ecf_title", "Electronic invoice verification")}</h3>
      {document ? <p className="mt-1 text-[13px] text-black/60 dark:text-white/60">{document}</p> : null}
      <ul className="mt-4 space-y-2">
        {verification.checks.map((check) => {
          const { Icon, className } = STATE_ICON[check.state];
          return (
            <li key={check.name} data-check={check.name} data-state={check.state} className="flex items-start gap-2 text-[14px] text-black/80 dark:text-white/80">
              <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${className}`} aria-hidden="true" />
              <span className="min-w-0 flex-1">{ecfCheckLine(check, t)}</span>
              <span className="shrink-0 rounded-full border border-black/10 px-2 py-0.5 text-[12px] text-black/60 dark:border-white/15 dark:text-white/60">{t(`business.dossier.ecf_state_${check.state}`, check.state)}</span>
            </li>
          );
        })}
      </ul>
      <p className="mt-4 text-[12px] text-black/55 dark:text-white/55">{t("business.dossier.ecf_note", "What the file proves by itself. Nothing here confirms DGII accepted the invoice; a line marked Review does not block approval.")}</p>
      <p className="mt-1 text-[12px] text-black/45 dark:text-white/45">{t("business.dossier.ecf_checked_at", "Checked on {{when}}", { when: formatTimestamp(verification.checked_at, locale) })}</p>
    </section>
  );
}
