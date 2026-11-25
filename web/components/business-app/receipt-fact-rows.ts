import type { SuggestedField } from "@/lib/business-dgii";
import type { BusinessDossier, BusinessFactField, ReviewFlagCode } from "@/lib/business-dossier";

const OPEN_QUESTION = new Set(["open", "owner_does_not_know", "waiting_for_window"]);

/** The fields the backend's blockers name; blockers with no field are shown by the guidance card, not counted here. */
export function blockedFields(dossier: Pick<BusinessDossier, "blockers">): Set<string> {
  return new Set(dossier.blockers.map((blocker) => blocker.field).filter((field): field is BusinessFactField => Boolean(field)));
}

export function askedFields(dossier: Pick<BusinessDossier, "questions">): Set<string> {
  return new Set(dossier.questions.filter((question) => OPEN_QUESTION.has(question.state)).map((question) => question.field));
}

/** The RNC row's standing is its status block's alone; the row's pencil is its one action. */
const RNC_STATUS_ROW = "rnc";
const FLAG_SHOWN_AS: Record<ReviewFlagCode, "own_line" | "doubt_mark"> = { rnc_check_digit: "own_line", ncf_malformed: "doubt_mark", itbis_high: "own_line", amounts_mismatch: "own_line" };

/** The read values the server doubts: a review flag names them, or the e-CF file says otherwise. */
export function doubtfulFields(dossier: Pick<BusinessDossier, "review_flags" | "ecf_checks">): Set<string> {
  const read = dossier.ecf_checks?.checks.find((check) => check.name === "read_matches_xml" && check.state === "failed");
  const flagged = (dossier.review_flags ?? []).filter((flag) => FLAG_SHOWN_AS[flag.code] === "doubt_mark").map((flag) => flag.field);
  const disputed = Object.keys(read?.detail ?? {}).map((field) => field === "total" ? "amount" : field);
  return new Set([...flagged, ...disputed].filter((field) => field !== RNC_STATUS_ROW));
}

export const RECORD_FIELDS: readonly BusinessFactField[] = ["kind", "counterparty", "occurred_on", "amount", "currency", "category_id", "funding", "business_share", "receipt_state"];

/** Where the form shows each field: the activity section, the fiscal section (which opens with the receipt state), then how it was paid. The ledger category stays off a Business record: its 606 tipo de gasto is the one classification shown. So does the business share: the Personal switch is its one control. */
export const PAYMENT_FIELDS: readonly BusinessFactField[] = ["funding"];
/** The fiscal rows of an open draft: the NCF and the e-CF are one number there. */
export type FiscalRow = "rnc" | "fiscal_number" | "itbis";
/** The rows a person edits in place. `amount` holds the total and its currency. */
export type ReviewRow = BusinessFactField | FiscalRow | "document_type" | SuggestedField | SaleChoice;
/** The 607 answers a person picks on a sale: the type of income and the one payment form. */
export type SaleChoice = "income_type" | "sale_payment";
export type DocumentType = NonNullable<BusinessDossier["document_type"]>;
/** Compra then Venta, each by its intake word. */
export const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = { recibo: "business.intake.type_recibo", venta: "business.intake.type_venta" };
/** The six read facts, in the order they are read off a receipt. */
export const READ_FACT_ROWS: readonly ReviewRow[] = ["counterparty", "occurred_on", "amount", "rnc", "fiscal_number", "itbis"];
