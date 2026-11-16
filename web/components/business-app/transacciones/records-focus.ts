import { reportRequestSchema, type ReportRequest } from "@/lib/business-reports-api";

/** One family and currency over a period, filtered by the server readiness answer. */
export type RecordsFocus = { family: "purchase" | "sale"; currency: string; from: string; to: string; ready: false };

/** The report request that lists exactly the focused records. */
export function focusRequest(focus: RecordsFocus): ReportRequest {
  return reportRequestSchema.parse({
    filters: {
      period: { kind: "custom", from_date: focus.from, to_date: focus.to },
      record_families: [focus.family],
      currencies: [focus.currency],
      ready: focus.ready,
    },
  });
}

export const focusKey = (focus: RecordsFocus | undefined) => (focus ? `${focus.family}:${focus.currency}:${focus.from}:${focus.to}:${focus.ready}` : "default");
