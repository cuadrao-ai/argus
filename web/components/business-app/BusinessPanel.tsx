"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
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
import { RecordsAnnotationsPreview } from "./transacciones/RecordsAnnotationsPreview";
import { RecordEvidenceContext, RecordGlanceContext, RecordReadinessContext, RecordRowsContext, type RefreshRecordRow } from "./transacciones/RecordGlanceContext";
import { previewRecordMetadata } from "./transacciones/records-results-preview";
import type { RecordRow } from "./transacciones/transacciones-model";
import ExpenseDetailPanel from "./ExpenseDetailPanel";
import BusinessSettingsPanel from "./BusinessSettingsPanel";
import ReceiptReviewPanel from "./ReceiptReviewPanel";
import { EmailRecord } from "./BusinessEmailDeliveries";
import PanelErrorBoundary from "./PanelErrorBoundary";
import { formatBusinessName } from "./business-format";
import { RecordTrayContext, recordList } from "./record-tray";
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

type RecordPanel = Extract<BusinessPanelState, { kind: "receipt" | "draft" | "expense" | "email" }>;

function recordKey(panel: RecordPanel): string {
  switch (panel.kind) {
    case "receipt": return `receipt:${panel.receiptId}`;
    case "draft": return `draft:${panel.draftId}`;
    case "expense": return `expense:${panel.expenseId}`;
    case "email": return `email:${panel.emailId}`;
  }
}

function rowTarget(row: RecordRow): string | null {
  return row.opens ? recordKey(row.opens) : null;
}

function RecordContent({ panel, preview }: { panel: RecordPanel; preview?: RecordRow }) {
  if (panel.kind === "expense") return <ExpenseDetailPanel key={panel.expenseId} expenseId={panel.expenseId} preview={preview} />;
  if (panel.kind === "email") return <EmailRecord key={panel.emailId} emailId={panel.emailId} />;
  if (panel.kind === "receipt") return <ReceiptReviewPanel key={panel.receiptId} target={{ kind: "receipt", id: panel.receiptId }} />;
  return <ReceiptReviewPanel key={panel.draftId} target={{ kind: "draft", id: panel.draftId }} />;
}

/**
 * A record on a desktop: beside Registros, which it came from, or in the wide dossier over the
 * Bandeja. The tray is not modal: a click on another row swaps the record. AdaptivePanel closes it
 * and puts focus back on the row that was open; the workspace's panel guard asks first while the
 * record holds an unsaved edit.
 */
function RecordTray({ panel, list, listRef, returnFocusRef, preview }: { panel: RecordPanel; list: RecordList; listRef: RefObject<HTMLDivElement | null>; returnFocusRef: RefObject<HTMLElement | null>; preview?: RecordRow }) {
  const { t } = useTranslation();
  const { openPanel } = useBusiness();
  const [footer, setFooter] = useState<HTMLDivElement | null>(null);
  const [summary, setSummary] = useState<HTMLDivElement | null>(null);
  const [headerActions, setHeaderActions] = useState<HTMLDivElement | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  // A receipt's dossier makes the drawer's header its own: its name, total, status, origin and place in the list.
  const receiptHeader = panel.kind === "receipt" || panel.kind === "draft";
  const settleList = useCallback((next: RecordList) => {
    if ((panel.kind === "receipt" || panel.kind === "draft") && panel.list === undefined && next !== list) openPanel({ ...panel, list: next });
  }, [list, openPanel, panel]);
  const tray = useMemo(() => ({ footer, summary: receiptHeader ? summary : null, headerActions: receiptHeader ? headerActions : null, setTitle, settleList }), [footer, summary, headerActions, receiptHeader, settleList]);
  const close = () => {
    const host = listRef.current;
    returnFocusRef.current = host?.querySelector<HTMLElement>('[aria-current="true"] button, tr[aria-selected="true"]') ?? host;
    openPanel({ kind: list });
  };
  return (
    <AdaptivePanel
      modal={false}
      width={list === "inbox" ? "dossier" : "record"}
      title={(receiptHeader ? title : null) ?? t("business.tray.title", "Details")}
      titleId={receiptHeader ? "receipt-review-title" : undefined}
      headerSize={receiptHeader ? "large" : "default"}
      summary={receiptHeader ? <div ref={setSummary} data-header-slot="" /> : undefined}
      headerActions={receiptHeader ? <div ref={setHeaderActions} data-header-actions="" className="flex items-center empty:hidden" /> : undefined}
      closeLabel={t("common.close", "Close")}
      onClose={close}
      returnFocusRef={returnFocusRef}
      footer={<div ref={setFooter} data-footer-slot="" />}
    >
      <RecordTrayContext.Provider value={tray}>
        <div className="px-5 py-5">
          <PanelErrorBoundary key={recordKey(panel)}>
            <RecordContent panel={panel} preview={preview} />
          </PanelErrorBoundary>
        </div>
      </RecordTrayContext.Provider>
    </AdaptivePanel>
  );
}

/** Inside the one canvas every screen starts at its left edge; a list or a form keeps a narrower column there. */
const COLUMN = { canvas: "", reading: "max-w-3xl", form: "max-w-[40rem]" } as const;
const SCREEN_COLUMN: Partial<Record<BusinessPanelState["kind"], keyof typeof COLUMN>> = { overview: "canvas", inbox: "canvas", transactions: "canvas", invoicing: "canvas", activity: "canvas", receipt: "canvas", draft: "canvas", business: "canvas", expense: "form" };

