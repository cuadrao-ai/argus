"use client";

import { useEffect, useState } from "react";
import { getChosenGrant, LOCAL_BUSINESS_PREFIX } from "@/lib/business-grant";
import { listInvoices } from "@/lib/business-invoices-api";
import { invoicingShown, useBusiness } from "../BusinessWorkspace";
import { INVOICE_STAGE_COUNTS } from "./home-draft-data";

type Counts = { key: string; drafts: number | null };

/** The preview's sample Business, the only one that shows samples; a person's own local Business never does. */
export function useSampleBusiness() {
  const { source, chosen } = useBusiness();
  return source.mode !== "live" && !chosen?.space_id?.startsWith(LOCAL_BUSINESS_PREFIX);
}

/** Invoice drafts, the one count Inicio reads on its own; the Bandeja's numbers come with the workspace records. */
export function useHomeCounts(): { drafts: number | null } {
  const { source, chosen, userId, invoicing: invoicingState } = useBusiness();
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
  if (samples) return { drafts: invoicing ? INVOICE_STAGE_COUNTS.draft ?? 0 : null };
  const current = live && invoicing && counts?.key === key ? counts : null;
  return { drafts: current?.drafts ?? null };
}
