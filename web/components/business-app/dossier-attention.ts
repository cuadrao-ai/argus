import type { TFunction } from "i18next";
import { businessDateMessage } from "@/lib/business-date-errors";
import type { BusinessDossier, BusinessFactField, ListoGap, ReviewFlagCode } from "@/lib/business-dossier";
import { documentFamily, factLabel } from "@/lib/counterparty-term";
import type { ReviewRow } from "./receipt-fact-rows";
import type { SaveRow } from "./receipt-review-save";

/** The words of the "Parece repetido" flow: the problem and the compare view. */
export const DUPLICATE_KEYS = "business.receipts.duplicate_resolution";

/** The dossier's tabs. Documento joins them only in the narrow size. */
export type DossierTab = "general" | "documento" | "fiscal" | "detalles" | "historial";

export const FLAGGED_ROW: Record<ReviewFlagCode, ReviewRow> = { rnc_check_digit: "rnc", ncf_malformed: "fiscal_number", itbis_high: "itbis", amounts_mismatch: "amount" };

/** One reason the record is not Listos, as the panel says it: the server's gap, its words, and the row that fixes it. */
export type DossierProblem = {
  key: string;
  reason: ListoGap;
  title: string;
  text: string;
  tab: DossierTab;
  /** The row the problem points at; null when no row holds it. */
  row: ReviewRow | null;
  /** The tab and the row, as the problem list says where to go. */
  where: string;
  /** Only on the "Parece repetido" problem: the first document this one may repeat. */
  compare?: string;
};

type Standing = Pick<BusinessDossier, "listo_gaps" | "review_flags" | "duplicate_candidates" | "document_type" | "facts" | "year_to_check">;

const GAP = "business.dossier.gap";
/** Copy the locked design does not hold yet waits here for its owner. */
const PLACEHOLDER_GAP = "business.dossier.placeholder.gap";
const GAP_ROW: Partial<Record<ListoGap, ReviewRow>> = {
  missing_merchant: "counterparty",
  missing_date: "occurred_on",
  missing_amount: "amount",
  missing_currency: "currency",
  sin_comprobante: "fiscal_number",
  missing_rnc: "rnc",
  invalid_rnc: "rnc",
  missing_ncf: "fiscal_number",
  invalid_ncf: "fiscal_number",
  ecf_check_failed: "fiscal_number",
  missing_itbis: "itbis",
};
/** The gaps whose words the flag copy already owns. */
const OWN_WORDS: Partial<Record<ListoGap, string>> = { invalid_rnc: "business.dossier.review_flag.rnc_check_digit", invalid_ncf: "business.dossier.review_flag.ncf_malformed" };
/** A flag whose own gap already names it: `review_flag` says the others. */
const OWN_GAP: Partial<Record<ReviewFlagCode, ListoGap>> = { rnc_check_digit: "invalid_rnc", ncf_malformed: "invalid_ncf" };

/** The name of a row of the form: the General cards, the problem list and the save lines say the same word. */
export function dossierRowLabel(t: TFunction, row: SaveRow, dossier: Pick<BusinessDossier, "document_type" | "facts"> | null): string {
  const fiscal = dossier?.facts.fiscal;
  switch (row) {
    case "rnc": return (fiscal?.rnc.value ?? "").replace(/\D/g, "").length === 11 ? t("business.dossier.row.cedula") : t("business.dossier.field.rnc");
    case "fiscal_number": return fiscal?.ecf.state === "known" ? t("business.dossier.field.ecf") : t("business.dossier.field.ncf");
    case "occurred_on": return t("business.dossier.row.date");
    case "net_amount": return t("business.dossier.row.subtotal");
    case "itbis": return t("business.terms.itbis");
    case "legal_tip": return t("business.terms.legal_tip");
    case "amount": return t("business.terms.total");
    case "currency": return t("business.dossier.field.currency");
    case "document_type": return t("business.dossier.type_label");
    case "category": return t("business.dossier.placeholder.expense_type");
    case "payment_method": return t("business.dossier.placeholder.payment_form");
    default: return factLabel(t, row, documentFamily(dossier?.document_type));
  }
}

/**
 * Why the record is not Listos: `listo_gaps` item for item, in the server's
 * order. The pill's reason, the problem list, the row status slots and the
 * confirm read this one list. Nothing here decides a reason.
 */
