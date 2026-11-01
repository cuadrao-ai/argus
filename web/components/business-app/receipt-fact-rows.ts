import type { BusinessDossier, BusinessFact, BusinessFactField, BusinessFacts, BusinessFiscalField } from "@/lib/business-dossier";

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

/** The read values the server doubts: a review flag names them, or the e-CF file says otherwise. */
export function doubtfulFields(dossier: Pick<BusinessDossier, "review_flags" | "ecf_checks">): Set<string> {
  const read = dossier.ecf_checks?.checks.find((check) => check.name === "read_matches_xml" && check.state === "failed");
  return new Set([...(dossier.review_flags ?? []).map((flag) => flag.field), ...Object.keys(read?.detail ?? {}).map((field) => field === "total" ? "amount" : field)]);
}

/** The server's two figures when the e-CF's parts do not add up to its total. The web never adds them itself. */
export function totalMismatch(dossier: Pick<BusinessDossier, "ecf_checks">): { sum: string; total: string } | null {
  const check = dossier.ecf_checks?.checks.find((item) => item.name === "totals_arithmetic" && item.state === "failed" && item.code === "totals_mismatch");
  return check?.detail.sum_of_parts && check.detail.monto_total ? { sum: check.detail.sum_of_parts, total: check.detail.monto_total } : null;
}

export const RECORD_FIELDS: readonly BusinessFactField[] = ["kind", "counterparty", "occurred_on", "amount", "currency", "category_id", "funding", "business_share", "receipt_state"];

/** Where the form shows each field: the activity section, the fiscal section (which opens with the receipt state), then how it was paid. */
export const KIND_FIELDS: readonly BusinessFactField[] = ["occurred_on", "amount", "currency", "counterparty", "category_id", "kind"];
export const PAYMENT_FIELDS: readonly BusinessFactField[] = ["funding", "business_share"];
/** The fiscal rows of an open draft: the NCF and the e-CF are one number there. */
export type FiscalRow = "rnc" | "fiscal_number" | "itbis";
/** The rows a person edits in place on an open draft. `amount` holds the total and its currency. */
export type ReviewRow = BusinessFactField | FiscalRow;
/** The six read facts, in the order they are read off a receipt. */
export const READ_FACT_ROWS: readonly ReviewRow[] = ["counterparty", "occurred_on", "amount", "rnc", "fiscal_number", "itbis"];

export function recordFactRows(dossier: Pick<BusinessDossier, "facts" | "blockers" | "questions">): FactRow<BusinessFactField>[] {
  return factRows(RECORD_FIELDS, (key) => dossier.facts[key], blockedFields(dossier), askedFields(dossier))
    .sort((a, b) => Number(b.standing === "empty") - Number(a.standing === "empty"));
}

export function fiscalFactRows(facts: BusinessFacts): FactRow<BusinessFiscalField>[] {
  const fiscal = facts.fiscal;
  if (!fiscal) return [];
  return factRows(["rnc", "ncf", "ecf", "itbis"] as const, (key) => fiscal[key]);
}
