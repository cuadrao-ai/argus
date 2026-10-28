import type { BusinessDossier, BusinessFactField, BusinessFiscalField } from "@/lib/business-dossier";
import { ecfRows } from "./ReceiptEcfChecks";
import type { FactRow } from "./receipt-fact-rows";

/** A field a person can be sent to: a record fact or one of the fiscal facts the form shows. */
export type FactKey = BusinessFactField | Exclude<BusinessFiscalField, "include_606">;

export type AttentionItem = {
  key: string;
  /** The row the item points at; "fiscal" is the fiscal number as a whole, null when no row holds it. */
  field: FactKey | "fiscal" | null;
  kind: "blocker" | "check_failed" | "suggestion" | "contradiction";
  text: string;
};

type T = (key: string, fallback: string, options?: Record<string, unknown>) => string;

/** The e-CF compared fields as the form names them. */
const ECF_FIELD: Record<string, FactKey> = { itbis: "itbis", rnc: "rnc", ecf: "ecf", total: "amount", occurred_on: "occurred_on" };

/**
 * What needs the person on this record, in the order the strip lists it: the
 * server's blockers, the e-CF checks that failed, the suggestions nobody has
 * confirmed, and a fiscal number the record and its file disagree on. The
 * strip, the row markers and the footer count all read this one list. A
 * recorded approval leaves nothing to do.
 */
export function dossierAttention(
  dossier: Pick<BusinessDossier, "blockers" | "review_state" | "approval_result" | "ecf_checks" | "fiscal_value" | "facts">,
  rows: readonly FactRow<FactKey | "include_606">[],
  t: T,
): AttentionItem[] {
  if (dossier.review_state === "accepted" && dossier.approval_result?.status === "recorded") return [];
  const label = (field: string) => t(`business.dossier.field.${field}`, field);
  const items: AttentionItem[] = dossier.blockers.map((blocker, index) => {
    const reason = t(
      blocker.code === "possible_duplicate" ? "business.attention.duplicate" : `business.dossier.blocker.${blocker.code}`,
      t("business.dossier.blocker_fallback", "This record needs further review before approval."),
    );
    return { key: `blocker-${blocker.code}-${index}`, field: blocker.field, kind: "blocker", text: blocker.field ? `${reason} · ${label(blocker.field)}` : reason };
  });

  const verification = dossier.ecf_checks;
  if (verification) {
    // One item per field the read and the XML disagree on, in the same words as the e-CF card, so each points at its row.
    const read = verification.checks.find((check) => check.name === "read_matches_xml" && check.state === "failed");
    const compared = Object.keys(read?.detail ?? {});
    for (const name of compared) {
      items.push({ key: `check-read-${name}`, field: ECF_FIELD[name] ?? null, kind: "check_failed", text: t("business.dossier.ecf_read_failed", "Review: the read differs from the XML in {{fields}}", { fields: t(`business.dossier.ecf_field_${name}`, name) }) });
    }
    for (const row of ecfRows(verification, t)) {
      if (row.state !== "failed" || (row.key === "read" && compared.length)) continue;
      items.push({ key: `check-${row.key}`, field: null, kind: "check_failed", text: `${row.title}: ${row.caption}` });
    }
  }

  const named = new Set(items.map((item) => item.field));
  for (const row of rows) {
    const field = row.key;
    if (field === "include_606" || row.standing !== "suggestion" || named.has(field)) continue;
    items.push({ key: `suggestion-${field}`, field, kind: "suggestion", text: t("business.dossier.attention.suggestion", "{{field}}: suggestion to confirm", { field: label(field) }) });
  }

  const encf = verification?.encf;
  if (encf && (dossier.fiscal_value === "ncf" || dossier.facts.fiscal?.ecf.state === "owner_does_not_know")) {
    items.push({ key: "contradiction-fiscal", field: "fiscal", kind: "contradiction", text: t("business.dossier.attention.fiscal_disagree", "The record and its file disagree on the fiscal number: the file carries e-CF {{encf}}.", { encf }) });
  }
  return items;
}
