import type { BandejaGroup, BusinessAccount, DocumentDeleteAccess, ReceiptAttention } from "./business-api";
import type { DgiiDeclaration, SalePayment, SuggestedField, SuggestionSource } from "./business-dgii";
import type { PersonName, PersonShown } from "./person-name";

export type BusinessFact<T> =
  | { state: "known"; value: T; origin: "extracted" | "qr_decoded" | "owner_stated" | "member_set" | "matched" | "default"; verified: boolean; source_ids: string[] }
  | { state: "unknown"; value: null; origin: "extracted" | "qr_decoded" | "owner_stated" | "member_set" | "matched" | null; verified: false; source_ids: string[] }
  | { state: "owner_does_not_know"; value: null; origin: "owner_stated" | "member_set"; verified: false; source_ids: string[] };

/** What a reader may decide for a possible repeat. The server lists the allowed ones on each candidate. */
export type BusinessDuplicateDecision = "same_purchase" | "different_purchase";
/** The main data the compare view's diff shows, in its order. The server compares the file too; the column heads and previews show it. */
export const BUSINESS_COMPARED_FIELDS = ["counterparty", "occurred_on", "amount", "currency", "fiscal_number"] as const;
export type BusinessComparedField = (typeof BUSINESS_COMPARED_FIELDS)[number];
/** One document of a possible repeat as its draft holds it now; null is unknown. */
export type BusinessComparedDocument = {
  draft_id: string;
  counterparty: string | null;
  occurred_on: string | null;
  amount: string | null;
  currency: string | null;
  /** The NCF, else the e-CF number. */
  fiscal_number: string | null;
  /** The first file, with where and when it arrived. */
  file: { connection_id: string; filename: string | null; media_type: string; channel: "web" | "whatsapp" | "email"; received_at: string } | null;
  received_at: string | null;
  approved_at: string | null;
  /** `accepted` once approved; the reviewed document is always `open`. */
  state: "open" | "accepted";
};
/**
 * A document the reviewed one may repeat. The server owns why (`basis`), what this reader may decide
 * (`decisions`), which values differ and what the fiscal numbers recommend; the web renders them and computes none.
 */
