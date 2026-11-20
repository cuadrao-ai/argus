import type { TFunction } from "i18next";
import { businessDateMessage } from "@/lib/business-date-errors";
import type { BusinessDossier, BusinessFactField } from "@/lib/business-dossier";
import { documentFamily, factLabel } from "@/lib/counterparty-term";

/** The words of the "Parece repetido" flow: the top box and the compare view. */
export const DUPLICATE_KEYS = "business.receipts.duplicate_resolution";

export type AttentionItem = {
  key: string;
  /** The row the item points at; null when no row holds it. */
  field: BusinessFactField | null;
  text: string;
  /** Only on the "Parece repetido" item: each document this one may repeat, with why the server says so. */
  duplicates?: readonly { draftId: string; text: string }[];
};

type T = TFunction;

/**
 * What stops approval, as the server's blockers say it, and the documents this
 * one may repeat: the top box, the row markers and the footer read this one
 * list. The duplicate is one item, where its blocker is; a candidate the server
 * lists without a blocker (an RNC and NCF pair) comes last. A recorded approval
 * leaves nothing to do.
 */
export function dossierAttention(dossier: Pick<BusinessDossier, "blockers" | "review_state" | "approval_result" | "duplicate_candidates" | "document_type">, t: T, locale: string): AttentionItem[] {
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
