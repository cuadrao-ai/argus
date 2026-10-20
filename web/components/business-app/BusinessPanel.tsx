"use client";

import { useCallback, useMemo, useRef, useState, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { BusinessClosedNotice } from "@/components/status/BusinessClosedNotice";
import { RemovedMemberScreen } from "@/components/status/RemovedMemberScreen";
import { ServerErrorScreen } from "@/components/status/ServerErrorScreen";
import { useBusiness, type BusinessPanelState, type RecordList } from "./BusinessWorkspace";
import { useAccessBanner } from "./useAccessBanner";
import BusinessOverviewPanel from "./BusinessOverviewPanel";
import BusinessInboxPanel from "./BusinessInboxPanel";
import BusinessExpensesPanel from "./BusinessExpensesPanel";
import ExpenseDetailPanel from "./ExpenseDetailPanel";
import BusinessAccessPanel from "./BusinessAccessPanel";
import ReceiptReviewPanel from "./ReceiptReviewPanel";
import PanelErrorBoundary from "./PanelErrorBoundary";
import { formatBusinessName } from "./business-format";
import { RecordTrayContext, recordList } from "./record-tray";

/**
 * Inside a client's Business every screen says so, and the first landing
 * carries a one-line welcome the person dismisses once; the server remembers
 * the dismissal per grant. A grant that died mid-session says so, once.
 */
export function BusinessContextCue() {
  const { t } = useTranslation();
  const { chosen, lostAccess, clearLostAccess } = useBusiness();
  const access = useAccessBanner();
  const client = chosen && chosen.role !== "owner" ? chosen : null;
  const clientName = formatBusinessName(client?.name, t("business.overview.title", "My business"));
  return (
    <>
      {lostAccess ? <RemovedMemberScreen onReturn={clearLostAccess} /> : null}
      {client ? (
        <p data-testid="business-client-cue" className="mb-3 text-[13px] font-medium text-[var(--cuadrao-green)]">
          {t("business.switcher.client_cue", "Client: {{name}}", { name: clientName })}
        </p>
      ) : null}
      {access.visible ? (
        <div role="status" data-testid="business-access-line" className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-[14px] border border-[var(--cuadrao-green)]/30 bg-[var(--cuadrao-cream)] px-3.5 py-2.5 text-[13px] text-black/80 dark:bg-white/[0.06] dark:text-white/85">
          <span>{t("business.switcher.access_line", "You now have access to {{name}} · View and prepare", { name: clientName })}</span>
          <button type="button" disabled={access.busy} onClick={() => void access.dismiss()} className="inline-flex min-h-9 items-center rounded-full bg-[var(--cuadrao-green)] px-3 text-[12px] font-medium text-[var(--cuadrao-cream)] transition-opacity hover:opacity-85 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40">
            {t("business.switcher.got_it", "Got it")}
          </button>
        </div>
      ) : null}
    </>
  );
}

type RecordPanel = Extract<BusinessPanelState, { kind: "receipt" | "draft" | "expense" }>;

function recordKey(panel: RecordPanel): string {
  return panel.kind === "receipt" ? `receipt:${panel.receiptId}` : panel.kind === "draft" ? `draft:${panel.draftId}` : `expense:${panel.expenseId}`;
}

function RecordContent({ panel }: { panel: RecordPanel }) {
  if (panel.kind === "expense") return <ExpenseDetailPanel key={panel.expenseId} expenseId={panel.expenseId} />;
  if (panel.kind === "receipt") return <ReceiptReviewPanel key={panel.receiptId} target={{ kind: "receipt", id: panel.receiptId }} />;
  return <ReceiptReviewPanel key={panel.draftId} target={{ kind: "draft", id: panel.draftId }} />;
}

/**
 * A record beside the list it came from, on a desktop. The tray is not modal:
 * a click on another row swaps the record, and closing returns to the list
 * with focus on the row that was open.
 */
function RecordTray({ panel, list, listRef }: { panel: RecordPanel; list: RecordList; listRef: RefObject<HTMLDivElement | null> }) {
  const { t } = useTranslation();
  const { openPanel } = useBusiness();
  const [footer, setFooter] = useState<HTMLDivElement | null>(null);
  const settleList = useCallback((next: RecordList) => {
    if (panel.kind !== "expense" && panel.list === undefined && next !== list) openPanel({ ...panel, list: next });
  }, [list, openPanel, panel]);
  const tray = useMemo(() => ({ footer, settleList }), [footer, settleList]);
  const close = () => {
    const host = listRef.current;
    (host?.querySelector<HTMLElement>('[aria-current="true"] button') ?? host)?.focus();
    openPanel({ kind: list });
  };
  return (
    <AdaptivePanel
      modal={false}
      width="record"
      title={t("business.tray.title", "Details")}
      closeLabel={t("common.close", "Close")}
      onClose={close}
      footer={<div ref={setFooter} data-footer-slot="" />}
    >
      <RecordTrayContext.Provider value={tray}>
        <div className="px-5 py-5">
          <PanelErrorBoundary key={recordKey(panel)}>
            <RecordContent panel={panel} />
          </PanelErrorBoundary>
        </div>
      </RecordTrayContext.Provider>
    </AdaptivePanel>
  );
}

export default function BusinessPanel() {
  const { panel, lostAccess, records, reload } = useBusiness();
  const { isBelowDesktop } = useResponsiveLayout();
  const listRef = useRef<HTMLDivElement>(null);
  if (records.closed) {
    return (
      <div className="mx-auto flex w-full max-w-3xl justify-center pb-6">
        <BusinessClosedNotice />
      </div>
    );
  }
  if (records.serverReference) return <ServerErrorScreen reference={records.serverReference} onRetry={reload} />;
  if (lostAccess) {
    return (
      <div className="mx-auto w-full max-w-3xl pb-6">
        <BusinessContextCue />
      </div>
    );
  }
  const record = panel.kind === "receipt" || panel.kind === "draft" || panel.kind === "expense" ? panel : null;
  // On a desktop a record opens in a tray beside its list; below it the record is the whole page.
  const tray = record && !isBelowDesktop ? recordList(record) : null;
  const shown = tray ?? panel.kind;
  return (
    <div ref={listRef} tabIndex={-1} className={`mx-auto w-full outline-none ${record && !tray && record.kind !== "expense" ? "" : "max-w-3xl pb-6"}`}>
      <BusinessContextCue />
      {/* Keyed by what the page shows, so opening a record beside the list keeps the list mounted. */}
      <PanelErrorBoundary key={tray ?? (record ? recordKey(record) : panel.kind)}>
        {shown === "overview" ? <BusinessOverviewPanel /> : null}
        {shown === "inbox" ? <BusinessInboxPanel /> : null}
        {shown === "expenses" ? <BusinessExpensesPanel /> : null}
        {shown === "access" ? <BusinessAccessPanel /> : null}
        {record && !tray ? <RecordContent panel={record} /> : null}
      </PanelErrorBoundary>
      {record && tray ? <RecordTray panel={record} list={tray} listRef={listRef} /> : null}
    </div>
  );
}
