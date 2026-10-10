import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessFacts, BusinessFactField } from "@/lib/business-dossier";
import { formatDay, formatMoney } from "./business-format";

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
    return share.value.kind === "partial" ? formatMoney(share.value.amount, facts.currency.state === "known" ? facts.currency.value : null, locale) || share.value.amount : labels.value?.(key, share.value.kind) ?? share.value.kind;
  }
  if (key === "amount") return facts.currency.state === "known" ? formatMoney(String(fact.value), facts.currency.value, locale) : String(fact.value);
  if (key === "occurred_on") return formatDay(String(fact.value), locale);
  return labels.value?.(key, String(fact.value)) ?? String(fact.value);
}
