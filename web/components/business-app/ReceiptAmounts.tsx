"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessDossier } from "@/lib/business-dossier";
import { resolveLanguage } from "@/lib/language-features";
import { formatAmount } from "./business-format";
import { dossierRowLabel, problemWords, rowProblems, type DossierProblem } from "./dossier-attention";
import { DossierCard, DossierRow, DossierRows, type RowStatus } from "./dossier/DossierParts";
import styles from "./dossier/dossier.module.css";
import type { FactsReview, RowFlash } from "./ReceiptRecordFacts";
import { doubtfulFields } from "./receipt-fact-rows";

type AmountRow = "net_amount" | "itbis" | "legal_tip" | "amount";

/**
 * The Montos card, last in General: Subtotal, ITBIS, Propina legal when the
 * receipt has one, and the Total. Numbers align right and carry no symbol; the
 * currency is the picker in the heading, as its ISO code. A calculated subtotal
 * says so in its status slot, and the Total carries the math check: when the
 * amounts do not add up, the server's difference is the Total's warning.
 */
export default function ReceiptAmounts({ dossier, review, problems = [], flash = null }: { dossier: BusinessDossier; review?: FactsReview; problems?: readonly DossierProblem[]; flash?: RowFlash | null }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const currency = dossier.facts.currency.value;
  const tip = dossier.facts.legal_tip?.value;
  const net = review?.amountsPreview?.net_amount ?? dossier.net_amount;
  const mismatch = review?.amountsPreview !== undefined ? review.amountsPreview?.mismatch : dossier.review_flags?.find((flag) => flag.code === "amounts_mismatch");
  const doubtful = doubtfulFields(dossier);
  const money = (amount: string | null | undefined) => amount == null ? "" : formatAmount(amount, currency ?? "DOP", locale);
  const picker = useRef<HTMLButtonElement>(null);
  const currencyFlash = flash?.row === "currency" ? flash.n : 0;
  useEffect(() => {
    if (currencyFlash) picker.current?.focus();
  }, [currencyFlash]);
  const status = (key: AmountRow): RowStatus | null => {
    if (key === "amount" && mismatch) return { kind: "warn", text: mismatch.difference != null ? t("business.terms.difference", { amount: formatAmount(mismatch.difference, currency ?? "DOP", locale) }) : t("business.terms.difference_unavailable") };
    if (key === "amount" && review?.amountsPreview?.status === "error") return { kind: "warn", text: t("business.terms.difference_unavailable") };
    const found = [...rowProblems(problems, key), ...(key === "amount" ? rowProblems(problems, "currency") : [])];
    if (found.length) return { kind: "warn", text: problemWords(found) };
    if (doubtful.has(key)) return { kind: "warn", text: t("business.dossier.placeholder.doubtful_read", "check this") };
    if (key === "net_amount" && net?.source === "calculated") return { kind: "calculated", text: t(tip != null ? "business.terms.calculated_hint_with_tip" : "business.terms.calculated_hint") };
    return null;
  };
  const row = (key: AmountRow, amount: string | null | undefined) => (
    <DossierRow
      key={key}
      row={key}
      label={dossierRowLabel(t, key, dossier)}
      look="number"
      total={key === "amount"}
      value={money(amount)}
      status={status(key)}
      edit={review?.edit(key)}
      below={review?.note(key)}
      flash={flash?.row === key ? flash.n : undefined}
      attention={rowProblems(problems, key).length > 0 || (key === "amount" && Boolean(mismatch))}
      match={amount != null ? JSON.stringify([amount, money(amount)]) : undefined}
    />
  );
  const currencyEdit = review?.edit("currency");
  const choose = currencyEdit?.onOpen;
  const heading = (
    <button ref={picker} type="button" data-fact="currency" data-testid="montos-currency" data-missing={currency ? undefined : true} className={styles.currency} disabled={!choose} aria-label={`${t("business.dossier.field.currency")}: ${currency ?? t("business.terms.currency_missing")}`} onClick={choose}>
      {currency ?? t("business.terms.currency_choose")}
      {choose ? <ChevronDown size={14} aria-hidden="true" /> : null}
    </button>
  );
  return (
    <DossierCard title={t("business.terms.montos_title")} aside={heading} testId="receipt-facts-montos">
      <div aria-busy={review?.amountsPreview?.status === "pending" || undefined}>
        <DossierRows>
          {currencyEdit?.open ? <DossierRow row="currency" label={t("business.dossier.field.currency")} value={currency ?? ""} edit={currencyEdit} below={review?.note("currency")} /> : null}
          {row("net_amount", net?.amount)}
          {row("itbis", dossier.facts.fiscal?.itbis.value)}
          {tip != null ? row("legal_tip", tip) : null}
          {row("amount", dossier.facts.amount.value)}
        </DossierRows>
        {!currencyEdit?.open && review?.note("currency") ? <div className={styles.cardBody}>{review.note("currency")}</div> : null}
      </div>
    </DossierCard>
  );
}
