"use client";

import { CircleAlert } from "lucide-react";
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/Tooltip";
import type { BusinessDossier } from "@/lib/business-dossier";
import { resolveLanguage } from "@/lib/language-features";
import { formatAmount, formatMoney, UNKNOWN_VALUE } from "./business-format";
import type { AttentionItem } from "./dossier-attention";
import type { FactsReview } from "./ReceiptRecordFacts";
import { recordFactRows, fiscalFactRows } from "./receipt-fact-rows";

export default function ReceiptAmounts({ dossier, review, attention = [] }: { dossier: BusinessDossier; review?: FactsReview; attention?: readonly AttentionItem[] }) {
  const { t, i18n } = useTranslation();
  const id = useId();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const currency = dossier.facts.currency.value;
  const tip = dossier.facts.legal_tip?.value;
  const mismatch = dossier.review_flags?.find((flag) => flag.code === "amounts_mismatch");
  const hint = t(tip !== null && tip !== undefined ? "business.terms.calculated_hint_with_tip" : "business.terms.calculated_hint");
  const money = (amount: string | null | undefined) => {
    if (amount == null) return UNKNOWN_VALUE;
    if (currency) return formatMoney(amount, currency, locale) || UNKNOWN_VALUE;
    return `${formatAmount(amount, "", locale)} · ${t("business.reception_preview.placeholder.reason.missing_currency")}`;
  };
  const rows = new Map([...recordFactRows(dossier), ...fiscalFactRows(dossier.facts)].map((entry) => [entry.key, entry]));
  const row = (key: "net_amount" | "itbis" | "legal_tip" | "amount", label: string, amount: string | null | undefined) => {
    const standing = rows.get(key);
    const blocked = standing?.blocked || key === "amount" && Boolean(review && rows.get("currency")?.blocked);
    const asked = standing?.asked;
    const flagged = attention.some((item) => item.field === key || key === "amount" && item.field === "currency");
    const total = key === "amount";
    const calculated = key === "net_amount" && dossier.net_amount?.source === "calculated";
    const value = <span className="inline-flex items-center justify-end gap-1.5">{calculated ? <Tooltip content={hint} side="top"><span tabIndex={0} aria-label={hint} data-testid="amount-calculated" className="text-[13px] font-normal text-[#56635e] dark:text-white/65">ƒ</span></Tooltip> : null}<span>{money(amount)}</span></span>;
    return <div key={key} data-fact={key} data-standing={standing?.standing} data-blocked={blocked || asked ? "true" : undefined} data-attention={flagged ? "true" : undefined} data-match={amount != null ? JSON.stringify([amount, money(amount)]) : undefined} className={`grid grid-cols-[minmax(7.5rem,34%)_minmax(0,1fr)] items-start gap-x-4 py-1.5 max-tablet:[&:has([data-row-open])]:grid-cols-1 ${total ? "mt-1 border-t border-[#DCE0DA] pt-3 font-semibold dark:border-white/10" : ""}`}>
      <dt className="flex min-h-9 items-center text-[13px] leading-[18px] text-[#56635e] dark:text-white/70">{flagged ? <span aria-hidden="true" data-testid="attention-marker" className="mr-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#c27a1e] dark:bg-[#e8b26f]" /> : null}{label}</dt>
      <dd className={`cuadrao-amount min-w-0 py-[7px] text-right text-[15px] leading-[22px] tabular-nums [&_button>span]:text-right ${total && mismatch ? "text-[#9a650d] dark:text-[#e8b26f]" : "text-[#172b26] dark:text-white"}`}>
        {review ? review.row(key, { label, value, compound: calculated }) : value}
        {review?.note(key)}
        {(blocked || asked) && !(review && flagged) ? <span className="mt-1 block text-[13px] font-normal text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.dossier.needs_resolution")}</span> : null}
        {total && mismatch?.difference != null ? <span data-testid="amounts-difference" className="mt-1 flex items-center justify-end gap-1 text-[13px] font-normal"><CircleAlert className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />{t("business.terms.difference", { amount: money(mismatch.difference) })}</span> : null}
      </dd>
    </div>;
  };
  return <section data-testid="receipt-facts-montos" aria-labelledby={id}>
    <h3 id={id} className="text-[12px] font-medium uppercase leading-4 tracking-[0.06em] text-[#56635e] dark:text-white/60">{t("business.terms.montos_title")}</h3>
    <dl className="mt-1">
      {row("net_amount", t("business.terms.net_amount"), dossier.net_amount?.amount)}
      {row("itbis", t("business.terms.itbis"), dossier.facts.fiscal?.itbis.value)}
      {tip != null ? row("legal_tip", t("business.terms.legal_tip"), tip) : null}
      {row("amount", t("business.terms.total_review"), dossier.facts.amount.value)}
    </dl>
  </section>;
}
