"use client";

import { AlertCircle, CheckCircle2, CircleDashed, Link2, QrCode } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessDossier, BusinessFactField } from "@/lib/business-dossier";
import { useCategoryLabel } from "./business-ui";
import { presentBusinessFact, presentFiscalFact } from "./receipt-fact-presentation";
import { fiscalFactRows, recordFactRows, reviewCounts, type FactStanding } from "./receipt-fact-rows";

type StandingStyle = { Icon: typeof CheckCircle2; className: string; chip: string };

const GREY: StandingStyle = { Icon: CircleDashed, className: "text-black/40 dark:text-white/40", chip: "border-black/15 text-black/55 dark:border-white/15 dark:text-white/55" };
const STYLE: Record<FactStanding, StandingStyle> = {
  verified: { Icon: CheckCircle2, className: "text-[var(--rui-color-teal)]", chip: "border-[var(--rui-color-teal)]/40 text-[var(--rui-color-teal)]" },
  person: { Icon: CheckCircle2, className: "text-[var(--cuadrao-green)]", chip: "border-[var(--cuadrao-green)]/35 text-[var(--cuadrao-green)]" },
  qr: { Icon: QrCode, className: "text-[var(--cuadrao-green)]", chip: "border-[var(--cuadrao-green)]/35 text-[var(--cuadrao-green)]" },
  linked: { Icon: Link2, className: "text-[var(--cuadrao-green)]", chip: "border-[var(--cuadrao-green)]/35 text-[var(--cuadrao-green)]" },
  suggestion: { Icon: CircleDashed, className: "text-[var(--rui-color-warning)]", chip: "border-dashed border-[var(--rui-color-warning)]/70 text-[#7a6420] dark:text-[var(--rui-color-warning)]" },
  default: GREY,
  unverified: GREY,
  owner_unknown: GREY,
  empty: GREY,
};
const BLOCKED: StandingStyle = { Icon: AlertCircle, className: "text-[var(--rui-color-danger)]", chip: "border-[var(--rui-color-danger)]/50 text-[var(--rui-color-danger)]" };

