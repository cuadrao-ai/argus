"use client";

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessDossier, DeclarationSuggestion, ShownSuggestions } from "@/lib/business-dossier";
import type { DgiiField, DgiiFields, PurchaseChoice, SuggestedField, SuggestionSource } from "@/lib/business-dgii";
import { quietButtonClass } from "./business-ui";
import { DossierCard, DossierRow, DossierRows, type RowEdit, type RowStatus } from "./dossier/DossierParts";

type Choice = keyof PurchaseChoice;
const CHOICES: readonly SuggestedField[] = ["category", "payment_method"];

/** The answer the record holds. A legacy unconfirmed tipo de gasto is no answer. */
function savedChoice(dossier: BusinessDossier, choice: Choice): string {
  const declared = dossier.dgii;
  return choice === "category" && declared?.category_suggested === true ? "" : String(declared?.[choice] ?? "");
}

/** What the rows draw from: the record, the field codes, and whether those failed to load. */
export type ChoicesView = { dossier: BusinessDossier; fields: DgiiFields | null; failed: boolean; readOnly?: boolean };

function catalogField(fields: DgiiFields | null, choice: Choice): DgiiField | undefined {
  return fields?.["606"].find((item) => item.name === choice);
}

/**
 * What a 606 answer's row shows: the saved value, else the server's suggestion with where it
 * came from. A suggestion counts only when the row draws it: as text when read only, else as
 * an option of a loaded select. While the codes load or after they failed, nothing is shown.
 */
function shownChoice({ dossier, fields, failed, readOnly }: ChoicesView, choice: Choice): { value: string; source: SuggestionSource | null; suggestion: DeclarationSuggestion | null } {
  const saved = savedChoice(dossier, choice);
  if (saved) return { value: saved, source: dossier.dgii?.suggestion_sources?.[choice] ?? null, suggestion: null };
  const suggestion = dossier.declaration_suggestions?.[choice] ?? null;
  const drawn = suggestion && !failed && (readOnly || catalogField(fields, choice)?.options.includes(suggestion.value));
  return drawn ? { value: suggestion.value, source: suggestion.source, suggestion } : { value: "", source: null, suggestion: null };
}

/** The suggestions the rows show filled in: what the approve request carries so the approval saves them. */
export function shownSuggestions(view: ChoicesView): ShownSuggestions | undefined {
  const shown = CHOICES.flatMap((choice) => {
    const { suggestion } = shownChoice(view, choice);
    return suggestion ? [[choice, suggestion] as const] : [];
  });
  return shown.length ? Object.fromEntries(shown) : undefined;
}

/**
 * The report card of General: tipo de gasto and forma de pago, from the server's codes and
 * the locale's text. Neither blocks approval. A suggestion shows filled, with an icon for its
 * source in the status slot, and the approval saves it; a value the person chose has no icon.
 */
export default function ReceiptOwnerChoices({ dossier, fields, failed, readOnly = false, edit, note, onReload }: ChoicesView & {
  edit: (choice: Choice, label: string, value: string, source: SuggestionSource | null, options: ReactNode) => RowEdit;
  note: (choice: Choice) => ReactNode;
  onReload: () => void;
}) {
  const { t } = useTranslation();
  const row = (choice: Choice, label: string) => {
    const field = catalogField(fields, choice);
    const { value, source } = shownChoice({ dossier, fields, failed, readOnly }, choice);
    const name = (code: string) => t(`business.dgii.option.${choice}.${code}`, { defaultValue: code }) || code;
    const status: RowStatus | null = source ? { kind: source, text: t(`business.dossier.placeholder.suggestion_source.${source}`) } : null;
    const options = field?.options.map((code) => <option key={code} value={code}>{name(code)}</option>);
    return <DossierRow key={choice} row={choice} label={label} status={status} value={value ? name(value) : ""} edit={field && !readOnly ? edit(choice, label, value, source, options) : undefined} below={note(choice)} data={{ "data-suggestion-source": source ?? undefined }} />;
  };
  const form = dossier.dgii?.form ?? (dossier.document_type === "venta" ? "607" : "606");
  return (
    <DossierCard title={t("business.dossier.card.report", { form })} testId="receipt-facts-choices">
      {failed ? <p role="alert" className="py-3 text-[13px] leading-[18px] text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.dgii.load_failed", "We couldn't load the tax fields.")}<button type="button" className={`${quietButtonClass} ml-2`} onClick={onReload}>{t("common.retry", "Retry")}</button></p> : <DossierRows>
        {row("category", t("business.dossier.placeholder.expense_type", "Expense type"))}
        {row("payment_method", t("business.dossier.placeholder.payment_form", "Payment method"))}
      </DossierRows>}
    </DossierCard>
  );
}
