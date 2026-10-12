"use client";

import { useBusiness } from "./BusinessWorkspace";
import BusinessOverviewPanel from "./BusinessOverviewPanel";
import BusinessInboxPanel from "./BusinessInboxPanel";
import BusinessExpensesPanel from "./BusinessExpensesPanel";
import BusinessAccessPanel from "./BusinessAccessPanel";
import BusinessUpdatesPanel from "./BusinessUpdatesPanel";
import ReceiptReviewPanel from "./ReceiptReviewPanel";
import PanelErrorBoundary from "./PanelErrorBoundary";
import { SampleDataNotice } from "./business-ui";

export default function BusinessPanel() {
  const { panel } = useBusiness();
  return (
    <div className="mx-auto w-full max-w-3xl pb-6">
      <SampleDataNotice />
      <PanelErrorBoundary key={panel.kind === "receipt" ? `receipt:${panel.receiptId}` : panel.kind === "draft" ? `draft:${panel.draftId}` : panel.kind}>
        {panel.kind === "overview" ? <BusinessOverviewPanel /> : null}
        {panel.kind === "inbox" ? <BusinessInboxPanel /> : null}
        {panel.kind === "expenses" ? <BusinessExpensesPanel /> : null}
        {panel.kind === "updates" ? <BusinessUpdatesPanel /> : null}
        {panel.kind === "access" ? <BusinessAccessPanel /> : null}
        {panel.kind === "receipt" ? <ReceiptReviewPanel key={panel.receiptId} target={{ kind: "receipt", id: panel.receiptId }} /> : null}
        {panel.kind === "draft" ? <ReceiptReviewPanel key={panel.draftId} target={{ kind: "draft", id: panel.draftId }} /> : null}
      </PanelErrorBoundary>
    </div>
  );
}
