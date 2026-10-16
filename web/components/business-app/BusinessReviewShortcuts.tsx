"use client";

import { createContext, useContext, useLayoutEffect, useRef, type ReactNode } from "react";

export type ReviewShortcutId = "approve" | "approve_next" | "edit" | "previous" | "next";
export type ReviewShortcutActions = Partial<Record<ReviewShortcutId, () => void>>;
type Registry = { current: ReviewShortcutActions };
const ReviewShortcuts = createContext<Registry | null>(null);

export function BusinessReviewShortcutsProvider({ children }: { children: ReactNode }) {
  const actions = useRef<ReviewShortcutActions>({});
  return <ReviewShortcuts.Provider value={actions}>{children}</ReviewShortcuts.Provider>;
}

export function useRunReviewShortcut() {
  const registryRef = useContext(ReviewShortcuts);
  return (id: ReviewShortcutId): boolean => {
    const action = registryRef?.current[id];
    if (!action) return false;
    action();
    return true;
  };
}

export function ReceiptShortcutRegistration({ actions }: { actions: ReviewShortcutActions }) {
  const registryRef = useContext(ReviewShortcuts);
  useLayoutEffect(() => {
    if (!registryRef) return;
    registryRef.current = actions;
    return () => { if (registryRef.current === actions) registryRef.current = {}; };
  }, [actions, registryRef]);
  return null;
}

export function receiptNavigationActions(receiptId: string, rows: readonly { id: string; email_original?: boolean }[] | null, open: (id: string) => void): ReviewShortcutActions {
  const receipts = (rows ?? []).filter((row) => !row.email_original);
  const index = receipts.findIndex((row) => row.id === receiptId);
  if (index < 0) return {};
  const previous = receipts[index - 1];
  const next = receipts[index + 1];
  return { ...(previous ? { previous: () => open(previous.id) } : {}), ...(next ? { next: () => open(next.id) } : {}) };
}
