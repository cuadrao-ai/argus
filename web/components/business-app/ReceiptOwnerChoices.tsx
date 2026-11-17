"use client";

import { History, ReceiptText, SquareSparkles, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { BusinessDossier, ShownSuggestions } from "@/lib/business-dossier";
import type { DgiiField, DgiiFields, PurchaseChoice, SuggestedField, SuggestionSource } from "@/lib/business-dgii";
import { UNKNOWN_VALUE } from "./business-format";
import { quietButtonClass } from "./business-ui";
import { ReviewSelect } from "./ReceiptFieldControls";
import { FACT_LABEL_CLASS, FACT_ROW_CLASS } from "./ReceiptRecordFacts";
import ReceiptRowSave from "./ReceiptRowSave";
import type { RowSave, SaveRow } from "./receipt-review-save";

type Choice = keyof PurchaseChoice;
const CHOICES: readonly SuggestedField[] = ["category", "payment_method"];
const SOURCE_ICON: Record<SuggestionSource, LucideIcon> = { last_choice: History, receipt: ReceiptText, reading: SquareSparkles };

/** The answer the record holds. A legacy unconfirmed tipo de gasto is no answer. */
function savedChoice(dossier: BusinessDossier, choice: Choice): string {
  const declared = dossier.dgii;
  return choice === "category" && declared?.category_suggested === true ? "" : String(declared?.[choice] ?? "");
}

/** What a 606 answer shows: the saved value, else the server's suggestion, with where it came from. */
function shownChoice(dossier: BusinessDossier, choice: Choice): { value: string; source: SuggestionSource | null } {
  const saved = savedChoice(dossier, choice);
  if (saved) return { value: saved, source: dossier.dgii?.suggestion_sources?.[choice] ?? null };
  const suggestion = dossier.declaration_suggestions?.[choice] ?? null;
  return suggestion ? { value: suggestion.value, source: suggestion.source } : { value: "", source: null };
}

/** The suggestions the screen shows filled in: what the approve request carries so the approval saves them. */
export function shownSuggestions(dossier: BusinessDossier): ShownSuggestions | undefined {
  const shown = CHOICES.flatMap((choice) => {
    const suggestion = dossier.declaration_suggestions?.[choice];
    return suggestion && !savedChoice(dossier, choice) ? [[choice, suggestion] as const] : [];
  });
  return shown.length ? Object.fromEntries(shown) : undefined;
}

function SourceChip({ source }: { source: SuggestionSource }) {
  const { t } = useTranslation();
  const Icon = SOURCE_ICON[source];
  const label = t(`business.dossier.placeholder.suggestion_source.${source}`);
  return (
    <span role="img" aria-label={label} title={label} data-suggestion-source={source} className="inline-flex h-6 w-6 flex-none items-center justify-center rounded-full bg-[#eceeea] text-[#56635e] dark:bg-white/10 dark:text-white/80">
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
    </span>
  );
}

/**
 * Tipo de gasto and forma de pago, from the server's codes and the locale's text. Neither
 * blocks approval. A suggestion shows filled, with an icon for its source, and the approval
 * saves it; a value the person chose has no icon.
 */
export default function ReceiptOwnerChoices({ dossier, fields, failed, disabled, readOnly = false, saves, onChoose, onRetry, onCancel, onReload }: {
  dossier: BusinessDossier;
  fields: DgiiFields | null;
  /** The codes could not be loaded. */
  failed: boolean;
  disabled: boolean;
  /** The values as text, with no control. */
  readOnly?: boolean;
  saves: Partial<Record<SaveRow, RowSave>>;
  onChoose: (choice: Choice, value: string | null) => void;
  onRetry: (choice: Choice) => void;
  onCancel: (choice: Choice) => void;
  onReload: () => void;
}) {
  const { t } = useTranslation();
  const row = (choice: Choice, label: string) => {
    const field: DgiiField | undefined = fields?.["606"].find((item) => item.name === choice);
    const { value, source } = shownChoice(dossier, choice);
    const name = (code: string) => t(`business.dgii.option.${choice}.${code}`, { defaultValue: code }) || code;
    const chip = source ? <SourceChip source={source} /> : null;
    if (readOnly) return (
      <div key={choice} data-fact={choice} className={FACT_ROW_CLASS}>
        <dt className={FACT_LABEL_CLASS}>{label}</dt>
        <dd className="flex min-w-0 items-center gap-2 py-[7px] text-[15px] leading-[22px] text-[#172b26] dark:text-white"><span className="min-w-0 break-words">{value ? name(value) : UNKNOWN_VALUE}</span>{chip}</dd>
      </div>
    );
    return (
      <div key={choice} data-fact={choice} className={FACT_ROW_CLASS}>
        <dt className={FACT_LABEL_CLASS}>{label}</dt>
        <dd className="min-w-0 py-1">
          {field ? <label className="block"><span className="sr-only">{label}</span>
            <ReviewSelect value={value} disabled={disabled} adornment={chip} onChange={(event) => onChoose(choice, event.target.value || null)}>
              <option value="">{t("business.review.choose", "Choose")}</option>
              {field.options.map((code) => <option key={code} value={code}>{name(code)}</option>)}
            </ReviewSelect>
          </label> : null}
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
