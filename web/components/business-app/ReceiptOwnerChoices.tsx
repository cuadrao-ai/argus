"use client";

import { useTranslation } from "react-i18next";
import type { BusinessDossier } from "@/lib/business-dossier";
import type { DgiiField, DgiiFields, PurchaseChoice } from "@/lib/business-dgii";
import { quietButtonClass } from "./business-ui";
import { FACT_LABEL_CLASS, FACT_ROW_CLASS } from "./ReceiptRecordFacts";
import ReceiptRowSave from "./ReceiptRowSave";
import type { RowSave, SaveRow } from "./receipt-review-save";

type Choice = keyof PurchaseChoice;
const inputClass = "block min-h-11 w-full rounded-item border border-[#7d8a84] bg-[#FFFEFA] px-3 text-[16px] text-[#172b26] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] disabled:opacity-50 dark:bg-[#141517] dark:text-white";

/**
 * Tipo de gasto and forma de pago, from the server's codes and labels. Neither
 * blocks approval. A suggested tipo de gasto stays a suggestion until a person
 * takes it, because only a person's write reaches the 606.
 */
export default function ReceiptOwnerChoices({ dossier, fields, failed, disabled, saves, onChoose, onRetry, onCancel, onReload }: {
  dossier: BusinessDossier;
  fields: DgiiFields | null;
  /** The labels could not be loaded. */
  failed: boolean;
  disabled: boolean;
  saves: Partial<Record<SaveRow, RowSave>>;
  onChoose: (choice: Choice, value: string | null) => void;
  onRetry: (choice: Choice) => void;
  onCancel: (choice: Choice) => void;
  onReload: () => void;
}) {
  const { t } = useTranslation();
  const row = (choice: Choice, label: string) => {
    const field: DgiiField | undefined = fields?.["606"].find((item) => item.name === choice);
    const value = String(dossier.dgii?.[choice] ?? "");
    const name = (code: string) => field?.labels?.[code] ?? code;
    const suggestion = choice === "category" && !value ? dossier.expense_type_suggestion : null;
    return (
      <div key={choice} data-fact={choice} className={FACT_ROW_CLASS}>
        <dt className={FACT_LABEL_CLASS}>{label}</dt>
        <dd className="min-w-0 py-1">
          {field ? <label className="block"><span className="sr-only">{label}</span>
            <select className={inputClass} value={value} disabled={disabled} onChange={(event) => onChoose(choice, event.target.value || null)}>
              <option value="">{t("business.review.choose", "Choose")}</option>
              {field.options.map((code) => <option key={code} value={code}>{name(code)}</option>)}
            </select>
          </label> : null}
          {suggestion && field ? <p data-testid="expense-type-suggestion" className="mt-1 flex flex-wrap items-center gap-x-2 text-[13px] leading-[18px] text-[#56635e] dark:text-white/70">{t("business.dgii.suggested", "Suggested")}: {name(suggestion)}{disabled ? null : <button type="button" className={quietButtonClass} onClick={() => onChoose(choice, suggestion)}>{t("business.dossier.placeholder.use_suggestion", "Use")}</button>}</p> : null}
          <ReceiptRowSave save={saves[choice]} onRetry={() => onRetry(choice)} onCancel={() => onCancel(choice)} />
        </dd>
      </div>
    );
  };
  if (failed) return <p role="alert" className="py-2 text-[13px] leading-[18px] text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.dgii.load_failed", "We couldn't load the tax fields.")}<button type="button" className={`${quietButtonClass} ml-2`} onClick={onReload}>{t("common.retry", "Retry")}</button></p>;
  return <>
    {row("category", t("business.dossier.placeholder.expense_type", "Expense type"))}
    {row("payment_method", t("business.dossier.placeholder.payment_form", "Payment method"))}
  </>;
}
