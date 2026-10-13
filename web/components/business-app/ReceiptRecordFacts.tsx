"use client";

import { AlertCircle, CheckCircle2, CircleDashed, QrCode, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { BusinessAccount } from "@/lib/business-api";
import { BUSINESS_FISCAL_FIELDS, type BusinessDossier, type BusinessFactField, type BusinessFiscalField } from "@/lib/business-dossier";
import { useCategoryLabel } from "./business-ui";
import { presentBusinessFact, presentFiscalFact } from "./receipt-fact-presentation";
import { factRows, recordFactRows, reviewCounts, type FactStanding } from "./receipt-fact-rows";

/**
 * The record's facts, led by what is settled. Each row says where its value
 * stands: verified, stated by a person, decoded from the DGII QR, suggested
 * by the AI read and waiting for a person, a default, or missing. A
 * suggestion can be confirmed in place by a person who can prepare; the
 * record then holds it as that person's statement, in the history. Nothing
 * here decides approval: the backend's blockers and approval_available do.
 */

type StandingStyle = { Icon: typeof CheckCircle2; className: string; chip: string };

const STYLE: Record<FactStanding, StandingStyle> = {
  verified: { Icon: CheckCircle2, className: "text-[var(--rui-color-teal)]", chip: "border-[var(--rui-color-teal)]/40 text-[var(--rui-color-teal)]" },
  person: { Icon: CheckCircle2, className: "text-[var(--cuadrao-green)]", chip: "border-[var(--cuadrao-green)]/35 text-[var(--cuadrao-green)]" },
  qr: { Icon: QrCode, className: "text-[var(--cuadrao-green)]", chip: "border-[var(--cuadrao-green)]/35 text-[var(--cuadrao-green)]" },
  suggestion: { Icon: Sparkles, className: "text-[var(--rui-color-warning)]", chip: "border-dashed border-[var(--rui-color-warning)]/70 text-[#7a6420] dark:text-[var(--rui-color-warning)]" },
  default: { Icon: CircleDashed, className: "text-black/40 dark:text-white/40", chip: "border-black/15 text-black/55 dark:border-white/15 dark:text-white/55" },
  owner_unknown: { Icon: CircleDashed, className: "text-black/40 dark:text-white/40", chip: "border-black/15 text-black/55 dark:border-white/15 dark:text-white/55" },
  missing: { Icon: AlertCircle, className: "text-[var(--rui-color-danger)]", chip: "border-[var(--rui-color-danger)]/50 text-[var(--rui-color-danger)]" },
};

export default function ReceiptRecordFacts({ dossier, accounts, onConfirm, confirmable = false }: { dossier: BusinessDossier; accounts: BusinessAccount[]; onConfirm?: (key: BusinessFactField) => void; confirmable?: boolean }) {
  const { t, i18n } = useTranslation();
  const categoryLabel = useCategoryLabel();
  const locale = i18n.resolvedLanguage ?? "en";
  const fiscal = dossier.facts.fiscal;
  const labels = {
    unknown: t("business.dossier.unknown", "Unknown"),
    ownerUnknown: t("business.dossier.owner_unknown", "Owner doesn't know"),
    ownerFunds: t("business.dossier.owner_funds", "Owner's money"),
    businessAccount: t("business.dossier.business_account", "Business account"),
    value: (key: BusinessFactField, value: string) => {
      if (key === "category_id") return categoryLabel(value);
      const scope = key === "kind" ? "kind" : key === "business_share" ? "share" : key === "receipt_state" ? "receipt" : null;
      return scope ? t(`business.dossier.${scope}.${value}`, value) : value;
    },
  };
  const rows = recordFactRows(dossier.facts);
  const fiscalRows = fiscal ? factRows(BUSINESS_FISCAL_FIELDS, (key: BusinessFiscalField) => fiscal[key]) : [];
  const counts = reviewCounts([...rows, ...fiscalRows]);

  const standingText = (standing: FactStanding, origin: string | null) => {
    if (standing === "verified") return t("business.dossier.verified", "Verified");
    if (standing === "default") return t("business.dossier.default", "Default · not verified");
    if (standing === "suggestion") return t("business.dossier.standing.suggestion", "Suggestion · not verified");
    if (standing === "missing") return t("business.dossier.standing.missing", "Missing");
    if (standing === "owner_unknown") return t("business.dossier.owner_unknown", "Owner doesn't know");
    return origin ? t(`business.dossier.origin.${origin}`, t("business.dossier.not_verified", "Not verified")) : t("business.dossier.not_verified", "Not verified");
  };

  const row = (key: string, label: string, value: string, standing: FactStanding, origin: string | null, confirm?: () => void) => {
    const { Icon, className, chip } = STYLE[standing];
    return (
      <div key={key} data-fact={key} data-standing={standing} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
        <Icon className={`mt-1 h-4 w-4 shrink-0 ${className}`} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <dt className="text-[12px] font-medium text-black/55 dark:text-white/55">{label}</dt>
          <dd className="mt-0.5 break-words text-[15px] text-black/85 dark:text-white/85">{value}</dd>
          <p className="mt-1.5 flex flex-wrap items-center gap-2">
            <span className={`inline-flex min-h-6 items-center rounded-full border px-2 text-[11px] font-medium ${chip}`}>{standingText(standing, origin)}</span>
            {confirm ? (
              <button type="button" data-testid={`confirm-${key}`} onClick={confirm} className="inline-flex min-h-8 items-center rounded-full bg-[var(--cuadrao-green)] px-3 text-[12px] font-medium text-[var(--cuadrao-cream)] transition-opacity hover:opacity-85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40">
                {t("business.dossier.confirm_value", "Confirm")}
              </button>
            ) : null}
          </p>
        </div>
      </div>
    );
  };

  return (
    <div data-testid="receipt-current-facts">
      {counts.suggestions > 0 || counts.missing > 0 ? (
        <p role="status" data-testid="receipt-review-counts" className="mb-4 rounded-[14px] bg-[var(--cuadrao-cream)] px-3.5 py-2.5 text-[13px] text-black/75 dark:text-white/80">
          {[
            counts.suggestions > 0 ? t("business.dossier.suggestions_pending", { count: counts.suggestions, defaultValue: "{{count}} suggestions to confirm" }) : null,
            counts.missing > 0 ? t("business.dossier.missing_pending", { count: counts.missing, defaultValue: "{{count}} details missing" }) : null,
          ].filter(Boolean).join(" · ")}
        </p>
      ) : null}
      <dl className="divide-y divide-black/[0.05] dark:divide-white/[0.05]">
        {rows.map(({ key, standing }) => {
          const fact = dossier.facts[key];
          const value = presentBusinessFact(key, dossier.facts, accounts, locale, labels);
          const confirm = confirmable && onConfirm && standing === "suggestion" ? () => onConfirm(key) : undefined;
          return row(key, t(`business.dossier.field.${key}`, key), value, standing, fact.state === "known" ? fact.origin : null, confirm);
        })}
      </dl>
      {fiscal ? (
        <div className="mt-5 border-t border-black/10 pt-5 dark:border-white/10" data-testid="receipt-fiscal-facts">
          <p className="mb-3 text-[14px] font-medium text-black/80 dark:text-white/80">{t("business.dossier.fiscal_details", "Fiscal details")}</p>
          <dl className="divide-y divide-black/[0.05] dark:divide-white/[0.05]">
            {fiscalRows.map(({ key, standing }) => {
              const fact = fiscal[key];
              const value = presentFiscalFact(key, dossier.facts, locale, { ...labels, notRecorded: t("business.dossier.not_recorded", "Not recorded") });
              return row(key, t(`business.dossier.field.${key}`, key), value, standing, fact.state === "known" ? fact.origin : null);
            })}
          </dl>
        </div>
      ) : null}
    </div>
  );
}
