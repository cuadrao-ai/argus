"use client";

import { useTranslation } from "react-i18next";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessDossier, BusinessFactField } from "@/lib/business-dossier";
import { useCategoryLabel } from "./business-ui";
import { presentBusinessFact } from "./receipt-fact-presentation";

const VISIBLE_FIELDS: BusinessFactField[] = ["kind", "counterparty", "occurred_on", "amount", "currency", "category_id", "funding", "business_share", "receipt_state"];

export default function ReceiptRecordFacts({ dossier, accounts }: { dossier: BusinessDossier; accounts: BusinessAccount[] }) {
  const { t, i18n } = useTranslation();
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
    <dl className="grid grid-cols-2 gap-x-4 gap-y-5" data-testid="receipt-current-facts">
      {VISIBLE_FIELDS.map((key) => {
        const fact = dossier.facts[key];
        const material = dossier.questions.some((question) => question.field === key && ["open", "owner_does_not_know", "waiting_for_window"].includes(question.state));
        const value = presentBusinessFact(key, dossier.facts, accounts, i18n.resolvedLanguage ?? "en", labels);
        return (
          <div key={key} className={key === "funding" || key === "counterparty" ? "col-span-2 min-w-0" : "min-w-0"}>
            <dt className="text-[12px] font-medium text-black/55 dark:text-white/55">{t(`business.dossier.field.${key}`, key)}</dt>
            <dd className="mt-1.5 break-words text-[15px] text-black/85 dark:text-white/85">
              {value}
            </dd>
            <p className="mt-1 text-[12px] text-black/55 dark:text-white/55">
              {fact.state === "known" ? fact.origin === "default" ? t("business.dossier.default", "Default · not verified") : fact.verified ? t("business.dossier.verified", "Verified") : t(`business.dossier.origin.${fact.origin}`, t("business.dossier.not_verified", "Not verified")) : material ? t("business.dossier.needs_resolution", "Needs a decision before approval") : t("business.dossier.not_verified", "Not verified")}
            </p>
          </div>
        );
      })}
    </dl>
  );
}
