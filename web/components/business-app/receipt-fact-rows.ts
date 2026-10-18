import type { BusinessDossier, BusinessFact, BusinessFactField, BusinessFacts, BusinessFiscalField, BusinessFactPatch } from "@/lib/business-dossier";

/**
 * How a fact stands, from its backend state and origin alone. A person reads
 * what is settled (verified, stated by a person, decoded from the DGII QR,
 * linked to a source), what the AI read suggested and nobody confirmed, and
 * what has no value yet. Whether a gap blocks approval is the backend's
 * word, carried on the dossier's blockers and open questions: the page never
 * decides that on its own, so its counts agree with "Antes de aprobar".
 */
export type FactStanding = "verified" | "person" | "qr" | "linked" | "suggestion" | "default" | "unverified" | "owner_unknown" | "empty";

const ORDER: Record<FactStanding, number> = { verified: 0, person: 1, qr: 2, linked: 3, suggestion: 4, default: 5, unverified: 6, owner_unknown: 7, empty: 8 };

export function factStanding(fact: BusinessFact<unknown>): FactStanding {
  if (fact.state === "unknown") return "empty";
  if (fact.state === "owner_does_not_know") return "owner_unknown";
  if (fact.verified) return "verified";
  switch (fact.origin) {
    case "default":
      return "default";
    case "qr_decoded":
      return "qr";
    case "extracted":
      return "suggestion";
    case "owner_stated":
    case "member_set":
      return "person";
    case "matched":
      return "linked";
    default:
      return "unverified";
  }
}

export type FactRow<K extends string> = {
  key: K;
  standing: FactStanding;
  /** The backend names this field in a blocker: approval waits on it. */
  blocked: boolean;
  /** An open question on this field waits for a person's decision. */
  asked: boolean;
};

const OPEN_QUESTION = new Set(["open", "owner_does_not_know", "waiting_for_window"]);

/** The fields the backend's blockers name; blockers with no field are shown by the guidance card, not counted here. */
export function blockedFields(dossier: Pick<BusinessDossier, "blockers">): Set<string> {
  return new Set(dossier.blockers.map((blocker) => blocker.field).filter((field): field is BusinessFactField => Boolean(field)));
}

export function askedFields(dossier: Pick<BusinessDossier, "questions">): Set<string> {
  return new Set(dossier.questions.filter((question) => OPEN_QUESTION.has(question.state)).map((question) => question.field));
}

/** The rows in reading order: settled first, then suggestions, then defaults, then what has no value yet. Within a group the given field order holds. */
export function factRows<K extends BusinessFactField | BusinessFiscalField>(
  fields: readonly K[],
  lookup: (key: K) => BusinessFact<unknown> | undefined,
  blocked: ReadonlySet<string> = new Set(),
  asked: ReadonlySet<string> = new Set(),
): FactRow<K>[] {
  return fields
    .map((key, index) => {
      const fact = lookup(key);
      return { key, standing: fact ? factStanding(fact) : ("empty" as FactStanding), blocked: blocked.has(key), asked: asked.has(key), index };
    })
    .sort((a, b) => ORDER[a.standing] - ORDER[b.standing] || a.index - b.index)
    .map(({ key, standing, blocked: isBlocked, asked: isAsked }) => ({ key, standing, blocked: isBlocked, asked: isAsked }));
}

export const RECORD_FIELDS: readonly BusinessFactField[] = ["kind", "counterparty", "occurred_on", "amount", "currency", "category_id", "funding", "business_share", "receipt_state"];

/**
 * What the page says about completeness, in the same numbers the rows show:
 * suggestions waiting on a person; "missing" is every row with no value that
 * a blocker names (each reads Falta); "unresolved" is every other row that a
 * blocker or an open question names while it has a value or an owner's
 * "doesn't know" (each carries the decision marker).
 */
export function reviewCounts(rows: readonly FactRow<string>[]): { suggestions: number; missing: number; unresolved: number } {
  return {
    suggestions: rows.filter((row) => row.standing === "suggestion").length,
    missing: rows.filter((row) => row.standing === "empty" && row.blocked).length,
    unresolved: rows.filter((row) => (row.blocked || row.asked) && row.standing !== "empty").length,
  };
}

export function recordFactRows(dossier: Pick<BusinessDossier, "facts" | "blockers" | "questions">): FactRow<BusinessFactField>[] {
  return factRows(RECORD_FIELDS, (key) => dossier.facts[key], blockedFields(dossier), askedFields(dossier))
    .sort((a, b) => Number(b.standing === "empty") - Number(a.standing === "empty"));
}

export function fiscalFactRows(facts: BusinessFacts): FactRow<BusinessFiscalField>[] {
  const fiscal = facts.fiscal;
  if (!fiscal) return [];
  return factRows(["rnc", "ncf", "ecf", "itbis"] as const, (key) => fiscal[key]);
}

export function extractedConfirmationPatch(dossier: Pick<BusinessDossier, "facts" | "blockers" | "questions">, edits: BusinessFactPatch): BusinessFactPatch {
  return Object.fromEntries(recordFactRows(dossier).flatMap(({ key, standing, blocked, asked }) => {
    const fact = dossier.facts[key];
    return standing === "suggestion" && !blocked && !asked && !Object.hasOwn(edits, key) && fact.state === "known"
      ? [[key, { state: "known", value: fact.value }]] : [];
  })) as BusinessFactPatch;
}
