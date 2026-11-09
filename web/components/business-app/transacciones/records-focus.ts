import { reportRequestSchema, type ReportRequest } from "@/lib/business-reports-api";

/**
 * One Registros list another screen counted: a family's records in one currency, over a period, that the 606 or
 * 607 still holds ("Faltan datos fiscales"). Registros shows one family and one currency at a time, so a focus
 * names exactly one of each.
 */
export type RecordsFocus = { family: "purchase" | "sale"; currency: string; from: string; to: string; fiscal_data: "missing" };

/** The report request that lists exactly the focused records. */
export function focusRequest(focus: RecordsFocus): ReportRequest {
  return reportRequestSchema.parse({
    filters: {
      period: { kind: "custom", from_date: focus.from, to_date: focus.to },
      record_families: [focus.family],
      currencies: [focus.currency],
      fiscal_data: focus.fiscal_data,
    },
  });
}

export const focusKey = (focus: RecordsFocus | undefined) => (focus ? `${focus.family}:${focus.currency}:${focus.from}:${focus.to}:${focus.fiscal_data}` : "default");
