import type { BusinessFact, BusinessFactField, BusinessFacts, BusinessFiscalField } from "@/lib/business-dossier";

/**
 * How a fact stands, from its backend state and origin alone. A person reads
 * three kinds of thing on the review page: what is settled (verified, stated
 * by a person, or decoded from the DGII QR), what the AI read suggested and
 * nobody confirmed, and what is still missing. A suggestion never counts as
 * known: it waits for a person.
 */
export type FactStanding = "verified" | "person" | "qr" | "suggestion" | "default" | "owner_unknown" | "missing";

const ORDER: Record<FactStanding, number> = { verified: 0, person: 1, qr: 2, suggestion: 3, default: 4, owner_unknown: 5, missing: 6 };

export function factStanding(fact: BusinessFact<unknown>): FactStanding {
  if (fact.state === "unknown") return "missing";
  if (fact.state === "owner_does_not_know") return "owner_unknown";
  if (fact.verified) return "verified";
  if (fact.origin === "default") return "default";
  if (fact.origin === "qr_decoded") return "qr";
  if (fact.origin === "extracted") return "suggestion";
  return "person";
}

/** Settled enough to count toward what the record knows; a suggestion is not. */
export function countsAsKnown(standing: FactStanding): boolean {
  return standing === "verified" || standing === "person" || standing === "qr";
}

export type FactRow<K extends string> = { key: K; standing: FactStanding };

/** The rows in reading order: settled first, then suggestions, then defaults, then what a person must still give. Within a group the given field order holds. */
export function factRows<K extends BusinessFactField | BusinessFiscalField>(
  fields: readonly K[],
  lookup: (key: K) => BusinessFact<unknown> | undefined,
): FactRow<K>[] {
  return fields
    .map((key, index) => {
      const fact = lookup(key);
      return { key, standing: fact ? factStanding(fact) : ("missing" as FactStanding), index };
    })
    .sort((a, b) => ORDER[a.standing] - ORDER[b.standing] || a.index - b.index)
    .map(({ key, standing }) => ({ key, standing }));
}

export const RECORD_FIELDS: readonly BusinessFactField[] = ["kind", "counterparty", "occurred_on", "amount", "currency", "category_id", "funding", "business_share", "receipt_state"];

/** What the page says about the record's completeness: suggestions waiting on a person and fields still missing, from the rows alone. */
export function reviewCounts(rows: readonly FactRow<string>[]): { suggestions: number; missing: number } {
  return {
    suggestions: rows.filter((row) => row.standing === "suggestion").length,
    missing: rows.filter((row) => row.standing === "missing").length,
  };
}

export function recordFactRows(facts: BusinessFacts): FactRow<BusinessFactField>[] {
  return factRows(RECORD_FIELDS, (key) => facts[key]);
}
