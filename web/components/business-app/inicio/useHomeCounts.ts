"use client";

import { useEffect, useState } from "react";
import { getChosenGrant, LOCAL_BUSINESS_PREFIX } from "@/lib/business-grant";
import { listInvoices } from "@/lib/business-invoices-api";
import { referenceCode } from "@/lib/failure-screen";
import { invoicingShown, useBusiness } from "../BusinessWorkspace";
import { inboxCount } from "../inbox-count";
import { INVOICE_STAGE_COUNTS } from "./home-draft-data";

/** Bandeja rows waiting for review, as the server answered it: still loading, unreadable (with its reference), or a number. `none` is a Business with no server to ask. */
export type ReviewCount = { kind: "none" } | { kind: "loading" } | { kind: "failed"; reference: string } | { kind: "ready"; value: number };

type Counts = { key: string; drafts: number | null };

/** The preview's sample Business, the only one that shows samples; a person's own local Business never does. */
export function useSampleBusiness() {
  const { source, chosen } = useBusiness();
  return source.mode !== "live" && !chosen?.space_id?.startsWith(LOCAL_BUSINESS_PREFIX);
}

/** Receipt review uses the shared Bandeja count. Only invoice drafts need a separate request. */
export function useHomeCounts(): { toReview: ReviewCount; drafts: number | null; retry: () => void } {
  const { source, chosen, userId, records, reload, invoicing: invoicingState } = useBusiness();
  const live = source.mode === "live";
  const samples = useSampleBusiness();
  const invoicing = invoicingShown(invoicingState);
  const key = `${userId ?? "none"}:${chosen?.space_id ?? "none"}`;
  const [counts, setCounts] = useState<Counts | null>(null);
  useEffect(() => {
    if (!live || !userId || !chosen || !invoicing) return;
    const controller = new AbortController();
    const scope = { userId, businessId: chosen.space_id, grantId: getChosenGrant() };
    void listInvoices(scope, { page: 1, page_size: 25, search: "" }, controller.signal)
      .then((page) => page.stage_counts.draft ?? 0, () => null)
      .then((drafts) => { if (!controller.signal.aborted) setCounts({ key, drafts }); });
    return () => controller.abort();
  }, [live, userId, chosen, invoicing, key]);
  const waiting = inboxCount(records);
  const toReview: ReviewCount = records.error || (waiting === null && records.serverReference)
    ? { kind: "failed", reference: records.failureReference ?? records.serverReference ?? referenceCode(null) }
    : waiting !== null ? { kind: "ready", value: waiting }
    : live ? { kind: "loading" } : { kind: "none" };
  if (samples) return { toReview, drafts: invoicing ? INVOICE_STAGE_COUNTS.draft ?? 0 : null, retry: reload };
  const current = live && invoicing && counts?.key === key ? counts : null;
  return { toReview, drafts: current?.drafts ?? null, retry: reload };
}
