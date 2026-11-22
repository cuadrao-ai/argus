import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import { resolveLanguage } from "@/lib/language-features";
import { formatMoney, formatRelativeTime } from "../business-format";
import { useBusiness } from "../BusinessWorkspace";
import type { JumpRow } from "./DossierHeader";

/**
 * The jump card's rows: the documents of the run in the order the panel was
 * opened with, each as the server's list says it now: its label, whether it is
 * unopened, how long it has waited, who issued it and its total. The list is
 * asked for when the card opens, so the card shows the server's last answer and
 * the panel pays for it only when someone looks. Null until it has answered.
 */
export function useJumpRows(receiptIds: readonly string[]): { rows: JumpRow[] | null; load: () => void } {
  const { t, i18n } = useTranslation();
  const { source } = useBusiness();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const [listed, setListed] = useState<{ source: typeof source; items: readonly ReceiptSummary[] } | null>(null);
  const load = useCallback(() => {
    const asked = source.receiptPage ? source.receiptPage("all").then((page) => page.items) : source.receipts("all");
    asked.then((items) => setListed({ source, items }), () => setListed({ source, items: [] }));
  }, [source]);
  if (!listed || listed.source !== source) return { rows: null, load };
  const byId = new Map(listed.items.map((receipt) => [receipt.id, receipt]));
  const rows = receiptIds.flatMap((id): JumpRow[] => {
    const receipt = byId.get(id);
    return receipt ? [{
      id,
      name: receipt.merchant || receipt.filename || t("business.document_delete.unnamed"),
      label: receipt.bandeja_group?.label ?? null,
      unopened: receipt.activity?.unread === true,
      wait: formatRelativeTime(receipt.received_at, locale),
      total: formatMoney(receipt.amount, receipt.currency, locale) || "",
    }] : [];
  });
  return { rows, load };
}
