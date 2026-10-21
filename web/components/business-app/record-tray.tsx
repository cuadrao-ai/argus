"use client";

import { createContext, useContext, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { BusinessPanelState, RecordList } from "./BusinessWorkspace";

/** The list a record sits beside on a desktop; null for a panel that is not a record. */
export function recordList(panel: BusinessPanelState): RecordList | null {
  if (panel.kind === "expense") return "transactions";
  if (panel.kind === "receipt" || panel.kind === "draft") return panel.list ?? "inbox";
  if (panel.kind === "email") return "inbox";
  return null;
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
  /** A record opened without a list (a link, a reload) names the list it belongs beside once it has loaded. */
  settleList: (list: RecordList) => void;
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
