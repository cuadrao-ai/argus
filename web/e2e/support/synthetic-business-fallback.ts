import type { Request } from "@playwright/test";
import { reportAnswerSchema, reportRequestSchema } from "../../lib/business-reports-api";

type SyntheticBusinessRoute = {
  request(): Pick<Request, "url" | "method" | "postDataJSON">;
  fulfill(options: { json: unknown }): Promise<void>;
};

export async function fulfillSyntheticBusinessFallback(route: SyntheticBusinessRoute): Promise<void> {
  const request = route.request();
  const url = new URL(request.url());
  const path = url.pathname.split("/business/")[1];
  if (url.pathname !== "/api/v1/business/reports/query") throw new Error(`Unmapped synthetic endpoint ${path}`);
  if (request.method() !== "POST" || url.search) throw new Error("Synthetic reports/query requires POST without query parameters");
  const report = reportRequestSchema.parse(request.postDataJSON());
  if (report.filters.period.kind !== "all" || report.sort !== "date_desc") throw new Error("Synthetic reports/query supports only all periods and date_desc");
  return route.fulfill({ json: reportAnswerSchema.parse({
    items: [],
    overview: { needs_review: 0, awaiting_approval: 0, ready_for_export: 0 },
    effective_sort: "date_desc",
    sort_unavailable_reason: null,
    matching_count: 0,
    page: report.page,
    page_size: report.page_size,
    page_count: 0,
    totals: [],
    fingerprint: "0".repeat(64),
    captured_at: "2026-10-21T17:45:00Z",
    resolved_period: { from_date: null, to_date: null, calendar: "America/Santo_Domingo" },
    excluded_unknown_dates: 0,
    excluded_personal: { income: 0, expense: 0 },
    counterparties: [],
    categories: [],
    funding_sources: [],
    coverage_notes: [
      "records_only_evidence_separate",
      "legal_cancellation_coverage_unavailable",
      "source_document_subtype_may_be_unknown",
      "counterparty_identity_requires_explicit_tax_id",
    ],
  }) });
}
