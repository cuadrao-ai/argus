import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessFacts, BusinessFactField, BusinessFiscalField } from "@/lib/business-dossier";
import { formatDay, formatMoney, UNKNOWN_VALUE } from "./business-format";

/** An amount in the record's own currency; with no known currency it is unknown, never a bare number. */
function moneyOrUnknown(amount: string, facts: BusinessFacts, locale: string): string {
  return facts.currency.state === "known" ? formatMoney(amount, facts.currency.value, locale) : UNKNOWN_VALUE;
}

export function presentBusinessFact(
  key: BusinessFactField,
  facts: BusinessFacts,
  accounts: BusinessAccount[],
  locale: string,
  labels: { unknown: string; ownerUnknown: string; ownerFunds: string; businessAccount: string; value?: (key: BusinessFactField, value: string) => string },
): string {
  const fact = facts[key];
  if (fact.state !== "known") return fact.state === "owner_does_not_know" ? labels.ownerUnknown : labels.unknown;
  if (key === "funding") {
    const funding = facts.funding;
    if (funding.state !== "known") return labels.unknown;
    if (funding.value.kind === "owner_funds") return labels.ownerFunds;
    const id = funding.value.account_id;
    return accounts.find((account) => account.id === id)?.nickname ?? labels.businessAccount;
  }
  if (key === "business_share") {
    const share = facts.business_share;
    if (share.state !== "known") return labels.unknown;
    return share.value.kind === "partial" ? moneyOrUnknown(share.value.amount, facts, locale) : labels.value?.(key, share.value.kind) ?? share.value.kind;
  }
  if (key === "amount") return moneyOrUnknown(String(fact.value), facts, locale);
  if (key === "occurred_on") return formatDay(String(fact.value), locale);
  return labels.value?.(key, String(fact.value)) ?? String(fact.value);
}

export function presentFiscalFact(key: BusinessFiscalField, facts: BusinessFacts, locale: string, labels: { unknown: string; ownerUnknown: string; notRecorded: string; rncUnknown?: string; yes?: string; no?: string }): string {
  const fact = facts.fiscal?.[key];
  if (!fact) return labels.notRecorded;
  // An RNC nobody knows says so by name; it is never shown as a number.
  if (fact.state === "unknown" && key === "rnc" && labels.rncUnknown) return labels.rncUnknown;
  if (fact.state !== "known") return fact.state === "owner_does_not_know" ? labels.ownerUnknown : labels.unknown;
  // The 606 answer reads as the Sí or No the accountant chose.
  if (typeof fact.value === "boolean") return (fact.value ? labels.yes : labels.no) ?? String(fact.value);
  return key === "itbis" ? moneyOrUnknown(fact.value, facts, locale) : fact.value;
}
