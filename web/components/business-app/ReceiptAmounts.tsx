"use client";

import { TriangleAlert } from "lucide-react";
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/Tooltip";
import type { BusinessDossier } from "@/lib/business-dossier";
import { resolveLanguage } from "@/lib/language-features";
import { formatAmount, UNKNOWN_VALUE } from "./business-format";
import type { AttentionItem } from "./dossier-attention";
import { AMOUNT_BOX_CLASS } from "./ReceiptEditRow";
import type { FactsReview } from "./ReceiptRecordFacts";
import { recordFactRows, fiscalFactRows } from "./receipt-fact-rows";

export default function ReceiptAmounts({ dossier, review, attention = [] }: { dossier: BusinessDossier; review?: FactsReview; attention?: readonly AttentionItem[] }) {
  const { t, i18n } = useTranslation();
  const id = useId();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const currency = dossier.facts.currency.value;
  const tip = dossier.facts.legal_tip?.value;
  const net = review?.amountsPreview?.net_amount ?? dossier.net_amount;
  const mismatch = review?.amountsPreview !== undefined ? review.amountsPreview?.mismatch : dossier.review_flags?.find((flag) => flag.code === "amounts_mismatch");
  const hint = t(tip !== null && tip !== undefined ? "business.terms.calculated_hint_with_tip" : "business.terms.calculated_hint");
  const money = (amount: string | null | undefined) => amount == null ? UNKNOWN_VALUE : formatAmount(amount, currency ?? "DOP", locale);
  const rows = new Map([...recordFactRows(dossier), ...fiscalFactRows(dossier.facts)].map((entry) => [entry.key, entry]));
  const row = (key: "net_amount" | "itbis" | "legal_tip" | "amount", label: string, amount: string | null | undefined) => {
    const standing = rows.get(key);
    const blocked = standing?.blocked;
    const asked = standing?.asked;
    const flagged = attention.some((item) => item.field === key);
    const total = key === "amount";
    const calculated = key === "net_amount" && net?.source === "calculated";
    const value = <span>{money(amount)}</span>;
    return <div key={key} data-fact={key} data-standing={standing?.standing} data-blocked={blocked || asked ? "true" : undefined} data-attention={flagged ? "true" : undefined} data-match={amount != null ? JSON.stringify([amount, money(amount)]) : undefined} className={`grid grid-cols-[minmax(7.5rem,34%)_minmax(0,1fr)] items-start gap-x-4 py-1.5 ${total ? "mt-1 border-t border-[#DCE0DA] pt-3 font-semibold dark:border-white/10" : ""}`}>
      <dt className="flex min-h-11 items-center gap-1.5 text-[13px] leading-[18px] text-[#56635e] dark:text-white/70">{flagged ? <span aria-hidden="true" data-testid="attention-marker" className="mr-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#c27a1e] dark:bg-[#e8b26f]" /> : null}{label}
        {calculated ? <Tooltip content={hint} side="top"><span tabIndex={0} aria-label={hint} data-testid="amount-calculated" className="text-[13px] font-normal text-[#56635e] dark:text-white/65">ƒ</span></Tooltip> : null}
        {total && mismatch ? <TriangleAlert data-testid="amounts-warning" className="h-3.5 w-3.5 shrink-0 text-[#9a650d] dark:text-[#e8b26f]" aria-hidden="true" /> : null}
      </dt>
      <dd className={`cuadrao-amount min-w-0 text-right text-[15px] leading-[22px] tabular-nums [&_button>span]:text-right ${total && mismatch ? "text-[#9a650d] dark:text-[#e8b26f]" : "text-[#172b26] dark:text-white"}`}>
        {review ? review.row(key, { label, value, layout: "amount" }) : <span data-number-box="" className={`${AMOUNT_BOX_CLASS} flex h-11 items-center justify-end border border-transparent px-3 text-[16px] leading-6`}>{value}</span>}
        {review?.note(key)}
        {(blocked || asked) && !(review && flagged) ? <span className="mt-1 block text-[13px] font-normal text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.dossier.needs_resolution")}</span> : null}
        {total && mismatch?.difference != null ? <span data-testid="amounts-difference" className={`${AMOUNT_BOX_CLASS} mt-1 block px-[13px] text-right text-[13px] font-normal`}>{t("business.terms.difference", { amount: formatAmount(mismatch.difference, currency ?? "DOP", locale) })}</span> : null}
      </dd>
    </div>;
  };
  const heading = <div className="flex min-h-6 items-center gap-2"><h3>{t("business.terms.montos_title")}{currency ? ` · ${currency}` : <span className="ml-2 text-[#9a650d] dark:text-[#e8b26f]">{t("business.terms.currency_missing")}</span>}</h3>{!currency && review?.onEdit ? <button type="button" className="text-[#9a650d] underline dark:text-[#e8b26f]" onClick={() => review.onEdit?.("currency")}>{t("business.terms.currency_choose")}</button> : null}</div>;
  return <section aria-busy={review?.amountsPreview?.status === "pending" || undefined} data-testid="receipt-facts-montos" aria-labelledby={id}>
    <div id={id} data-fact="currency" className="mb-1 text-[13px] font-medium leading-4 text-[#56635e] dark:text-white/60">
      {review ? review.row("currency", { label: t("business.dossier.field.currency"), layout: "currency", value: heading, compound: !currency, pencil: Boolean(currency) }) : heading}
      {review?.note("currency")}
    </div>
    <dl className="mt-1">
      {row("net_amount", t("business.terms.net_amount"), net?.amount)}
      {row("itbis", t("business.terms.itbis"), dossier.facts.fiscal?.itbis.value)}
      {tip != null ? row("legal_tip", t("business.terms.legal_tip"), tip) : null}
      {row("amount", t("business.terms.total_review"), dossier.facts.amount.value)}
    </dl>
  </section>;
}
