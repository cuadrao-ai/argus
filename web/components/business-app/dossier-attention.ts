import type { BusinessDossier, BusinessFactField } from "@/lib/business-dossier";

export type AttentionItem = {
  key: string;
  /** The row the item points at; null when no row holds it. */
  field: BusinessFactField | null;
  text: string;
};

type T = (key: string, fallback: string, options?: Record<string, unknown>) => string;

/**
 * What stops approval, as the server's blockers say it, and nothing else: the
 * top box, the row markers and the footer read this one list. A recorded
 * approval leaves nothing to do.
 */
export function dossierAttention(dossier: Pick<BusinessDossier, "blockers" | "review_state" | "approval_result">, t: T): AttentionItem[] {
  if (dossier.review_state === "accepted" && dossier.approval_result?.status === "recorded") return [];
  return dossier.blockers.map((blocker, index) => {
    const label = blocker.field ? t(`business.dossier.field.${blocker.field}`, blocker.field) : null;
    const reason = blocker.code === "fact_required" && label ? null
      : t(blocker.code === "possible_duplicate" ? "business.attention.duplicate" : `business.dossier.blocker.${blocker.code}`, "") || t("business.dossier.blocker_fallback", "This record needs further review before approval.");
    return { key: `blocker-${blocker.code}-${index}`, field: blocker.field, text: [reason, label].filter(Boolean).join(" · ") };
  });
}