export default function ReceiptRecordFacts({ dossier, accounts, onEdit, editor }: {
  dossier: BusinessDossier;
  accounts: BusinessAccount[];
  onEdit?: (key: BusinessFactField) => void;
  editor?: (key: BusinessFactField) => ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const categoryLabel = useCategoryLabel();
  const locale = i18n.resolvedLanguage ?? "en";
  const fiscal = dossier.facts.fiscal;
  const labels = {
    unknown: t("business.dossier.unknown", "Unknown"),
    ownerUnknown: t("business.dossier.owner_unknown", "Owner doesn't know"),
    yes: t("business.marks.yes", "Yes"),
    no: t("business.marks.no", "No"),
    ownerFunds: t("business.dossier.owner_funds", "Owner's money"),
    businessAccount: t("business.dossier.business_account", "Business account"),
    value: (key: BusinessFactField, value: string) => {
      if (key === "category_id") return categoryLabel(value);
      const scope = key === "kind" ? "kind" : key === "business_share" ? "share" : key === "receipt_state" ? "receipt" : null;
      return scope ? t(`business.dossier.${scope}.${value}`, value) : value;
    },
  };
  const rows = recordFactRows(dossier);
  const fiscalRows = fiscalFactRows(dossier.facts);
  const counts = reviewCounts([...rows, ...fiscalRows]);
  // Without an NCF and an e-CF the record has no fiscal receipt number: one row
  // says so, in the chip's words, in place of two empty ones.
  const noFiscal = dossier.fiscal_known === true && !dossier.fiscal_value;
  const shownFiscalRows = noFiscal ? fiscalRows.filter(({ key }) => key !== "ncf" && key !== "ecf") : fiscalRows;

  const standingText = (standing: FactStanding, origin: string | null, blocked: boolean) => {
    if (standing === "verified") return t("business.dossier.verified", "Verified");
    if (standing === "default") return t("business.dossier.default", "Default · not verified");
    if (standing === "suggestion") return t("business.dossier.standing.suggestion", "Read from the source · suggestion, not verified");
    if (standing === "empty") return blocked ? t("business.dossier.standing.missing", "Missing") : t("business.dossier.standing.empty", "No value");
    if (standing === "owner_unknown") return t("business.dossier.owner_unknown", "Owner doesn't know");
    if (standing === "unverified" || !origin) return t("business.dossier.not_verified", "Not verified");
    return t(`business.dossier.origin.${origin}`, t("business.dossier.not_verified", "Not verified"));
  };

  const row = (key: string, label: string, value: string, standing: FactStanding, origin: string | null, blocked: boolean, asked: boolean, edit?: () => void, control?: ReactNode) => {
    const { Icon, className, chip } = blocked && standing === "empty" ? BLOCKED : STYLE[standing];
    const showChip = standing !== "suggestion";
    return (
      <div key={key} data-fact={key} data-standing={standing} data-blocked={blocked || asked ? "true" : undefined} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
        <Icon className={`mt-1 h-4 w-4 shrink-0 ${className}`} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <dt className="text-[12px] font-medium text-black/55 dark:text-white/55">{label}</dt>
          <dd className="mt-0.5 break-words text-[15px] text-black/85 dark:text-white/85">{control ?? (key === "occurred_on" && standing === "empty" ? <input disabled aria-label={label} placeholder="dd/mm/aaaa" className="mt-1 min-h-11 w-full rounded-[12px] border border-black/10 bg-transparent px-3 text-[16px] dark:border-white/15" value="" readOnly /> : edit ? <button type="button" onClick={edit} className="min-h-11 w-full rounded-lg text-left underline decoration-black/20 underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)] dark:decoration-white/20" aria-label={`${t("business.dossier.edit", "Edit details")} · ${label}`}>{value}</button> : value)}</dd>
          {standing === "suggestion" ? <p className="mt-1 text-[12px] text-black/60 dark:text-white/65">{t("business.dossier.read_from_receipt", t("business.dossier.origin.extracted", "Read from source · not verified"))}</p> : null}
          {showChip && !(key === "occurred_on" && standing === "empty") ? <p className="mt-1.5"><span className={`inline-flex min-h-6 items-center rounded-full border px-2 text-[11px] font-medium ${chip}`}>{standingText(standing, origin, blocked)}</span></p> : null}
          {blocked || asked ? <p className="mt-1 text-[12px] font-medium text-[var(--rui-color-danger)]">{key === "occurred_on" && standing === "empty" ? t("business.dossier.add_date_to_approve", "Agrega la fecha para aprobar") : t("business.dossier.needs_resolution", "Needs a decision before approval")}</p> : null}
        </div>
      </div>
    );
  };

  return (
    <div data-testid="receipt-current-facts">
      {counts.suggestions > 0 || counts.missing > 0 || counts.unresolved > 0 ? (
        <div role="status" data-testid="receipt-review-counts" className="mb-4 rounded-[14px] bg-[var(--cuadrao-cream)] px-3.5 py-2.5 text-[13px] text-black/75 dark:text-white/80">
          <p className={counts.suggestions > 0 ? "mt-1" : undefined}>
            {[
              counts.suggestions > 0 ? t("business.dossier.suggestions_pending", { count: counts.suggestions, defaultValue: "{{count}} suggestions to confirm" }) : null,
              counts.missing > 0 ? t("business.dossier.missing_pending", { count: counts.missing, defaultValue: "{{count}} details missing" }) : null,
              counts.unresolved > 0 ? t("business.dossier.unresolved_pending", { count: counts.unresolved, defaultValue: "{{count}} details to resolve" }) : null,
            ].filter(Boolean).join(" · ")}
          </p>
        </div>
      ) : null}
      <dl className="divide-y divide-black/[0.05] dark:divide-white/[0.05]">
        {rows.map(({ key, standing, blocked, asked }) => {
          const fact = dossier.facts[key];
          const value = presentBusinessFact(key, dossier.facts, accounts, locale, labels);
          const edit = onEdit ? () => onEdit(key) : undefined;
          return row(key, t(`business.dossier.field.${key}`, key), value, standing, fact.state === "known" ? fact.origin : null, blocked, asked, edit, editor?.(key));
        })}
      </dl>
      {fiscal || noFiscal ? (
        <div className="mt-5 border-t border-black/10 pt-5 dark:border-white/10" data-testid="receipt-fiscal-facts">
          <p className="mb-3 text-[14px] font-medium text-black/80 dark:text-white/80">{t("business.dossier.fiscal_details", "Fiscal details")}</p>
          <dl className="divide-y divide-black/[0.05] dark:divide-white/[0.05]">
            {noFiscal ? (
              <div data-fact="fiscal_number" data-standing="empty" className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
                <CircleDashed className={`mt-1 h-4 w-4 shrink-0 ${GREY.className}`} aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <dt className="text-[12px] font-medium text-black/55 dark:text-white/55">{`${t("business.dossier.field.ncf", "NCF")} / ${t("business.dossier.field.ecf", "e-CF")}`}</dt>
                  <dd className="mt-0.5 break-words text-[15px] text-black/85 dark:text-white/85">{t("business.marks.no_fiscal_chip", "No fiscal receipt number")}</dd>
                </div>
              </div>
            ) : null}
            {shownFiscalRows.map(({ key, standing }) => {
              const fact = fiscal?.[key];
              const value = presentFiscalFact(key, dossier.facts, locale, { ...labels, notRecorded: t("business.dossier.not_recorded", "Not recorded"), rncUnknown: t("business.dossier.rnc_unknown", "Unknown RNC") });
              // NCF and e-CF are alternatives and no blocker names a fiscal field: an empty one is "Sin dato", never "Falta".
              return row(key, t(`business.dossier.field.${key}`, key), value, standing, fact?.state === "known" ? fact.origin : null, false, false);
            })}
          </dl>
        </div>
      ) : null}
    </div>
  );
}
