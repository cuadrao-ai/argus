"use client";

import { useEffect, useState } from "react";
import { getChosenGrant, LOCAL_BUSINESS_PREFIX } from "@/lib/business-grant";
import { listInvoices } from "@/lib/business-invoices-api";
import { businessInvoicingEnabled } from "@/lib/private-alpha-flags";
import { defaultReportRequest } from "@/lib/business-reporting-wire";
import { queryBusinessReport } from "@/lib/business-reports-api";
import { useBusiness } from "../BusinessWorkspace";
import { INVOICE_STAGE_COUNTS, REPORT_OVERVIEW } from "./home-draft-data";

type Counts = { key: string; toReview: number | null; drafts: number | null };

/** The preview's sample Business, the only one that shows samples; a person's own local Business never does. */
export function useSampleBusiness() {
  const { source, chosen } = useBusiness();
  return source.mode !== "live" && !chosen?.space_id?.startsWith(LOCAL_BUSINESS_PREFIX);
}

/**
 * Inicio's two counts from other screens: Registros' records waiting for review this month (the report overview,
 * Registros' own default period) and Facturación's saved drafts (stage counts, only where Facturación is on).
 * Live, each comes from its endpoint; a failure leaves it null, so its row stays hidden rather than guessed. The
 * local preview reads the samples.
 */
export function useHomeCounts() {
  const { source, chosen, userId } = useBusiness();
  const live = source.mode === "live";
  const samples = useSampleBusiness();
  const invoicing = businessInvoicingEnabled || (!live && process.env.NODE_ENV === "development");
  const key = `${userId ?? "none"}:${chosen?.space_id ?? "none"}`;
  const [counts, setCounts] = useState<Counts | null>(null);
  useEffect(() => {
    if (!live || !userId || !chosen) return;
    const controller = new AbortController();
    const scope = { userId, businessId: chosen.space_id, grantId: getChosenGrant() };
    const settle = <T,>(request: Promise<T>, read: (value: T) => number | null) => request.then(read, () => null);
    void Promise.all([
      settle(queryBusinessReport(scope, defaultReportRequest(), controller.signal), (answer) => answer.overview?.needs_review ?? null),
      invoicing ? settle(listInvoices(scope, { page: 1, page_size: 25, search: "" }, controller.signal), (page) => page.stage_counts.draft ?? 0) : Promise.resolve(null),
    ]).then(([toReview, drafts]) => { if (!controller.signal.aborted) setCounts({ key, toReview, drafts }); });
    return () => controller.abort();
  }, [live, userId, chosen, invoicing, key]);
  if (samples) return { toReview: REPORT_OVERVIEW.needs_review, drafts: invoicing ? INVOICE_STAGE_COUNTS.draft ?? 0 : null };
  if (!live) return { toReview: null, drafts: null };
  const current = counts?.key === key ? counts : null;
  return { toReview: current?.toReview ?? null, drafts: current?.drafts ?? null };
}
