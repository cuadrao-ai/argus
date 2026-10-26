"use client";

import { useEffect, useMemo, useSyncExternalStore } from "react";
import { getChosenGrant, subscribeChosenGrant } from "@/lib/business-grant";
import { createBusinessReportController, type ReportingTransport } from "@/lib/business-reporting-wire";
import type { ReportRequest, ReportScope } from "@/lib/business-reports-api";

export function useBusinessReport(scope: ReportScope, initial?: ReportRequest, transport?: ReportingTransport) {
  const { userId, businessId, grantId } = scope;
  const controller = useMemo(() => createBusinessReportController({ userId, businessId, grantId }, initial, transport), [userId, businessId, grantId, initial, transport]);
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  useEffect(() => {
    void controller.load();
    void controller.listViews();
    const unsubscribe = subscribeChosenGrant(() => { if (getChosenGrant() !== grantId) controller.revoke(); });
    return () => { unsubscribe(); controller.dispose(); };
  }, [controller, grantId]);
  return { controller, state };
}
