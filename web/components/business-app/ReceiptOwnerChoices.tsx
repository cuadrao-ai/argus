"use client";

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessDossier, DeclarationSuggestion, ShownSuggestions } from "@/lib/business-dossier";
import type { DgiiField, DgiiFields, PurchaseChoice, SuggestedField, SuggestionSource } from "@/lib/business-dgii";
import { quietButtonClass } from "./business-ui";
import { DossierCard, DossierPickRow, DossierRow, DossierRows, type RowStatus } from "./dossier/DossierParts";
import { recordForm } from "./dossier/fiscal-rows";
import type { SaleChoice } from "./receipt-fact-rows";

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

/** How one choice saves: absent for someone who cannot write the report's answers now. */
export type ChoicePick = { onPick: (value: string) => void; saving: boolean; saved: boolean; disabled: boolean };
/** A row of the report card: one of the 606's two answers, or one of the 607's. */
export type ReportChoice = Choice | SaleChoice;
type Answer = { row: ReportChoice; label: string; value: string; codes: readonly string[] | null; name: (code: string) => string; source?: SuggestionSource | null; suggested?: DeclarationSuggestion | null };

/**
 * The report card of General, from the server's codes and the locale's text. A
 * purchase answers tipo de gasto and forma de pago; a sale answers tipo de
 * ingreso and its one forma de pago, whose whole amount the server places.
 * None blocks approval. Each is a row that opens its list and saves the pick
 * at once. A suggestion shows filled, with an icon for its source in the
 * status slot, and the approval saves it; a value the person chose has no icon.
 */
export default function ReceiptOwnerChoices({ dossier, fields, failed, readOnly = false, pick, note, onReload }: ChoicesView & {
  pick: (choice: ReportChoice) => ChoicePick;
  note: (choice: ReportChoice) => ReactNode;
  onReload: () => void;
}) {
  const { t } = useTranslation();
  // The type names the report, not a declaration left from the other one.
  const form = recordForm(dossier);
  const sourceStatus = (from: SuggestionSource): RowStatus => ({ kind: from, text: t(`business.dossier.placeholder.suggestion_source.${from}`) });
  const option = (field: string) => (code: string) => t(`business.dgii.option.${field}.${code}`, { defaultValue: code }) || code;
  const purchase = (choice: Choice, label: string): Answer => {
    const { value, source } = shownChoice({ dossier, fields, failed, readOnly }, choice);
    return { row: choice, label, value, source, codes: catalogField(fields, choice)?.options ?? null, name: option(choice), suggested: dossier.declaration_suggestions?.[choice] };
  };
  const answers: Answer[] = form === "607" ? [
    { row: "income_type", label: t("business.dossier.placeholder.income_type"), value: dossier.dgii?.form === "607" ? String(dossier.dgii.income_type ?? "") : "", codes: fields?.["607"].find((item) => item.name === "income_type")?.options ?? null, name: option("income_type") },
    { row: "sale_payment", label: t("business.dossier.placeholder.payment_form"), value: dossier.sale_payment?.form ?? "", codes: dossier.sale_payment?.options ?? null, name: option("sale_payment_form") },
  ] : [
    purchase("category", t("business.dossier.placeholder.expense_type", "Expense type")),
    purchase("payment_method", t("business.dossier.placeholder.payment_form", "Payment method")),
  ];
  const row = ({ row: choice, label, value, codes, name, source, suggested }: Answer) => {
    const status = source ? sourceStatus(source) : null;
    const data = { "data-suggestion-source": source ?? undefined };
    if (!codes || readOnly) return <DossierRow key={choice} row={choice} label={label} status={status} value={value ? name(value) : ""} below={note(choice)} data={data} />;
    const options = codes.map((code) => ({ value: code, label: name(code), status: suggested?.value === code ? sourceStatus(suggested.source) : null }));
    return <DossierPickRow key={choice} row={choice} label={label} status={status} value={value ? name(value) : ""} pick={{ value, options, ...pick(choice) }} below={note(choice)} data={data} />;
  };
  return (
    <DossierCard title={t("business.dossier.card.report", { form })} testId="receipt-facts-choices">
      {failed ? <p role="alert" className="py-3 text-[13px] leading-[18px] text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.dgii.load_failed", "We couldn't load the tax fields.")}<button type="button" className={`${quietButtonClass} ml-2`} onClick={onReload}>{t("common.retry", "Retry")}</button></p> : <DossierRows>{answers.map(row)}</DossierRows>}
    </DossierCard>
  );
}
