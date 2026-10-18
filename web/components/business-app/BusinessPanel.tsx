"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useBusiness } from "./BusinessWorkspace";
import BusinessSectionActions from "./BusinessSectionActions";
import BusinessOverviewPanel from "./BusinessOverviewPanel";
import BusinessInboxPanel from "./BusinessInboxPanel";
import BusinessExpensesPanel from "./BusinessExpensesPanel";
import ExpenseDetailPanel from "./ExpenseDetailPanel";
import BusinessAccessPanel from "./BusinessAccessPanel";
import BusinessUpdatesPanel from "./BusinessUpdatesPanel";
import ReceiptReviewPanel from "./ReceiptReviewPanel";
import PanelErrorBoundary from "./PanelErrorBoundary";
import { SampleDataNotice } from "./business-ui";
import { formatBusinessName } from "./business-format";

/**
 * Inside a client's Business every screen says so, and the first landing
 * carries a one-line welcome the person dismisses once; the server remembers
 * the dismissal per grant. A grant that died mid-session says so, once.
 */
export function BusinessContextCue() {
  const { t } = useTranslation();
  const { chosen, markAccessSeen, lostAccess } = useBusiness();
  const [busy, setBusy] = useState(false);
  const client = chosen && chosen.role !== "owner" ? chosen : null;
  const clientName = formatBusinessName(client?.name, t("business.overview.title", "My business"));
  return (
    <>
      {lostAccess ? (
        <p role="status" data-testid="business-access-lost" className="mb-3 rounded-[14px] bg-[var(--cuadrao-cream)] px-3.5 py-2.5 text-[13px] text-black/75 dark:bg-white/[0.06] dark:text-white/80">
          {t("business.switcher.lost", "You no longer have access to this Business.")}
        </p>
      ) : null}
      {client ? (
        <p data-testid="business-client-cue" className="mb-3 text-[13px] font-medium text-[var(--cuadrao-green)]">
          {t("business.switcher.client_cue", "Client: {{name}}", { name: clientName })}
        </p>
      ) : null}
      {client && !client.access_seen ? (
        <div role="status" data-testid="business-access-line" className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-[14px] border border-[var(--cuadrao-green)]/30 bg-[var(--cuadrao-cream)] px-3.5 py-2.5 text-[13px] text-black/80 dark:bg-white/[0.06] dark:text-white/85">
          <span>{t("business.switcher.access_line", "You now have access to {{name}} · View and prepare", { name: clientName })}</span>
          <button type="button" disabled={busy} onClick={async () => { setBusy(true); try { await markAccessSeen(); } catch { /* shown again next time */ } finally { setBusy(false); } }} className="inline-flex min-h-9 items-center rounded-full bg-[var(--cuadrao-green)] px-3 text-[12px] font-medium text-[var(--cuadrao-cream)] transition-opacity hover:opacity-85 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40">
            {t("business.switcher.got_it", "Got it")}
          </button>
        </div>
      ) : null}
    </>
  );
}

export default function BusinessPanel() {
  const { panel } = useBusiness();
  return (
    <div className="mx-auto w-full max-w-3xl pb-6">
      <SampleDataNotice />
      <BusinessContextCue />
      <BusinessSectionActions />
      <PanelErrorBoundary key={panel.kind === "receipt" ? `receipt:${panel.receiptId}` : panel.kind === "draft" ? `draft:${panel.draftId}` : panel.kind === "expense" ? `expense:${panel.expenseId}` : panel.kind}>
        {panel.kind === "overview" ? <BusinessOverviewPanel /> : null}
        {panel.kind === "inbox" ? <BusinessInboxPanel /> : null}
        {panel.kind === "expenses" ? <BusinessExpensesPanel /> : null}
        {panel.kind === "expense" ? <ExpenseDetailPanel key={panel.expenseId} expenseId={panel.expenseId} /> : null}
        {panel.kind === "updates" ? <BusinessUpdatesPanel /> : null}
        {panel.kind === "access" ? <BusinessAccessPanel /> : null}
        {panel.kind === "receipt" ? <ReceiptReviewPanel key={panel.receiptId} target={{ kind: "receipt", id: panel.receiptId }} /> : null}
        {panel.kind === "draft" ? <ReceiptReviewPanel key={panel.draftId} target={{ kind: "draft", id: panel.draftId }} /> : null}
      </PanelErrorBoundary>
    </div>
  );
}
