import type { TFunction } from "i18next";
import type { SavedInvoice } from "@/lib/business-invoices-api";
import { formatDate } from "../business-format";

export function invoiceReference(record: Pick<SavedInvoice, "operation" | "created_at">, t: TFunction, locale: string): string {
  if (record.operation?.number) return record.operation.number;
  const instant = new Date(record.created_at);
  if (Number.isNaN(instant.getTime())) return t("business.invoicing.draft_reference_undated");
  return t("business.invoicing.draft_reference", { date: formatDate(instant, locale, { day: "numeric", month: "short", year: "numeric" }) });
}
