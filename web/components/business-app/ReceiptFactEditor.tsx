"use client";

import { useEffect, useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import MoneyInput from "@/components/money/MoneyInput";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessFacts, BusinessFactField, BusinessFactInput, BusinessFactPatch } from "@/lib/business-dossier";
import { RECEIPT_CATEGORY_IDS } from "./business-format";
import { DatePicker } from "./foundation/DatePicker";
import { useCategoryLabel } from "./business-ui";

const inputClass = "block min-h-11 w-full rounded-item border border-[#7d8a84] bg-[#FFFEFA] px-3 text-[16px] text-[#172b26] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] disabled:opacity-50 dark:bg-[#141517] dark:text-white";

export default function ReceiptFactEditor({ facts, accounts, currencies, disabled, field, patch, autoFocus, onChange }: {
  facts: BusinessFacts;
  accounts: BusinessAccount[];
  currencies: string[];
  disabled: boolean;
  field: BusinessFactField;
  autoFocus: boolean;
  patch: BusinessFactPatch;
  onChange: (patch: BusinessFactPatch, invalid: boolean) => void;
}) {
  const { t } = useTranslation();
  const controls = useRef<HTMLDivElement>(null);
  const dateId = useId();
  useEffect(() => {
    if (autoFocus) controls.current?.querySelector<HTMLInputElement | HTMLSelectElement>("input, select")?.focus();
  }, [autoFocus]);
  const categoryLabel = useCategoryLabel();
  const set = <K extends BusinessFactField>(key: K, value: BusinessFactInput<NonNullable<BusinessFacts[K]["value"]>>, invalid = false) => {
    onChange({ [key]: value } as BusinessFactPatch, invalid);
  };
  const scalar = (key: "counterparty" | "occurred_on" | "amount" | "currency" | "category_id") => (patch[key] ?? facts[key]).value ?? "";
  const setScalar = (key: "counterparty" | "occurred_on" | "amount" | "currency" | "category_id", value: string) => set(key, value ? { state: "known", value } : { state: "unknown", value: null });
  const kind = patch.kind ?? facts.kind;
  const funding = patch.funding ?? facts.funding;
  const fundingValue = funding.state === "owner_does_not_know" ? "owner_does_not_know" : funding.state !== "known" ? "" : funding.value.kind === "owner_funds" ? "owner_funds" : `account:${funding.value.account_id}`;
  const share = patch.business_share ?? facts.business_share;
  const receiptState = patch.receipt_state ?? facts.receipt_state;
  const label = (key: BusinessFactField) => t(`business.dossier.field.${key}`, key);
  const choose = t("business.review.choose", "Choose");

  return (
    <div ref={controls} className="space-y-3" data-testid={`edit-${field}`}>
      {field === "kind" ? <label className="block text-[13px] text-black/65 dark:text-white/65"><span className="sr-only">{label("kind")}</span><select className={inputClass} value={kind.value ?? ""} disabled={disabled} onChange={(event) => {
        if (event.target.value === "expense" || event.target.value === "income" || event.target.value === "refund") set("kind", { state: "known", value: event.target.value });
        else if (!event.target.value) set("kind", { state: "unknown", value: null });
        else if (facts.kind.state === "known" && event.target.value === facts.kind.value) set("kind", { state: "known", value: facts.kind.value });
      }}><option value="">{choose}</option>{(["expense", "income", "refund"] as const).map((kind) => <option key={kind} value={kind}>{t(`business.dossier.kind.${kind}`, kind)}</option>)}{facts.kind.state === "known" && !["expense", "income", "refund"].includes(facts.kind.value) ? <option value={facts.kind.value}>{t(`business.dossier.kind.${facts.kind.value}`, facts.kind.value)}</option> : null}</select></label> : null}
      {field === "counterparty" ? <label className="block text-[13px] text-black/65 dark:text-white/65"><span className="sr-only">{label("counterparty")}</span><input className={inputClass} value={scalar("counterparty")} disabled={disabled} onChange={(event) => setScalar("counterparty", event.target.value)} autoComplete="off" /></label> : null}
      {field === "occurred_on" ? <div><label htmlFor={dateId} className="sr-only">{label("occurred_on")}</label><DatePicker id={dateId} label={label("occurred_on")} value={(patch.occurred_on ?? facts.occurred_on).value ?? ""} disabled={disabled} onChange={(iso, invalid) => set("occurred_on", iso ? { state: "known", value: iso } : { state: "unknown", value: null }, invalid)} /></div> : null}
      {field === "currency" ? <label className="text-[13px] text-black/65 dark:text-white/65"><span className="sr-only">{label("currency")}</span><select className={inputClass} value={scalar("currency")} disabled={disabled} onChange={(event) => setScalar("currency", event.target.value)}><option value="">{choose}</option>{[...new Set([...currencies, ...(scalar("currency") ? [scalar("currency")] : [])])].map((currency) => <option key={currency}>{currency}</option>)}</select></label> : null}
      {field === "amount" ? <MoneyInput label={label("amount")} currency={scalar("currency")} value={scalar("amount") || null} disabled={disabled} onValueChange={({ value, invalid }) => { set("amount", value ? { state: "known", value } : { state: "unknown", value: null }, invalid); }} testId="dossier-review-amount" /> : null}
      {field === "funding" ? <label className="block text-[13px] text-black/65 dark:text-white/65"><span className="sr-only">{label("funding")}</span><select className={inputClass} value={fundingValue} disabled={disabled} onChange={(event) => {
        const value = event.target.value;
        if (!value || value === "owner_does_not_know") set("funding", { state: value === "owner_does_not_know" ? value : "unknown", value: null });
        else set("funding", { state: "known", value: value === "owner_funds" ? { kind: "owner_funds" } : { kind: "business_account", account_id: value.slice(8) } });
      }}><option value="">{choose}</option><option value="owner_does_not_know">{t("business.dossier.owner_unknown", "Owner doesn't know")}</option><option value="owner_funds">{t("business.dossier.owner_funds", "Owner's money")}</option>{accounts.map((account) => <option key={account.id} value={`account:${account.id}`}>{account.nickname ?? t("business.dossier.business_account", "Business account")} · {account.currency}</option>)}</select></label> : null}
      {field === "category_id" ? <label className="text-[13px] text-black/65 dark:text-white/65"><span className="sr-only">{label("category_id")}</span><select className={inputClass} value={scalar("category_id")} disabled={disabled} onChange={(event) => setScalar("category_id", event.target.value)}><option value="">{choose}</option>{RECEIPT_CATEGORY_IDS.map((id) => <option key={id} value={id}>{categoryLabel(id)}</option>)}</select></label> : null}
      {field === "receipt_state" ? (
        <fieldset disabled={disabled}>
          <legend className="sr-only">{label("receipt_state")}</legend>
          <div className="space-y-1">
            {(["fiscal_receipt", "informal_receipt", "no_receipt"] as const).map((value) => (
              <label key={value} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-item px-2 text-[15px] text-[#172b26] hover:bg-black/[0.03] has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-[#2f5a49] dark:text-white dark:hover:bg-white/[0.04]">
                <input type="radio" name={`receipt-state-${field}`} value={value} checked={receiptState.value === value} onChange={() => set("receipt_state", { state: "known", value })} className="h-4 w-4 accent-[#2f5a49]" />
                {t(`business.dossier.receipt.${value}`, value)}
              </label>
            ))}
          </div>
          <p className="mt-1 px-2 text-[13px] text-[#56635e] dark:text-white/70">{t("business.dossier.receipt_hint", "The last two stay out of the 606 and 607.")}</p>
        </fieldset>
      ) : null}
      {field === "business_share" ? <label className="block text-[13px] text-black/65 dark:text-white/65"><span className="sr-only">{label("business_share")}</span><select className={inputClass} value={share.state === "known" ? share.value.kind : ""} disabled={disabled} onChange={(event) => {
        const value = event.target.value;
        if (value === "all" || value === "none") set("business_share", { state: "known", value: { kind: value } });
        else if (value === "partial") set("business_share", { state: "known", value: { kind: "partial", amount: "" } }, true);
        else set("business_share", { state: "unknown", value: null });
      }}><option value="">{choose}</option>{["all", "none", "partial"].map((value) => <option key={value} value={value}>{t(`business.dossier.share.${value}`, value)}</option>)}</select></label> : null}
      {field === "business_share" && share.state === "known" && share.value.kind === "partial" ? <MoneyInput label={t("business.dossier.business_amount", "Business amount")} currency={scalar("currency")} value={share.value.amount || null} disabled={disabled} onValueChange={({ value, invalid }) => { set("business_share", { state: "known", value: { kind: "partial", amount: value ?? "" } }, invalid || !value); }} /> : null}
    </div>
  );
}
