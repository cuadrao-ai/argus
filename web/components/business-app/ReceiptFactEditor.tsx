"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import MoneyInput from "@/components/money/MoneyInput";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessFacts, BusinessFactField, BusinessFactInput, BusinessFactPatch } from "@/lib/business-dossier";
import { RECEIPT_CATEGORY_IDS } from "./business-format";
import { secondaryButtonClass, useCategoryLabel } from "./business-ui";

const inputClass = "mt-1.5 block min-h-11 w-full rounded-[12px] border border-black/10 bg-white px-3 text-[16px] text-black outline-none focus-visible:ring-2 focus-visible:ring-black/20 disabled:opacity-50 dark:border-white/10 dark:bg-[#141517] dark:text-white dark:focus-visible:ring-white/20";

export default function ReceiptFactEditor({ facts, accounts, currencies, disabled, onChange, onSave, onCancel }: {
  facts: BusinessFacts;
  accounts: BusinessAccount[];
  currencies: string[];
  disabled: boolean;
  onChange: (changed: boolean) => void;
  onSave: (patch: BusinessFactPatch) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const categoryLabel = useCategoryLabel();
  const [patch, setPatch] = useState<BusinessFactPatch>({});
  const [amountInvalid, setAmountInvalid] = useState(false);
  const [shareInvalid, setShareInvalid] = useState(false);
  const set = <K extends BusinessFactField>(key: K, value: BusinessFactInput<NonNullable<BusinessFacts[K]["value"]>>) => {
    setPatch((current) => ({ ...current, [key]: value }));
    onChange(true);
  };
  const scalar = (key: "counterparty" | "occurred_on" | "amount" | "currency" | "category_id") => (patch[key] ?? facts[key]).value ?? "";
  const setScalar = (key: "counterparty" | "occurred_on" | "amount" | "currency" | "category_id", value: string) => set(key, value ? { state: "known", value } : { state: "unknown", value: null });
  const kind = patch.kind ?? facts.kind;
  const funding = patch.funding ?? facts.funding;
  const fundingValue = funding.state === "owner_does_not_know" ? "owner_does_not_know" : funding.state !== "known" ? "" : funding.value.kind === "owner_funds" ? "owner_funds" : `account:${funding.value.account_id}`;
  const share = patch.business_share ?? facts.business_share;
  const receiptState = patch.receipt_state ?? facts.receipt_state;
  const label = (key: BusinessFactField) => t(`business.dossier.field.${key}`, key);
  const choose = t("business.dossier.unknown", "Unknown");
  const cannotSave = disabled || amountInvalid || shareInvalid || !Object.keys(patch).length || (share.state === "known" && share.value.kind === "partial" && !share.value.amount);

  return (
    <form onSubmit={(event) => { event.preventDefault(); if (!cannotSave) onSave(patch); }} className="space-y-4" aria-label={t("business.dossier.edit", "Edit details")}>
      <label className="block text-[13px] text-black/65 dark:text-white/65">{label("kind")}<select className={inputClass} value={kind.value ?? ""} disabled={disabled} onChange={(event) => {
        if (event.target.value === "expense") set("kind", { state: "known", value: "expense" });
        else if (!event.target.value) set("kind", { state: "unknown", value: null });
        else if (facts.kind.state === "known" && event.target.value === facts.kind.value) set("kind", { state: "known", value: facts.kind.value });
      }}><option value="">{choose}</option><option value="expense">{t("business.dossier.kind.expense", "Expense")}</option>{facts.kind.state === "known" && facts.kind.value !== "expense" ? <option value={facts.kind.value}>{t(`business.dossier.kind.${facts.kind.value}`, facts.kind.value)}</option> : null}</select></label>
      <label className="block text-[13px] text-black/65 dark:text-white/65">{label("counterparty")}<input className={inputClass} value={scalar("counterparty")} disabled={disabled} onChange={(event) => setScalar("counterparty", event.target.value)} autoComplete="off" /></label>
      <div className="grid grid-cols-2 gap-3">
        <label className="text-[13px] text-black/65 dark:text-white/65">{label("occurred_on")}<input type="date" className={inputClass} value={scalar("occurred_on")} disabled={disabled} onChange={(event) => setScalar("occurred_on", event.target.value)} /></label>
        <label className="text-[13px] text-black/65 dark:text-white/65">{label("currency")}<select className={inputClass} value={scalar("currency")} disabled={disabled} onChange={(event) => setScalar("currency", event.target.value)}><option value="">{choose}</option>{[...new Set([...currencies, ...(scalar("currency") ? [scalar("currency")] : [])])].map((currency) => <option key={currency}>{currency}</option>)}</select></label>
      </div>
      <MoneyInput label={label("amount")} currency={scalar("currency")} value={scalar("amount") || null} disabled={disabled} onValueChange={({ value, invalid }) => { setScalar("amount", value ?? ""); setAmountInvalid(invalid); }} testId="dossier-review-amount" />
      <label className="block text-[13px] text-black/65 dark:text-white/65">{label("funding")}<select className={inputClass} value={fundingValue} disabled={disabled} onChange={(event) => {
        const value = event.target.value;
        if (!value || value === "owner_does_not_know") set("funding", { state: value === "owner_does_not_know" ? value : "unknown", value: null });
        else set("funding", { state: "known", value: value === "owner_funds" ? { kind: "owner_funds" } : { kind: "business_account", account_id: value.slice(8) } });
      }}><option value="">{choose}</option><option value="owner_does_not_know">{t("business.dossier.owner_unknown", "Owner doesn't know")}</option><option value="owner_funds">{t("business.dossier.owner_funds", "Owner's money")}</option>{accounts.map((account) => <option key={account.id} value={`account:${account.id}`}>{account.nickname ?? t("business.dossier.business_account", "Business account")} · {account.currency}</option>)}</select></label>
      <div className="grid grid-cols-2 gap-3">
        <label className="text-[13px] text-black/65 dark:text-white/65">{label("category_id")}<select className={inputClass} value={scalar("category_id")} disabled={disabled} onChange={(event) => setScalar("category_id", event.target.value)}><option value="">{choose}</option>{RECEIPT_CATEGORY_IDS.map((id) => <option key={id} value={id}>{categoryLabel(id)}</option>)}</select></label>
        <label className="text-[13px] text-black/65 dark:text-white/65">{label("receipt_state")}<select className={inputClass} value={receiptState.value ?? ""} disabled={disabled} onChange={(event) => {
          const value = event.target.value;
          if (value === "fiscal_receipt" || value === "informal_receipt" || value === "no_receipt") set("receipt_state", { state: "known", value });
          else set("receipt_state", { state: "unknown", value: null });
        }}><option value="">{choose}</option>{["fiscal_receipt", "informal_receipt", "no_receipt"].map((value) => <option key={value} value={value}>{t(`business.dossier.receipt.${value}`, value)}</option>)}</select></label>
      </div>
      <label className="block text-[13px] text-black/65 dark:text-white/65">{label("business_share")}<select className={inputClass} value={share.state === "known" ? share.value.kind : ""} disabled={disabled} onChange={(event) => {
        const value = event.target.value;
        setShareInvalid(false);
        if (value === "all" || value === "none") set("business_share", { state: "known", value: { kind: value } });
        else if (value === "partial") set("business_share", { state: "known", value: { kind: "partial", amount: "" } });
        else set("business_share", { state: "unknown", value: null });
      }}><option value="">{choose}</option>{["all", "none", "partial"].map((value) => <option key={value} value={value}>{t(`business.dossier.share.${value}`, value)}</option>)}</select></label>
      {share.state === "known" && share.value.kind === "partial" ? <MoneyInput label={t("business.dossier.business_amount", "Business amount")} currency={scalar("currency")} value={share.value.amount || null} disabled={disabled} onValueChange={({ value, invalid }) => { set("business_share", { state: "known", value: { kind: "partial", amount: value ?? "" } }); setShareInvalid(invalid); }} /> : null}
      <p className="text-[12px] leading-relaxed text-black/55 dark:text-white/55">{t("business.dossier.edit_note", "Saving updates the review details. Approval is a separate action.")}</p>
      <div className="flex flex-wrap gap-2">
        <button type="submit" className={secondaryButtonClass} disabled={cannotSave}>{t("business.dossier.save", "Save review details")}</button>
        <button type="button" className={secondaryButtonClass} disabled={disabled} onClick={onCancel}>{t("common.cancel", "Cancel")}</button>
      </div>
    </form>
  );
}
