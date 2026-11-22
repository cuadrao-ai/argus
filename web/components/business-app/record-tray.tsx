"use client";

import { createContext, useContext, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { BusinessPanelState, RecordList } from "./BusinessWorkspace";

export type RecordPanel = Extract<BusinessPanelState, { kind: "receipt" | "draft" | "expense" | "email" }>;

export function isRecordPanel(panel: BusinessPanelState): panel is RecordPanel {
  return panel.kind === "receipt" || panel.kind === "draft" || panel.kind === "expense" || panel.kind === "email";
}

/** The list a record belongs beside; null for a panel that is not a record, or a record opened without one that has not loaded yet. */
export function recordList(panel: BusinessPanelState): RecordList | null {
  if (panel.kind === "expense") return "transactions";
  if (panel.kind === "receipt" || panel.kind === "draft") return panel.list ?? null;
  if (panel.kind === "email") return "inbox";
  return null;
}

/** On a desktop a record opens in the tray over its list; below it the record is the page. */
export function recordInTray(panel: BusinessPanelState, isBelowDesktop: boolean): panel is RecordPanel {
  if (!isRecordPanel(panel)) return false;
  // The local Registros preview keeps its list beneath a phone record sheet.
  const recordsPhonePreview = process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true" && recordList(panel) === "transactions";
  return !isBelowDesktop || recordsPhonePreview;
}

/**
 * The one screen on the page, which the top bar names. Under a record in the tray it is the record's list; a
 * record opened without one (a link, Actividad) shows no list until it has loaded and said which. Otherwise it is
 * the panel itself.
 */
export function shownScreen(panel: BusinessPanelState, isBelowDesktop: boolean): BusinessPanelState["kind"] {
  return (recordInTray(panel, isBelowDesktop) ? recordList(panel) : null) ?? panel.kind;
}

/** Whether a row that opens `target` is the record open now. */
export function isOpenRecord(panel: BusinessPanelState, target: BusinessPanelState): boolean {
  if (panel.kind === "receipt") return target.kind === "receipt" && target.receiptId === panel.receiptId;
  if (panel.kind === "draft") return target.kind === "draft" && target.draftId === panel.draftId;
  if (panel.kind === "expense") return target.kind === "expense" && target.expenseId === panel.expenseId;
  if (panel.kind === "email") return target.kind === "email" && target.emailId === panel.emailId;
  return false;
}

/** The open row's highlight, the same in the Bandeja and in Transacciones. */
export const OPEN_ROW_CLASS = "aria-[current=true]:bg-[var(--cuadrao-green)]/10";

export type RecordTrayValue = Readonly<{
  /** The drawer's pinned footer; the record's actions are portalled here. */
  footer: HTMLElement | null;
  /** Under the drawer's title: a receipt's total, status and where it came from. Null for a record that keeps the drawer's own header. */
  summary: HTMLElement | null;
  /** Beside the drawer's close control: a receipt's place in its list. */
  headerActions: HTMLElement | null;
  /** A receipt names the drawer after itself; null gives the drawer back its own title. */
  setTitle: (title: string | null) => void;
  /** A record opened without a list (a link, a reload) names the list it belongs beside once it has loaded. */
  settleList: (list: RecordList) => void;
  /** The dossier's size: 640px when narrow, 1040px when not. Absent for a record that keeps the drawer's own width. */
  narrow?: boolean;
  toggleNarrow?: () => void;
}>;

export const RecordTrayContext = createContext<RecordTrayValue | null>(null);

/** Null on a full page: a phone, or any record shown outside the desktop tray. */
export function useRecordTray(): RecordTrayValue | null {
  return useContext(RecordTrayContext);
}

export function TrayFooter({ children }: { children: ReactNode }) {
  const tray = useRecordTray();
  return tray?.footer ? createPortal(children, tray.footer) : null;
}

/** Renders into one of the drawer's header slots, or nowhere while it has none. */
export function TraySlot({ slot, children }: { slot: "summary" | "headerActions"; children: ReactNode }) {
  const tray = useRecordTray();
  const target = tray?.[slot];
  return target ? createPortal(children, target) : null;
}
