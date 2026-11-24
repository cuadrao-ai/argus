"use client";

import { useCallback, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { BusinessClosedNotice } from "@/components/status/BusinessClosedNotice";
import { RemovedMemberScreen } from "@/components/status/RemovedMemberScreen";
import { ServerErrorScreen } from "@/components/status/ServerErrorScreen";
import { invoicingShown, useBusiness, type BusinessPanelState, type RecordList } from "./BusinessWorkspace";
import { useAccessBanner } from "./useAccessBanner";
import BusinessOverviewPanel from "./BusinessOverviewPanel";
import BusinessInboxPanel from "./BusinessInboxPanel";
import TransaccionesPanel from "./transacciones/TransaccionesPanel";
import InvoiceWorkspaceEntry from "./invoicing/InvoiceWorkspaceEntry";
import ActivityDraft from "./actividad/ActivityDraft";
import BusinessSettingsPanel from "./BusinessSettingsPanel";
import ReceiptReviewPanel from "./ReceiptReviewPanel";
import { EmailRecord } from "./BusinessEmailDeliveries";
import PanelErrorBoundary from "./PanelErrorBoundary";
import { formatBusinessName } from "./business-format";
import { RecordTrayContext, isRecordPanel, recordInTray, recordList, shownScreen, type RecordPanel } from "./record-tray";
import { primaryButtonClass } from "./business-ui";

/**
 * While invitations are on, the first landing in a client's Business carries a
 * one-line welcome the person dismisses once; the server remembers the
 * dismissal per grant. A grant that died mid-session says so, once.
 */
export function BusinessContextCue() {
  const { t } = useTranslation();
  const { chosen, lostAccess, clearLostAccess } = useBusiness();
  const access = useAccessBanner();
  const clientName = formatBusinessName(chosen?.name, t("business.overview.title", "My business"));
  return (
    <>
      {lostAccess ? <RemovedMemberScreen onReturn={clearLostAccess} /> : null}
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

function recordKey(panel: RecordPanel): string {
  switch (panel.kind) {
    case "receipt": return `receipt:${panel.receiptId}`;
    case "draft": return `draft:${panel.draftId}`;
    case "expense": return `expense:${panel.expenseId}`;
    case "email": return `email:${panel.emailId}`;
  }
}

/** Every record opens the one dossier, whichever id it was opened by. An email is a delivery, not a record. */
function RecordContent({ panel }: { panel: RecordPanel }) {
  if (panel.kind === "email") return <EmailRecord key={panel.emailId} emailId={panel.emailId} />;
  const id = panel.kind === "receipt" ? panel.receiptId : panel.kind === "draft" ? panel.draftId : panel.expenseId;
  return <ReceiptReviewPanel key={recordKey(panel)} target={{ kind: panel.kind, id }} detailsCard={panel.detailsCard} />;
}

/**
 * A record on a desktop: beside Registros, which it came from, or in the wide dossier over the
 * Bandeja. The tray is not modal: a click on another row swaps the record. AdaptivePanel closes it
 * and puts focus back on the row that was open; the workspace's panel guard asks first while the
 * record holds an unsaved edit.
 */
function RecordTray({ panel, list, listRef, returnFocusRef }: { panel: RecordPanel; list: RecordList | null; listRef: RefObject<HTMLDivElement | null>; returnFocusRef: RefObject<HTMLElement | null> }) {
  const { t } = useTranslation();
  const { openPanel } = useBusiness();
  const [footer, setFooter] = useState<HTMLDivElement | null>(null);
  const [summary, setSummary] = useState<HTMLDivElement | null>(null);
  const [headerActions, setHeaderActions] = useState<HTMLDivElement | null>(null);
  const [title, setTitle] = useState<ReactNode>(null);
  // A dossier makes the drawer's header its own: its name, status and place in the list.
  const dossier = panel.kind !== "email";
  const settleList = useCallback((next: RecordList) => {
    if ((panel.kind === "receipt" || panel.kind === "draft") && panel.list === undefined) openPanel({ ...panel, list: next });
  }, [openPanel, panel]);
  // A dossier opens wide over the Bandeja and narrow beside Registros; its size button switches between the two.
  const [resized, setResized] = useState<boolean | null>(null);
  const narrow = resized ?? list === "transactions";
  const toggleNarrow = useCallback(() => setResized((current) => !(current ?? list === "transactions")), [list]);
  const tray = useMemo(() => ({ footer, summary: dossier ? summary : null, headerActions: dossier ? headerActions : null, setTitle, settleList, ...(dossier ? { narrow, toggleNarrow } : {}) }), [footer, summary, headerActions, dossier, settleList, narrow, toggleNarrow]);
  const close = () => {
    const host = listRef.current;
    returnFocusRef.current = host?.querySelector<HTMLElement>('[aria-current="true"] button, tr[aria-selected="true"]') ?? host;
    openPanel({ kind: list ?? "inbox" });
  };
  return (
    <AdaptivePanel
      modal={false}
      width={dossier && narrow ? "record" : "dossier"}
      title={(dossier ? title : null) ?? t("business.tray.title", "Details")}
      titleId={dossier ? "receipt-review-title" : undefined}
      headerSize={dossier ? "large" : "default"}
      summary={dossier ? <div ref={setSummary} data-header-slot="" /> : undefined}
      headerActions={dossier ? <div ref={setHeaderActions} data-header-actions="" className="flex items-center empty:hidden" /> : undefined}
      closeLabel={t("common.close", "Close")}
      onClose={close}
      returnFocusRef={returnFocusRef}
      footer={<div ref={setFooter} data-footer-slot="" />}
    >
      <RecordTrayContext.Provider value={tray}>
        {/* A receipt's dossier fills the drawer: its tabs and its document scroll on their own. */}
        <div className={dossier ? "relative h-full" : "px-5 py-5"}>
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
const SCREEN_COLUMN: Partial<Record<BusinessPanelState["kind"], keyof typeof COLUMN>> = { overview: "canvas", inbox: "canvas", transactions: "canvas", invoicing: "canvas", activity: "canvas", receipt: "canvas", draft: "canvas", business: "canvas", expense: "canvas" };

export default function BusinessPanel() {
  const { panel, lostAccess, records, reload, chosen, userId, directoryStatus, directoryReference, inboxReady, invoicing } = useBusiness();
  const { isBelowDesktop } = useResponsiveLayout();
  const listRef = useRef<HTMLDivElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  if (records.closed) {
    return (
      <div className={`flex w-full justify-center pb-6 ${COLUMN.reading}`}>
        <BusinessClosedNotice />
      </div>
    );
  }
  if (records.serverReference) return <ServerErrorScreen reference={records.serverReference} onRetry={reload} />;
  if (panel.kind === "inbox" && inboxReady === false && directoryReference) return <ServerErrorScreen reference={directoryReference} onRetry={reload} />;
  if (lostAccess) {
    return (
      <div className={`w-full pb-6 ${COLUMN.reading}`}>
        <BusinessContextCue />
      </div>
    );
  }
  const record = isRecordPanel(panel) ? panel : null;
  const inTray = recordInTray(panel, isBelowDesktop);
  const tray = inTray ? recordList(panel) : null;
  const shown = shownScreen(panel, isBelowDesktop);
  // Negocio bounds its own columns through SettingsLayout, so every tab shares one left edge and width.
  const column = SCREEN_COLUMN[shown] ?? "reading";
  return (
    <div ref={listRef} tabIndex={-1} data-column={column} className={`w-full ${record && !inTray ? "pb-0" : "pb-6"} outline-none ${COLUMN[column]}`}>
      <BusinessContextCue />
      {/* A dossier tray lies over the list, so what it covers leaves the Tab order and the accessibility tree. */}
      <div inert={tray === "inbox" ? true : undefined}>
      {/* Keyed by what the page shows, so opening a record beside the list keeps the list mounted. */}
      <PanelErrorBoundary key={record && !inTray ? recordKey(record) : shown}>
        {shown === "overview" ? <BusinessOverviewPanel /> : null}
        {shown === "inbox" && inboxReady !== false ? <BusinessInboxPanel /> : null}
        {shown === "transactions" ? <TransaccionesPanel /> : null}
        {shown === "invoicing" && invoicingShown(invoicing) ? <InvoiceWorkspaceEntry directoryStatus={directoryStatus} onRetry={reload} scope={userId && chosen?.permissions?.includes("read") === true ? { userId, businessId: chosen.space_id, grantId: chosen.grant_id } : null} business={chosen?.name ?? ""} capabilities={{ prepare: chosen?.permissions?.includes("prepare") === true, issue: chosen?.permissions?.includes("approve") === true, download: chosen?.permissions?.includes("download") === true }} sample={invoicing === "sample"} /> : null}
        {shown === "activity" ? <ActivityDraft /> : null}
        {shown === "business" ? <BusinessSettingsPanel tab={panel.kind === "business" ? panel.tab : undefined} /> : null}
        {record && !inTray ? <RecordContent panel={record} /> : null}
      </PanelErrorBoundary>
      </div>
      {record && inTray ? <RecordTray panel={record} list={tray} listRef={listRef} returnFocusRef={returnFocusRef} /> : null}
    </div>
  );
}
