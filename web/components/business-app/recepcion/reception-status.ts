import type { ReceptionRow } from "./reception-model";

/** The four row tags, plus the existing word for a discarded receipt. `reason` is a code the server sent. */
export type ReceptionTag =
  | { tag: "reading" }
  | { tag: "attention"; reason: string | null }
  | { tag: "listo" }
  | { tag: "approved" }
  | { tag: "dismissed" };

export function receptionTag(row: ReceptionRow): ReceptionTag {
  if (row.kind === "note") return { tag: "attention", reason: "note" };
  if (row.kind === "email") return row.email.standing === "reading" ? { tag: "reading" } : { tag: "attention", reason: "no_receipt" };
  const { status, bandeja_group: group } = row.receipt;
  if (status === "confirmed") return { tag: "approved" };
  if (status === "dismissed") return { tag: "dismissed" };
  if (group?.group === "listo") return { tag: "listo" };
  if (group?.reason === "reading") return { tag: "reading" };
  return { tag: "attention", reason: group?.reason ?? null };
}

const MISSING = "business.transactions.layout.workflow.missing";
const ATTENTION = "business.attention_short";
const PLACEHOLDER = "business.reception_preview.placeholder.reason";

/** The Bandeja's one plain word for each reason the server sends. A code not listed here shows no reason, never a guess. */
export const BANDEJA_REASON_KEY: Readonly<Record<string, string>> = {
  ai_unavailable: `${ATTENTION}.ai_unavailable`,
  blocked: `${PLACEHOLDER}.blocked`,
  check_details: `${ATTENTION}.check_details`,
  credit_note: "business.transactions.layout.filters.document.credit_note",
  duplicate: `${ATTENTION}.duplicate`,
  ecf_check_failed: `${PLACEHOLDER}.ecf_check_failed`,
  foreign_currency: `${PLACEHOLDER}.foreign_currency`,
  interrupted: `${ATTENTION}.interrupted`,
  invalid_ncf: `${MISSING}.ncf_invalid`,
  invalid_rnc: `${MISSING}.rnc_invalid`,
  missing_amount: `${PLACEHOLDER}.missing_amount`,
  missing_currency: `${PLACEHOLDER}.missing_currency`,
  missing_date: `${MISSING}.date_missing`,
  missing_itbis: `${PLACEHOLDER}.missing_itbis`,
  missing_merchant: `${PLACEHOLDER}.missing_merchant`,
  missing_ncf: `${MISSING}.ncf_missing`,
  missing_rnc: `${MISSING}.rnc_missing`,
  no_purchase_found: `${ATTENTION}.no_purchase_found`,
  not_a_receipt: `${ATTENTION}.not_a_receipt`,
  not_read: "business.inbox.row_saved",
  note: "business.inbox.row_note",
  outcome_unknown: `${ATTENTION}.outcome_unknown`,
  personal: "business.marks.personal_chip",
  read_budget_day: `${ATTENTION}.read_budget_day`,
  read_budget_month: `${ATTENTION}.read_budget_month`,
  review_flag: `${ATTENTION}.check_details`,
  sale: "business.search.badge_venta",
  several_purchases: `${ATTENTION}.several_purchases`,
  sin_comprobante: "business.marks.sin_comprobante_chip",
  source_unavailable: `${ATTENTION}.source_unavailable`,
  unreadable: `${ATTENTION}.unreadable`,
  unverified_sender: `${PLACEHOLDER}.unverified_sender`,
};
