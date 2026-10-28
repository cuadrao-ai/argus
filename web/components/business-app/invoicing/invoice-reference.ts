import type { TFunction } from "i18next";
import type { SavedInvoice } from "@/lib/business-invoices-api";

export function invoiceReference(record: Pick<SavedInvoice, "operation" | "created_at">, t: TFunction, locale: string): string {
  if (record.operation?.number) return record.operation.number;
  const day = record.created_at.slice(0, 10), instant = new Date(`${day}T12:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || Number.isNaN(instant.getTime())) return t("business.invoicing.draft_reference_undated");
  return t("business.invoicing.draft_reference", { date: new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(instant) });
}
