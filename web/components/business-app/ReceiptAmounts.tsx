"use client";

import { ChevronDown, RotateCcw } from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessDossier } from "@/lib/business-dossier";
import { resolveLanguage } from "@/lib/language-features";
import { Tooltip } from "@/components/ui/Tooltip";
import { formatAmount } from "./business-format";
import { dossierRowLabel, problemWords, rowProblems, type DossierProblem } from "./dossier-attention";
import { DossierCard, DossierRow, DossierRows, SavedMark, type RowStatus } from "./dossier/DossierParts";
import styles from "./dossier/dossier.module.css";
import type { FactsReview, RowFlash } from "./ReceiptRecordFacts";
import { doubtfulFields } from "./receipt-fact-rows";

type AmountRow = "net_amount" | "itbis" | "legal_tip" | "amount";

/**
 * The Montos card, last in General: Subtotal, ITBIS, Propina legal when the
 * receipt has one, and the Total. Numbers align right and carry no symbol; the
 * currency is the picker in the heading, as its ISO code. The server says who
 * gave the Subtotal: one it calculated says so in its status slot, and one a
 * person typed offers the way back to it there. The Total carries the server's
 * math check: a check when the amounts add up, the difference as a warning
 * when they do not, and nothing while it has not checked.
 */
export default function ReceiptAmounts({ dossier, review, problems = [], flash = null }: { dossier: BusinessDossier; review?: FactsReview; problems?: readonly DossierProblem[]; flash?: RowFlash | null }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const currency = dossier.facts.currency.value;
  const tip = dossier.facts.legal_tip?.value;
  const net = review?.amountsPreview?.net_amount ?? dossier.net_amount;
  // While a person types, the preview says what the amounts would leave over. It never says they add up.
  const previewed = review?.amountsPreview !== undefined;
  const check = dossier.amounts_check;
  const mismatch = previewed ? review?.amountsPreview?.mismatch : check?.state === "difference" ? check : null;
  const addsUp = !previewed && check?.state === "adds_up";
  const doubtful = doubtfulFields(dossier);
  const money = (amount: string | null | undefined) => amount == null ? "" : formatAmount(amount, currency ?? "DOP", locale);
  const picker = useRef<HTMLButtonElement>(null);
  const currencyFlash = flash?.row === "currency" ? flash.n : 0;
  useEffect(() => {
    if (currencyFlash) picker.current?.focus();
  }, [currencyFlash]);
  const currencyEdit = review?.edit("currency");
  const status = (key: AmountRow): RowStatus | null => {
    if (key === "amount" && mismatch) return { kind: "warn", text: mismatch.difference != null ? t("business.terms.difference", { amount: formatAmount(mismatch.difference, currency ?? "DOP", locale) }) : t("business.terms.difference_unavailable") };
    if (key === "amount" && review?.amountsPreview?.status === "error") return { kind: "warn", text: t("business.terms.difference_unavailable") };
    const found = [...rowProblems(problems, key), ...(key === "amount" ? rowProblems(problems, "currency") : [])];
    if (found.length) return { kind: "warn", text: problemWords(found) };
    if (doubtful.has(key)) return { kind: "warn", text: t("business.dossier.placeholder.doubtful_read", "check this") };
    if (key === "net_amount" && net?.source === "calculated") return { kind: "calculated", text: t(tip != null ? "business.terms.calculated_hint_with_tip" : "business.terms.calculated_hint") };
    if (key === "amount" && addsUp) return { kind: "ok", text: t(tip != null ? "business.terms.total_adds_up_with_tip" : "business.terms.total_adds_up") };
    return null;
  };
  const restoreLabel = t("business.dossier.placeholder.restore_calculated");
  const restoreSubtotal = dossier.net_amount?.source === "edited" && review?.restoreSubtotal && !review.edit("net_amount").open
    ? <Tooltip content={restoreLabel} side="top"><button type="button" aria-label={restoreLabel} data-restore-calculated="net_amount" className={styles.pen} style={{ opacity: 1, width: 24, height: 24 }} onClick={review.restoreSubtotal}><RotateCcw size={14} aria-hidden="true" /></button></Tooltip>
    : null;
  const row = (key: AmountRow, amount: string | null | undefined) => (
    <DossierRow
      key={key}
      row={key}
      label={dossierRowLabel(t, key, dossier)}
      look="number"
      total={key === "amount"}
      value={money(amount)}
      status={status(key)}
      statusAction={key === "net_amount" ? restoreSubtotal : undefined}
      edit={review?.edit(key)}
      below={review?.note(key)}
      flash={flash?.row === key ? flash.n : undefined}
      attention={rowProblems(problems, key).length > 0 || (key === "amount" && Boolean(mismatch))}
      match={amount != null ? JSON.stringify([amount, money(amount)]) : undefined}
    />
  );
  const choose = currencyEdit?.onOpen;
  const heading = (<span className="flex items-center gap-2">
    {currencyEdit?.saved && !currencyEdit.open ? <SavedMark /> : null}
    <button ref={picker} type="button" data-fact="currency" data-testid="montos-currency" data-missing={currency ? undefined : true} className={styles.currency} disabled={!choose} aria-label={`${t("business.dossier.field.currency")}: ${currency ?? t("business.terms.currency_missing")}`} onClick={choose}>
      {currency ?? t("business.terms.currency_choose")}
      {choose ? <ChevronDown size={14} aria-hidden="true" /> : null}
    </button>
  </span>);
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