export function dossierProblems(dossier: Standing, t: TFunction): DossierProblem[] {
  const flags = dossier.review_flags ?? [];
  const candidate = dossier.duplicate_candidates?.[0];
  const general = t("business.dossier.tab.general");
  const words = (reason: ListoGap, part: "title" | "text") => t([`${OWN_WORDS[reason] ?? `${GAP}.${reason}`}.${part}`, `${PLACEHOLDER_GAP}.${reason}.${part}`]);
  return (dossier.listo_gaps ?? []).map((reason, index): DossierProblem => {
    const key = `${index}-${reason}`;
    if (reason === "duplicate") {
      const basis = candidate ? `${DUPLICATE_KEYS}.basis.${candidate.basis === "fiscal_number" && documentFamily(dossier.document_type) === "sale" ? "fiscal_number_sale_placeholder" : candidate.basis}` : null;
      return { key, reason, title: t(`${DUPLICATE_KEYS}.title`), text: basis ? t(basis) : words(reason, "text"), tab: "general", row: null, where: `${general} · ${t(`${DUPLICATE_KEYS}.compare`)}`, compare: candidate?.draft_id };
    }
    const flag = reason === "review_flag" ? flags.find((item) => !OWN_GAP[item.code]) ?? flags[0] : undefined;
    const row = flag ? FLAGGED_ROW[flag.code] : reason === "check_details" && dossier.year_to_check ? "occurred_on" : GAP_ROW[reason] ?? null;
    const text = reason === "invalid_rnc" && !flags.some((item) => item.code === "rnc_check_digit") ? t("business.dgii.rnc_check.invalid_length.reason")
      : flag?.code === "amounts_mismatch" ? flag.difference != null ? t("business.terms.difference", { amount: flag.difference }) : words(reason, "text")
      : flag ? t(`business.dossier.review_flag.${flag.code}.text`)
      : words(reason, "text");
    return { key, reason, title: words(reason, "title"), text, tab: "general", row, where: row ? `${general} · ${dossierRowLabel(t, row, dossier)}` : general };
  });
}

/** The problems that point at one row, for its status slot. */
export function rowProblems(problems: readonly DossierProblem[], row: SaveRow): DossierProblem[] {
  return problems.filter((problem) => problem.row === row);
}

export type AttentionItem = {
  key: string;
  /** The row the item points at; null when no row holds it. */
  field: BusinessFactField | null;
  text: string;
  /** Only on the "Parece repetido" item: each document this one may repeat, with why the server says so. */
  duplicates?: readonly { draftId: string; text: string }[];
};

/**
 * What stops approval, as the server's blockers say it, and the documents this
 * one may repeat: the top box, the row markers and the footer read this one
 * list. The duplicate is one item, where its blocker is; a candidate the server
 * lists without a blocker (an RNC and NCF pair) comes last. A recorded approval
 * leaves nothing to do.
 */
export function dossierAttention(dossier: Pick<BusinessDossier, "blockers" | "review_state" | "approval_result" | "duplicate_candidates" | "document_type">, t: TFunction, locale: string): AttentionItem[] {
  if (dossier.review_state === "accepted" && dossier.approval_result?.status === "recorded") return [];
  const candidates = dossier.review_state === "open" ? dossier.duplicate_candidates ?? [] : [];
  const duplicate: AttentionItem = {
    key: "possible-duplicate",
    field: null,
    text: t(`${DUPLICATE_KEYS}.title`, "Looks repeated"),
    duplicates: candidates.map((candidate) => ({ draftId: candidate.draft_id, text: t(`${DUPLICATE_KEYS}.basis.${candidate.basis === "fiscal_number" && documentFamily(dossier.document_type) === "sale" ? "fiscal_number_sale_placeholder" : candidate.basis}`, "") })),
  };
  const items = dossier.blockers.map((blocker, index): AttentionItem => {
    if (blocker.code === "possible_duplicate") return duplicate;
    const label = blocker.field ? factLabel(t, blocker.field, documentFamily(dossier.document_type)) : null;
    const dateMessage = businessDateMessage(blocker, t, locale, label ?? undefined);
    if (dateMessage) return { key: `blocker-${blocker.code}-${index}`, field: blocker.field, text: dateMessage };
    const reason = blocker.code === "fact_required" && label ? null
      : t(`business.dossier.blocker.${blocker.code}`, "") || t("business.dossier.blocker_fallback", "This record needs further review before approval.");
    return { key: `blocker-${blocker.code}-${index}`, field: blocker.field, text: [reason, label].filter(Boolean).join(" · ") };
  });
  const shown = [...new Set(items)];
  return shown.includes(duplicate) || !candidates.length ? shown : [...shown, duplicate];
}