export default function BusinessPanel() {
  const { panel, lostAccess, records, reload, openPanel, chosen, userId, directoryStatus, invoicing, revision } = useBusiness();
  const previewEnabled = process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
  const scope = JSON.stringify([userId, chosen?.space_id ?? "own", chosen?.grant_id ?? null]);
  const [glance, setGlance] = useState<{ scope: string; row: RecordRow; revision: number; refresh?: RefreshRecordRow } | null>(null);
  const openGlance = (row: RecordRow, refresh?: RefreshRecordRow) => { if (!row.opens) return; setGlance({ scope, row, revision, refresh }); openPanel(row.opens); };
  const refreshSelectedRow = useCallback((rows: readonly RecordRow[]) => {
    setGlance((selected) => {
      if (!selected || selected.scope !== scope) return selected;
      const next = rows.find((row) => rowTarget(row) === rowTarget(selected.row));
      if (!next) return null;
      return next.report === selected.row.report ? selected : { ...selected, row: next };
    });
  }, [scope]);
  const { isBelowDesktop } = useResponsiveLayout();
  // A phone unmounts Registros while the record is open. Ask the same report for its new answer after a save.
  useEffect(() => {
    if (!isBelowDesktop || previewEnabled || !glance?.refresh || glance.scope !== scope || glance.revision === revision) return;
    const selected = glance;
    const abort = new AbortController();
    void glance.refresh(abort.signal).then((row) => {
      if (!abort.signal.aborted) setGlance((current) => current === selected ? row ? { ...selected, row, revision } : null : current);
    }, () => {
      if (!abort.signal.aborted) setGlance((current) => current === selected ? null : current);
    });
    return () => abort.abort();
  }, [glance, isBelowDesktop, previewEnabled, revision, scope]);
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
  if (lostAccess) {
    return (
      <div className={`w-full pb-6 ${COLUMN.reading}`}>
        <BusinessContextCue />
      </div>
    );
  }
  const record = panel.kind === "receipt" || panel.kind === "draft" || panel.kind === "expense" || panel.kind === "email" ? panel : null;
  // The local Registros preview keeps its list beneath a phone record sheet.
  const recordsPhonePreview = process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true" && record && recordList(record) === "transactions";
  const tray = record && (!isBelowDesktop || recordsPhonePreview) ? recordList(record) : null;
  const shown = tray ?? panel.kind;
  const preview = previewEnabled && !glance?.row.report && record?.kind === "expense" && glance?.scope === scope && glance.row.opens?.kind === "expense" && glance.row.opens.expenseId === record.expenseId ? glance.row : undefined;
  const selectedRow = record && glance?.scope === scope && rowTarget(glance.row) === recordKey(record) ? glance.row : null;
  const readiness = selectedRow ? selectedRow.report ?? (previewEnabled ? previewRecordMetadata(selectedRow, chosen?.space_id ?? null) : null) : null;
  // Negocio bounds its own columns through SettingsLayout, so every tab shares one left edge and width.
  const column = SCREEN_COLUMN[shown] ?? "reading";
  return (
    <RecordGlanceContext.Provider value={openGlance}>
      <RecordRowsContext.Provider value={refreshSelectedRow}>
      <RecordReadinessContext.Provider value={readiness}>
      <RecordEvidenceContext.Provider value={(row) => { if (row.opens) { setGlance(null); openPanel(row.opens); } }}>
        <RecordsAnnotationsPreview><div ref={listRef} tabIndex={-1} data-column={column} className={`w-full ${record && !tray ? "pb-0" : "pb-6"} outline-none ${COLUMN[column]}`}>
      <BusinessContextCue />
      {/* A dossier tray lies over the list, so what it covers leaves the Tab order and the accessibility tree. */}
      <div inert={tray === "inbox" ? true : undefined}>
      {/* Keyed by what the page shows, so opening a record beside the list keeps the list mounted. */}
      <PanelErrorBoundary key={tray ?? (record ? recordKey(record) : panel.kind)}>
        {shown === "overview" ? <BusinessOverviewPanel /> : null}
        {shown === "inbox" ? <BusinessInboxPanel /> : null}
        {shown === "transactions" ? <TransaccionesPanel /> : null}
        {shown === "invoicing" && invoicingShown(invoicing) ? <InvoiceWorkspaceEntry directoryStatus={directoryStatus} onRetry={reload} scope={userId && chosen?.permissions?.includes("read") === true ? { userId, businessId: chosen.space_id, grantId: chosen.grant_id } : null} business={chosen?.name ?? ""} capabilities={{ prepare: chosen?.permissions?.includes("prepare") === true, issue: chosen?.permissions?.includes("approve") === true, download: chosen?.permissions?.includes("download") === true }} sample={invoicing === "sample"} /> : null}
        {shown === "activity" ? <ActivityDraft /> : null}
        {shown === "business" ? <BusinessSettingsPanel tab={panel.kind === "business" ? panel.tab : undefined} /> : null}
        {record && !tray ? <RecordContent panel={record} /> : null}
      </PanelErrorBoundary>
      </div>
      {record && tray ? <RecordTray panel={record} list={tray} listRef={listRef} returnFocusRef={returnFocusRef} preview={preview} /> : null}
        </div></RecordsAnnotationsPreview>
      </RecordEvidenceContext.Provider>
      </RecordReadinessContext.Provider>
      </RecordRowsContext.Provider>
    </RecordGlanceContext.Provider>
  );
}
