"use client";

import { useEffect, useState } from "react";
import { getChosenGrant, LOCAL_BUSINESS_PREFIX } from "@/lib/business-grant";
import { listInvoices } from "@/lib/business-invoices-api";
import { businessInvoicingEnabled } from "@/lib/private-alpha-flags";
import { defaultReportRequest } from "@/lib/business-reporting-wire";
import { queryBusinessReport } from "@/lib/business-reports-api";
import { referenceCode } from "@/lib/failure-screen";
import { useBusiness } from "../BusinessWorkspace";
import { INVOICE_STAGE_COUNTS, REPORT_OVERVIEW } from "./home-draft-data";

/** Registros waiting for review, as the server answered it: still loading, unreadable (with its reference), or a number. `none` is a Business with no server to ask. */
export type ReviewCount = { kind: "none" } | { kind: "loading" } | { kind: "failed"; reference: string } | { kind: "ready"; value: number };

type Counts = { key: string; toReview: ReviewCount; drafts: number | null };

/** The preview's sample Business, the only one that shows samples; a person's own local Business never does. */
export function useSampleBusiness() {
  const { source, chosen } = useBusiness();
  return source.mode !== "live" && !chosen?.space_id?.startsWith(LOCAL_BUSINESS_PREFIX);
}

/**
 * Inicio's two counts from other screens: Registros' records waiting for review this month (the report overview,
 * Registros' own default period) and Facturación's saved drafts (stage counts, only where Facturación is on).
 * Live, the review count is loading, failed with a reference to show, or the server's number, and never reads as
 * zero until the server says zero. A failed drafts count leaves its row hidden rather than guessed. The local
 * preview reads the samples.
 */
export function useHomeCounts(): { toReview: ReviewCount; drafts: number | null; retry: () => void } {
  const { source, chosen, userId } = useBusiness();
  const live = source.mode === "live";
  const samples = useSampleBusiness();
  const invoicing = businessInvoicingEnabled || (!live && process.env.NODE_ENV === "development");
  const [attempt, setAttempt] = useState(0);
  const key = `${userId ?? "none"}:${chosen?.space_id ?? "none"}:${attempt}`;
  const [counts, setCounts] = useState<Counts | null>(null);
  useEffect(() => {
    if (!live || !userId || !chosen) return;
    const controller = new AbortController();
    const scope = { userId, businessId: chosen.space_id, grantId: getChosenGrant() };
    const toReview = queryBusinessReport(scope, defaultReportRequest(), controller.signal).then(
      (answer): ReviewCount => (answer.overview ? { kind: "ready", value: answer.overview.needs_review } : { kind: "failed", reference: referenceCode(null) }),
      (error): ReviewCount => ({ kind: "failed", reference: referenceCode(error) }),
    );
    const drafts = invoicing ? listInvoices(scope, { page: 1, page_size: 25, search: "" }, controller.signal).then((page) => page.stage_counts.draft ?? 0, () => null) : Promise.resolve(null);
    void Promise.all([toReview, drafts]).then(([review, draftCount]) => { if (!controller.signal.aborted) setCounts({ key, toReview: review, drafts: draftCount }); });
    return () => controller.abort();
  }, [live, userId, chosen, invoicing, key]);
  const retry = () => setAttempt((value) => value + 1);
  if (samples) return { toReview: { kind: "ready", value: REPORT_OVERVIEW.needs_review }, drafts: invoicing ? INVOICE_STAGE_COUNTS.draft ?? 0 : null, retry };
  if (!live || !userId) return { toReview: { kind: "none" }, drafts: null, retry };
  const current = counts?.key === key ? counts : null;
  return { toReview: current?.toReview ?? { kind: "loading" }, drafts: current?.drafts ?? null, retry };
}