export type BusinessDuplicateCandidate = {
  draft_id: string;
  version: number;
  basis: "read_facts" | "fiscal_number";
  decisions: BusinessDuplicateDecision[];
  comparison: {
    document: BusinessComparedDocument;
    other: BusinessComparedDocument;
    differences: (BusinessComparedField | "file")[];
    recommendation: BusinessDuplicateDecision | null;
  };
};
export type BusinessFunding = { kind: "business_account"; account_id: string } | { kind: "owner_funds" };
export type BusinessFacts = {
  kind: BusinessFact<"expense" | "income" | "transfer" | "refund" | "owner_contribution" | "owner_withdrawal" | "credit_purchase" | "payable_payment" | "loan_received" | "loan_payment">;
  amount: BusinessFact<string>;
  net_amount?: BusinessFact<string>;
  legal_tip?: BusinessFact<string>;
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
export type BusinessFactPatch = { [K in BusinessFactField]?: BusinessFactInput<NonNullable<NonNullable<BusinessFacts[K]>["value"]>> };
export type BusinessMontosReview = { net_amount?: BusinessFactInput<string>; legal_tip?: BusinessFactInput<string>; restore_inherited?: string[]; override_inherited?: string[] };
/** Who acted and who granted their access, each named live by the server (`PersonName`). */
export type BusinessActor = PersonName & { actor_id: string; actor_kind: "owner_via_agent" | "member" | "extractor"; grant_id: string; issuer_id: string; issuer_display_name: string | null; issuer_email?: string | null; issuer_shown_as: PersonShown };

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

export type EditableDossierField = BusinessFactField | "rnc" | "fiscal_number" | "itbis" | "document_type" | "due_on" | "modified_ncf" | "actual_refund";

export type BusinessDraftRevision = {
  before_document_type?: NonNullable<BusinessDossier["document_type"]> | null;
  after_document_type?: NonNullable<BusinessDossier["document_type"]> | null;
  before_due_on?: string | null;
  after_due_on?: string | null;
  before_current_note?: string | null;
  after_current_note?: string | null;
  supporting_change?: "appended" | "unlinked" | "restored" | null;
  supporting_filename?: string | null;
  before_dgii?: DgiiDeclaration | null;
  after_dgii?: DgiiDeclaration | null;
  draft_id: string;
  version: number;
  actor: BusinessActor;
  before: BusinessFacts | null;
  after: BusinessFacts;
  source_ids: string[];
  turn_key: string | null;
  created_at: string;
  /** Why the server made a revision no person and no read made. */
  reason?: "business_rnc_set" | null;
  /** The person's duplicate decision this revision records, with the other document as the server reads it now. */
  duplicate?: { decision: "different_purchase"; other_draft_id: string; other_counterparty: string | null; other_filename: string | null } | null;
};

export type BusinessRecordContext = {
  space_id: string;
  space_name: string | null;
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

export function readReviewNote(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value.trim();
  return text ? text : null;
}

export function readBusinessDossier(value: unknown): BusinessDossier {
  const body = typeof value === "object" && value !== null && !Array.isArray(value) ? value as BusinessDossier & { review_note?: unknown } : {} as BusinessDossier;
  return { ...body, review_note: readReviewNote(body.review_note) };
}

export const REVIEW_FLAG_CODES = ["rnc_check_digit", "ncf_malformed", "itbis_high", "amounts_mismatch"] as const;
export type ReviewFlagCode = (typeof REVIEW_FLAG_CODES)[number];
/** A read value to check again. The Listo rule decides whether the owner may accept over it. */
export type ReviewFlag = { code: ReviewFlagCode; field: "rnc" | "ncf" | "itbis" | "amount"; confirm: boolean; difference?: string | null };

export type BusinessApprovalAction = "record_expense" | "record_income" | "record_refund";
/** An approved purchase a refund or credit note may name; `id` is the activity `purchase_activity_id` takes. */
export type RefundCandidate = { id: string; merchant: string | null; occurred_on: string; amount: string; currency: string };

/** A value the server suggests and where it came from. */
export type DeclarationSuggestion = { value: string; source: SuggestionSource };
/** The suggestions a person saw filled in, which an expense approval saves into its blank answers. */
export type ShownSuggestions = Partial<Record<SuggestedField, DeclarationSuggestion>>;

/** Reasons from the Listo rule, plus a read in progress. */
export const LISTO_GAPS = ["not_read", "check_details", "several_purchases", "no_purchase_found", "duplicate", "credit_note", "missing_merchant", "missing_date", "missing_amount", "missing_currency", "sin_comprobante", "missing_rnc", "invalid_rnc", "missing_ncf", "invalid_ncf", "ecf_check_failed", "missing_itbis", "review_flag", "blocked", "unverified_sender", "reading"] as const;
export type ListoGap = (typeof LISTO_GAPS)[number] | ReceiptAttention;
/** What the DGII register says of the supplier RNC: its mapped status, or `not_found` when a loaded register does not list it. */
export const RNC_REGISTRY_STATUSES = ["verificado", "suspendido", "dado_de_baja", "cese_temporal", "anulado", "rechazado", "desconocido", "not_found"] as const;
export type RncRegistryStatus = (typeof RNC_REGISTRY_STATUSES)[number];

export type BusinessSupportingFile = {
  source_id: string;
  receipt_id: string;
  filename: string | null;
  media_type: string | null;
  size_bytes: number | null;
  state: "linked" | "unlinked";
  purge_at: string | null;
  unlink_available: boolean;
  restore_available: boolean;
};

export type AmountsCheck = { state: "adds_up" | "unchecked"; difference?: null } | { state: "difference"; difference: string };

export type RecordReadiness = {
  missing?: readonly string[];
  reasons?: Readonly<Record<string, { field: string | null; words: string }>>;
};

export type BusinessDossier = BusinessRecordContext & DocumentDeleteAccess & RecordReadiness & {
  /** Where the record stands in the Bandeja, by the rule the receipt list reads. An accepted record has the label `accepted`; a deleted one has none. */
  bandeja_group?: Pick<BandejaGroup, "group" | "reason" | "label"> | null;
  /** Every reason a record that needs attention is not Listos, in the rule's order; empty for any other record. */
  listo_gaps?: readonly ListoGap[];
  /** The gaps the owner may explicitly accept over, as named by the server. */
  confirmable?: readonly ListoGap[];
  /** Null when the record has no RNC or no register is loaded. */
  rnc_registry_status?: RncRegistryStatus | null;
  /** The Subtotal and who gave it: `calculated` while the server derives it, `edited` once a person typed one. Its `calculated` is the amount the server derives whoever gave the Subtotal: what a typed one goes back to. */
  net_amount?: { amount: string | null; source: "read" | "calculated" | "edited" | null; calculated?: string | null };
  /** Whether the Total is the Subtotal plus its taxes and tip, by the server's rule. `difference` comes with the amount left over. */
  amounts_check?: AmountsCheck;
  /** The note this record is, by the server's reading; null for a regular purchase or sale. */
  note_kind?: "credit" | "debit" | null;
  /** The declaration fields that always follow their source: the server drops a write to one, so its row is read-only. */
  source_owned_fields?: readonly string[];
  inheritance?: Record<string, { field: "net_amount" | "itbis" | "legal_tip" | "occurred_on" | "rnc" | "original_ncf"; value: string | null; inherited: boolean; paired_with: readonly string[] }>;
  current_note?: string | null;
  note_edit_available?: boolean;
  supporting_append_available?: boolean;
  supporting_files?: BusinessSupportingFile[];
  supporting_file_limit?: number;
  supporting_limit_reached?: boolean;
  annotation_unavailable_reason?: string | null;
  dgii?: DgiiDeclaration | null;
  /** What the 606 calculates from `dgii` for a purchase; null for a sale and for a record with no 606 declaration. */
  dgii_calculated?: { billed_amount: string; itbis_advance: string | null } | null;
  /** The server authorizes writing this dossier's facts and fiscal details. */
  facts_editable?: boolean;
  /** The fields the caller can correct at this revision. */
  editable_fields?: readonly EditableDossierField[];
  /** The caller may write the general 606 choices for this record. */
  declaration_editable?: boolean;
  /** The caller may write a sale's 607 answers now. */
  payment_split_editable?: boolean;
  /** How a sale was paid, as one pick; null for a record that is not a sale. */
  sale_payment?: SalePayment | null;
  /** The Business year in which the first source arrived, and whether the issue date is a read whose year is not that year. The server decides both; the date field offers the upload year exactly when `year_to_check` is true. */
  upload_year?: number | null;
  year_to_check?: boolean;
  /** What the server offers for each 606 answer this open expense lacks, under the declaration's field name. The approval saves the ones the person saw. */
  declaration_suggestions?: Partial<Record<SuggestedField, DeclarationSuggestion | null>>;
  /** What the e-CF XML proved by itself; null for any other source. */
  ecf_checks?: EcfVerification | null;
  /** The DGII QR the receipt carried; null when there was none. */
  dgii_qr?: DgiiQr | null;
  /** The server shows the e-CF checks card in review. `ecf_checks` and `dgii_qr` come either way. */
  ecf_checks_panel_available?: boolean;
  /** One NCF due notice. Unpaid is Factura por pagar. Paid, the same record is Factura pagada. */
  bill_mark?: "Factura por pagar" | "Factura pagada" | null;
  /** The record's marks from the server, the same reading every list shows: Personal, who last changed it when not the owner, the fiscal number, the 606 answer. */
  personal?: boolean;
  personal_marked_by?: PersonName | null;
  /** The record's facts exist, so an empty fiscal_value means no fiscal number. */
  fiscal_known?: boolean;
  fiscal_value?: "ncf" | "ecf" | null;
  /** Always present on the dossier: no comprobante fiscal stated and no NCF or e-CF. */
  sin_comprobante?: boolean;
  fiscal_question_applies?: boolean;
  include_606?: boolean | null;
  /** Who gave the 606 answer, while one applies. */
  include_606_by?: PersonName | null;
  read_purchases?: BusinessReadPurchase[];
  /** The receipt total the read showed, and how many read purchases this record leaves unrecorded (0 once settled). */
  read_total?: string | null;
  unrecorded_purchases?: number;
  /** Compra (`recibo`) or Venta: the draft's current type. */
  document_type?: "recibo" | "venta";
  /** The type was read from the document, not picked; absent when false. */
  document_type_detected?: boolean;
  /** The server permits changing this document type at the current revision. */
  document_type_editable?: boolean;
  draft_id: string;
  version: number;
  review_state: "open" | "accepting" | "accepted" | "dismissed";
  facts: BusinessFacts;
  sources: BusinessSourceEvidence[];
  questions: BusinessReviewQuestion[];
  history: BusinessDraftRevision[];
  blockers: { code: string; field: BusinessFactField | null; min_date?: string; today?: string }[];
  /** Computed on every read, after approval too. Absent from servers older than #1590. */
  review_flags?: ReviewFlag[];
  approval_available: boolean;
  duplicate_candidates?: BusinessDuplicateCandidate[];
  /** The approve action this draft takes, by its kind; null while approval is not available. Absent from servers older than #1353. */
  approval_action?: BusinessApprovalAction | null;
  /** The server's sentence for this draft. Absent and null mean there is none. The web shows the words as sent. */
  review_note?: string | null;
  /** The caller may answer the 606 question now, by the gate that action enforces. */
  fiscal_inclusion_available?: boolean;
  /** Purchases this draft may refund, newest first; empty unless it is a refund or a credit note. */
  refund_candidates?: RefundCandidate[];
  /** A recorded approval names the facts revision the person approved and when; later changes add history revisions without changing either. */
  approval_result: { status: "recorded"; activity_id: string; reviewed_version: number; approved_revision: number; approved_at: string; actor: BusinessActor } | { status: "outcome_unknown" | "failed"; code: string; reviewed_version: number } | null;
};
