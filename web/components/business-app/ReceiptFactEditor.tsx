"use client";

import { useEffect, useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import MoneyInput from "@/components/money/MoneyInput";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessFacts, BusinessFactField, BusinessFactInput, BusinessFactPatch } from "@/lib/business-dossier";
import { DatePicker } from "./foundation/DatePicker";
import { REVIEW_INPUT_CLASS, ReviewSelect } from "./ReceiptFieldControls";
import { DOCUMENT_TYPE_LABELS, type DocumentType, type ReviewRow } from "./receipt-fact-rows";

export default function ReceiptFactEditor({ facts, accounts, currencies, disabled, field, patch, fiscal = "", documentType, uploadedAt = null, tried, onChange, onFiscalChange, onDocumentTypeChange, fiscalForm }: {
  fiscalForm?: "606" | "607";
  facts: BusinessFacts;
  accounts: BusinessAccount[];
  currencies: string[];
  disabled: boolean;
  field: ReviewRow;
  /** A save was refused because this value cannot be sent. */
  tried: boolean;
  patch: BusinessFactPatch;
  /** The typed value of a fiscal row. */
  fiscal?: string;
  /** The chosen type of the type row. */
  documentType?: DocumentType;
  /** When the server received the document, which tells the date field the upload year. */
  uploadedAt?: string | null;
  onChange: (patch: BusinessFactPatch, invalid: boolean) => void;
  onFiscalChange?: (value: string, invalid: boolean) => void;
  onDocumentTypeChange?: (value: DocumentType) => void;
}) {
  const { t } = useTranslation();
  const controls = useRef<HTMLDivElement>(null);
  const dateId = useId();
  useEffect(() => {
    controls.current?.querySelector<HTMLInputElement | HTMLSelectElement>("input, select")?.focus();
  }, []);
  const set = <K extends BusinessFactField>(key: K, value: BusinessFactInput<NonNullable<NonNullable<BusinessFacts[K]>["value"]>>, invalid = false) => {
    onChange({ [key]: value } as BusinessFactPatch, invalid);
  };
  const scalar = (key: "counterparty" | "occurred_on" | "amount" | "currency") => (patch[key] ?? facts[key]).value ?? "";
  const setScalar = (key: "counterparty" | "occurred_on" | "amount" | "currency", value: string) => set(key, value ? { state: "known", value } : { state: "unknown", value: null });
  const kind = patch.kind ?? facts.kind;
  const funding = patch.funding ?? facts.funding;
  const fundingValue = funding.state === "owner_does_not_know" ? "owner_does_not_know" : funding.state !== "known" ? "" : funding.value.kind === "owner_funds" ? "owner_funds" : `account:${funding.value.account_id}`;
  const share = patch.business_share ?? facts.business_share;
  const label = (key: BusinessFactField) => t(`business.dossier.field.${key}`, key);
  const choose = t("business.review.choose", "Choose");

  return (
    <div ref={controls} className="space-y-3" data-testid={`edit-${field}`}>
      {field === "document_type" ? <label className="block text-[13px] text-black/65 dark:text-white/65"><span className="sr-only">{t("business.dossier.type_label", "Type")}</span><ReviewSelect value={documentType} disabled={disabled} onChange={(event) => onDocumentTypeChange?.(event.target.value as DocumentType)}>{(Object.keys(DOCUMENT_TYPE_LABELS) as DocumentType[]).map((type) => <option key={type} value={type}>{t(DOCUMENT_TYPE_LABELS[type])}</option>)}</ReviewSelect></label> : null}
      {field === "kind" ? <label className="block text-[13px] text-black/65 dark:text-white/65"><span className="sr-only">{label("kind")}</span><ReviewSelect value={kind.value ?? ""} disabled={disabled} onChange={(event) => {
        if (event.target.value === "expense" || event.target.value === "income" || event.target.value === "refund") set("kind", { state: "known", value: event.target.value });
        else if (!event.target.value) set("kind", { state: "unknown", value: null });
        else if (facts.kind.state === "known" && event.target.value === facts.kind.value) set("kind", { state: "known", value: facts.kind.value });
      }}><option value="">{choose}</option>{(["expense", "income", "refund"] as const).map((kind) => <option key={kind} value={kind}>{t(`business.dossier.kind.${kind}`, kind)}</option>)}{facts.kind.state === "known" && !["expense", "income", "refund"].includes(facts.kind.value) ? <option value={facts.kind.value}>{t(`business.dossier.kind.${facts.kind.value}`, facts.kind.value)}</option> : null}</ReviewSelect></label> : null}
      {field === "counterparty" ? <label className="block text-[13px] text-black/65 dark:text-white/65"><span className="sr-only">{label("counterparty")}</span><input className={REVIEW_INPUT_CLASS} value={scalar("counterparty")} disabled={disabled} onChange={(event) => setScalar("counterparty", event.target.value)} autoComplete="off" /></label> : null}
      {field === "occurred_on" ? <div><label htmlFor={dateId} className="sr-only">{label("occurred_on")}</label><DatePicker id={dateId} label={label("occurred_on")} context={{ kind: "document", uploadedAt }} value={(patch.occurred_on ?? facts.occurred_on).value ?? ""} disabled={disabled} onChange={(iso, invalid) => set("occurred_on", iso ? { state: "known", value: iso } : { state: "unknown", value: null }, invalid)} />{tried ? <p role="alert" className="mt-1 text-[13px] leading-5 text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.date_range.invalid_date", { format: t("business.date_picker.placeholder", "dd/mm/aaaa"), defaultValue: "Enter a valid date as {{format}}." })}</p> : null}</div> : null}
      {field === "currency" ? <div><label className="block"><span className="sr-only">{label("currency")}</span><ReviewSelect value={scalar("currency")} disabled={disabled} onChange={(event) => setScalar("currency", event.target.value)}><option value="">{choose}</option>{currencies.map((currency) => <option key={currency}>{currency}</option>)}</ReviewSelect></label>{fiscalForm && scalar("currency") && scalar("currency") !== "DOP" ? <p role="status" className="mt-2 text-[13px] font-normal text-[#9a650d] dark:text-[#e8b26f]">{t("business.terms.currency_fiscal_warning", { currency: scalar("currency"), form: fiscalForm })}</p> : null}</div> : null}
      {field === "amount" ? <MoneyInput flush numberOnly label={t("business.terms.total_review")} currency={scalar("currency")} value={scalar("amount") || null} disabled={disabled} onValueChange={({ value, invalid }) => set("amount", value ? { state: "known", value } : { state: "unknown", value: null }, invalid)} testId="dossier-review-amount" /> : null}
      {field === "net_amount" || field === "legal_tip" ? <MoneyInput flush numberOnly label={t(`business.terms.${field}`)} currency={scalar("currency")} value={(patch[field] ?? facts[field])?.value ?? null} allowZero disabled={disabled} onValueChange={({ value, invalid }) => set(field, value ? { state: "known", value } : { state: "unknown", value: null }, invalid)} testId={`dossier-review-${field}`} /> : null}
      {field === "itbis" ? <MoneyInput flush numberOnly label={t("business.terms.itbis")} currency={scalar("currency")} value={fiscal || null} allowZero disabled={disabled} onValueChange={({ value, invalid }) => onFiscalChange?.(value ?? "", invalid)} testId="dossier-review-itbis" /> : null}
      {field === "rnc" || field === "fiscal_number" ? <label className="block text-[13px] text-black/65 dark:text-white/65"><span className="sr-only">{field === "rnc" ? t("business.dossier.field.rnc", "RNC") : `${t("business.dossier.field.ncf", "NCF")} / ${t("business.dossier.field.ecf", "e-CF")}`}</span><input className={`${REVIEW_INPUT_CLASS} tabular-nums`} value={fiscal} disabled={disabled} inputMode={field === "rnc" ? "numeric" : undefined} autoCapitalize={field === "rnc" ? undefined : "characters"} autoComplete="off" onChange={(event) => onFiscalChange?.(event.target.value, false)} /></label> : null}
      {field === "funding" ? <label className="block text-[13px] text-black/65 dark:text-white/65"><span className="sr-only">{label("funding")}</span><ReviewSelect value={fundingValue} disabled={disabled} onChange={(event) => {
        const value = event.target.value;
        if (!value || value === "owner_does_not_know") set("funding", { state: value === "owner_does_not_know" ? value : "unknown", value: null });
        else set("funding", { state: "known", value: value === "owner_funds" ? { kind: "owner_funds" } : { kind: "business_account", account_id: value.slice(8) } });
      }}><option value="">{choose}</option><option value="owner_does_not_know">{t("business.dossier.owner_unknown", "Owner doesn't know")}</option><option value="owner_funds">{t("business.dossier.owner_funds", "Owner's money")}</option>{accounts.map((account) => <option key={account.id} value={`account:${account.id}`}>{account.nickname ?? t("business.dossier.business_account", "Business account")} · {account.currency}</option>)}</ReviewSelect></label> : null}
      {field === "business_share" ? <label className="block text-[13px] text-black/65 dark:text-white/65"><span className="sr-only">{label("business_share")}</span><ReviewSelect value={share.state === "known" ? share.value.kind : ""} disabled={disabled} onChange={(event) => {
        const value = event.target.value;
        if (value === "all" || value === "none") set("business_share", { state: "known", value: { kind: value } });
        else if (value === "partial") set("business_share", { state: "known", value: { kind: "partial", amount: "" } }, true);
        else set("business_share", { state: "unknown", value: null });
      }}><option value="">{choose}</option>{["all", "none", "partial"].map((value) => <option key={value} value={value}>{t(`business.dossier.share.${value}`, value)}</option>)}</ReviewSelect></label> : null}
      {field === "business_share" && share.state === "known" && share.value.kind === "partial" ? <MoneyInput label={t("business.dossier.business_amount", "Business amount")} currency={scalar("currency")} value={share.value.amount || null} disabled={disabled} onValueChange={({ value, invalid }) => { set("business_share", { state: "known", value: { kind: "partial", amount: value ?? "" } }, invalid || !value); }} /> : null}
    </div>
  );
}
