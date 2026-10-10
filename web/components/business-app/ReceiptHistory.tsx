"use client";

import { useTranslation } from "react-i18next";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessDraftRevision, BusinessFactField } from "@/lib/business-dossier";
import { formatTimestamp } from "./business-format";
import { cardClass, useCategoryLabel } from "./business-ui";
import { presentBusinessFact } from "./receipt-fact-presentation";

export default function ReceiptHistory({ history, accounts }: { history: BusinessDraftRevision[]; accounts: BusinessAccount[] }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const categoryLabel = useCategoryLabel();
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
  return (
    <details className={cardClass} data-testid="receipt-history">
      <summary className="min-h-11 cursor-pointer text-[14px] font-medium text-black/75 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20 dark:text-white/75 dark:focus-visible:ring-white/20">{t("business.dossier.history", "Revision history")} <span className="ml-1 text-black/45 dark:text-white/45">({history.length})</span></summary>
      {history.length ? (
        <ol className="mt-2 space-y-5">
          {[...history].sort((a, b) => b.version - a.version).map((revision) => {
            const changed = (Object.keys(revision.after).filter((key) => key !== "fiscal") as BusinessFactField[]).filter((key) => JSON.stringify(revision.before?.[key]) !== JSON.stringify(revision.after[key]));
            return (
              <li key={revision.version} className="border-l-2 border-black/10 pl-3 dark:border-white/10">
                <p className="text-[14px] font-medium text-black/80 dark:text-white/80">{revision.actor.display_name} · {t("business.dossier.revision", "Revision {{version}}", { version: revision.version })}</p>
                <p className="mt-1 text-[12px] text-black/55 dark:text-white/55">{formatTimestamp(revision.created_at, locale)}</p>
                {revision.actor.grant_id ? <p className="mt-1 text-[12px] text-black/55 dark:text-white/55">{t("business.dossier.grant_used", "Permission granted by {{issuer}}", { issuer: revision.actor.issuer_display_name })}</p> : null}
                <dl className="mt-3 space-y-3">
                  {changed.map((key) => (
                    <div key={key} className="text-[13px]">
                      <dt className="font-medium text-black/65 dark:text-white/65">{t(`business.dossier.field.${key}`, key)}</dt>
                      <dd className="mt-1 break-words text-black/75 dark:text-white/75"><span className="text-black/50 dark:text-white/50">{revision.before ? presentBusinessFact(key, revision.before, accounts, locale, labels) : t("business.dossier.not_recorded", "Not recorded")}</span><span aria-label={t("business.dossier.changed_to", "changed to")} className="mx-2">→</span>{presentBusinessFact(key, revision.after, accounts, locale, labels)}</dd>
                    </div>
                  ))}
                </dl>
                {!changed.length ? <p className="mt-2 text-[13px] text-black/65 dark:text-white/65">{t("business.dossier.reviewed_revision", "This revision was reviewed.")}</p> : null}
              </li>
            );
          })}
        </ol>
      ) : <p className="mt-2 text-[13px] text-black/60 dark:text-white/60">{t("business.dossier.no_history", "No revisions have been recorded yet.")}</p>}
    </details>
  );
}
