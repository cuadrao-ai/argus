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
import TransaccionesPanel from "./transacciones/TransaccionesPanel";
import ExpenseDetailPanel from "./ExpenseDetailPanel";
import BusinessSettingsPanel from "./BusinessSettingsPanel";
import ReceiptReviewPanel from "./ReceiptReviewPanel";
import { EmailRecord } from "./BusinessEmailDeliveries";
import PanelErrorBoundary from "./PanelErrorBoundary";
import { formatBusinessName } from "./business-format";
import { RecordTrayContext, recordList } from "./record-tray";
import { primaryButtonClass } from "./business-ui";

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
        <div role="status" data-testid="business-access-line" className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-item border border-[var(--cuadrao-green)]/30 bg-[var(--cuadrao-cream)] px-3.5 py-2.5 text-[13px] text-black/80 dark:bg-white/[0.06] dark:text-white/85">
          <span>{t("business.switcher.access_line", "You now have access to {{name}} · View and prepare", { name: clientName })}</span>
          <button type="button" disabled={access.busy} onClick={() => void access.dismiss()} className={primaryButtonClass}>
            {t("business.switcher.got_it", "Got it")}
          </button>
        </div>
      ) : null}
    </>
  );
}

type RecordPanel = Extract<BusinessPanelState, { kind: "receipt" | "draft" | "expense" | "email" }>;

function recordKey(panel: RecordPanel): string {
  switch (panel.kind) {
    case "receipt": return `receipt:${panel.receiptId}`;
    case "draft": return `draft:${panel.draftId}`;
    case "expense": return `expense:${panel.expenseId}`;
    case "email": return `email:${panel.emailId}`;
  }
}

function RecordContent({ panel }: { panel: RecordPanel }) {
  if (panel.kind === "expense") return <ExpenseDetailPanel key={panel.expenseId} expenseId={panel.expenseId} />;
  if (panel.kind === "email") return <EmailRecord key={panel.emailId} emailId={panel.emailId} />;
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
    if ((panel.kind === "receipt" || panel.kind === "draft") && panel.list === undefined && next !== list) openPanel({ ...panel, list: next });
  }, [list, openPanel, panel]);
  const tray = useMemo(() => ({ footer, settleList }), [footer, settleList]);
  const close = () => {
    const host = listRef.current;
    (host?.querySelector<HTMLElement>('[aria-current="true"] button, tr[aria-selected="true"]') ?? host)?.focus();
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

/** Inside the one canvas every screen starts at its left edge; a list or a form keeps a narrower column there. */
const COLUMN = { canvas: "", reading: "max-w-3xl", form: "max-w-[40rem]" } as const;
const SCREEN_COLUMN: Partial<Record<BusinessPanelState["kind"], keyof typeof COLUMN>> = { overview: "canvas", transactions: "canvas", receipt: "canvas", draft: "canvas", business: "form", expense: "form" };

export default function BusinessPanel() {
  const { panel, lostAccess, records, reload } = useBusiness();
  const { isBelowDesktop } = useResponsiveLayout();
  const listRef = useRef<HTMLDivElement>(null);
  if (records.closed) {
    return (
      <div className={`flex w-full justify-center pb-6 ${COLUMN.reading}`}>
        <BusinessClosedNotice />
      </div>
    );
  }
  if (records.serverReference) return <ServerErrorScreen reference={records.serverReference} onRetry={reload} />;
  if (lostAccess) {
    return (
      <div className={`w-full pb-6 ${COLUMN.reading}`}>
        <BusinessContextCue />
      </div>
    );
  }
  const record = panel.kind === "receipt" || panel.kind === "draft" || panel.kind === "expense" || panel.kind === "email" ? panel : null;
  // On a desktop a record opens in a tray beside its list; below it the record is the whole page.
  const tray = record && !isBelowDesktop ? recordList(record) : null;
  const shown = tray ?? panel.kind;
  const column = SCREEN_COLUMN[shown] ?? "reading";
  return (
    <div ref={listRef} tabIndex={-1} data-column={column} className={`w-full pb-6 outline-none ${COLUMN[column]}`}>
      <BusinessContextCue />
      {/* Keyed by what the page shows, so opening a record beside the list keeps the list mounted. */}
      <PanelErrorBoundary key={tray ?? (record ? recordKey(record) : panel.kind)}>
        {shown === "overview" ? <BusinessOverviewPanel /> : null}
        {shown === "inbox" ? <BusinessInboxPanel /> : null}
        {shown === "transactions" ? <TransaccionesPanel /> : null}
        {shown === "business" ? <BusinessSettingsPanel tab={panel.kind === "business" ? panel.tab : undefined} /> : null}
        {record && !tray ? <RecordContent panel={record} /> : null}
      </PanelErrorBoundary>
      {record && tray ? <RecordTray panel={record} list={tray} listRef={listRef} /> : null}
    </div>
  );
}
