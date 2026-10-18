import type { BusinessAccount } from "./business-api";

export type BusinessFact<T> =
  | { state: "known"; value: T; origin: "extracted" | "qr_decoded" | "owner_stated" | "member_set" | "matched" | "default"; verified: boolean; source_ids: string[] }
  | { state: "unknown"; value: null; origin: "extracted" | "qr_decoded" | "owner_stated" | "member_set" | "matched" | null; verified: false; source_ids: string[] }
  | { state: "owner_does_not_know"; value: null; origin: "owner_stated" | "member_set"; verified: false; source_ids: string[] };

export type BusinessFunding = { kind: "business_account"; account_id: string } | { kind: "owner_funds" };
export type BusinessFacts = {
  kind: BusinessFact<"expense" | "income" | "transfer" | "refund" | "owner_contribution" | "owner_withdrawal" | "credit_purchase" | "payable_payment" | "loan_received" | "loan_payment">;
  amount: BusinessFact<string>;
  currency: BusinessFact<string>;
  occurred_on: BusinessFact<string>;
  counterparty: BusinessFact<string>;
  funding: BusinessFact<BusinessFunding>;
  business_share: BusinessFact<{ kind: "all" | "none" } | { kind: "partial"; amount: string }>;
  receipt_state: BusinessFact<"fiscal_receipt" | "informal_receipt" | "no_receipt">;
  category_id: BusinessFact<string>;
  fiscal: { rnc: BusinessFact<string>; ncf: BusinessFact<string>; ecf: BusinessFact<string>; itbis: BusinessFact<string>; include_606?: BusinessFact<boolean> } | null;
};

export type BusinessSourceEvidence =
  | { id: string; kind: "message" | "agent_proposal"; channel: "web" | "whatsapp"; received_at: string; text: string }
  | { id: string; kind: "web_action"; channel: "web"; received_at: string; text: string }
  | { id: string; kind: "attachment"; channel: "web" | "whatsapp" | "email"; received_at: string; connection_id: string; filename: string | null; media_type: string; email_delivery_ids?: string[] };

export type BusinessFiscalField = keyof NonNullable<BusinessFacts["fiscal"]>;
export const BUSINESS_FISCAL_FIELDS: BusinessFiscalField[] = ["rnc", "ncf", "ecf", "itbis", "include_606"];

export type BusinessFactField = Exclude<keyof BusinessFacts, "fiscal">;
export type BusinessFactInput<T> = { state: "known"; value: T } | { state: "unknown" | "owner_does_not_know"; value: null };
export type BusinessFactPatch = { [K in BusinessFactField]?: BusinessFactInput<NonNullable<BusinessFacts[K]["value"]>> };
export type BusinessActor = { actor_id: string; actor_kind: "owner_via_agent" | "member" | "extractor"; display_name: string; grant_id: string; issuer_id: string; issuer_display_name: string };

export type BusinessReviewQuestion = {
  id: string;
  draft_id: string;
  field: BusinessFactField;
  asked_of: "owner" | "accountant";
  channel: "whatsapp" | "web";
  state: "open" | "answered" | "owner_does_not_know" | "waiting_for_window" | "withdrawn";
  prompt: string;
  allowed_answers: ("known" | "owner_does_not_know")[];
  answer_source_id: string | null;
  created_at: string;
};

export type BusinessDraftRevision = {
  draft_id: string;
  version: number;
  actor: BusinessActor;
  before: BusinessFacts | null;
  after: BusinessFacts;
  source_ids: string[];
  turn_key: string | null;
  created_at: string;
};

export type BusinessRecordContext = {
  space_id: string;
  space_name: string;
  accounts: BusinessAccount[];
  capabilities: ("read" | "prepare" | "approve")[];
};

/** One purchase a document read showed, kept as evidence when the read could not settle on one. */
export type BusinessReadPurchase = { index: number; amount: string | null; currency: string | null; occurred_on: string | null; merchant: string | null; kind_hint: string | null };

/** The revision number a person sees: the latest revision of the facts, the same number the history lists. The event's own version also counts approvals and settlements. */
export function factsRevision(dossier: Pick<BusinessDossier, "version" | "history">): number {
  return dossier.history.length ? Math.max(...dossier.history.map((revision) => revision.version)) : dossier.version;
}

export type EcfCheckName = "signature_integrity" | "totals_arithmetic" | "read_matches_xml" | "certificate_validity" | "certificate_issuer" | "subject_rnc" | "dgii_accepted" | "security_code" | "qr_present" | "qr_matches_read";
/** The DGII consultation link a receipt's QR carried; a person opens it, Cuadrao never fetches it. */
export type DgiiQr = { url: string; host: string; rnc_emisor: string; encf: string; monto_total: string | null; codigo_seguridad: string | null; fecha_emision: string | null; fecha_firma: string | null; rnc_comprador: string | null };
export type EcfCheckState = "verified" | "failed" | "not_checked";
/** One fact the e-CF file proved, or the reason it was not checked; never a blocker. */
/** One compared field as the read found it and as the QR states it; only the qr_matches_read row carries them. */
export type ReadVsQr = { read: string; qr: string };
export type EcfCheck = { name: EcfCheckName; state: EcfCheckState; code: string | null; detail: Record<string, string>; read_vs_qr?: Record<string, ReadVsQr> };
export type EcfVerification = { encf: string | null; tipo_ecf: string | null; checked_at: string; checks: EcfCheck[] };

export type BusinessDossier = BusinessRecordContext & {
  /** What the e-CF XML proved by itself; null for any other source. */
  ecf_checks?: EcfVerification | null;
  /** The DGII QR the receipt carried; null when there was none. */
  dgii_qr?: DgiiQr | null;
  /** The record's marks from the server, the same reading every list shows: Personal, who last changed it when not the owner, the fiscal number, the 606 answer. */
  personal?: boolean;
  personal_marked_by?: string | null;
  /** The record's facts exist, so an empty fiscal_value means no fiscal number. */
  fiscal_known?: boolean;
  fiscal_value?: "ncf" | "ecf" | null;
  include_606?: boolean | null;
  /** Who gave the 606 answer, while one applies. */
  include_606_by?: string | null;
  read_purchases?: BusinessReadPurchase[];
  /** The receipt total the read showed, and how many read purchases this record leaves unrecorded (0 once settled). */
  read_total?: string | null;
  unrecorded_purchases?: number;
  draft_id: string;
  version: number;
  review_state: "open" | "accepting" | "accepted" | "dismissed";
  facts: BusinessFacts;
  sources: BusinessSourceEvidence[];
  questions: BusinessReviewQuestion[];
  history: BusinessDraftRevision[];
  blockers: { code: string; field: BusinessFactField | null }[];
  approval_available: boolean;
  /** A recorded approval names the facts revision the person approved and when; later marks add history revisions without changing either. */
  approval_result: { status: "recorded"; activity_id: string; reviewed_version: number; approved_revision: number; approved_at: string; actor: BusinessActor } | { status: "outcome_unknown" | "failed"; code: string; reviewed_version: number } | null;
};
