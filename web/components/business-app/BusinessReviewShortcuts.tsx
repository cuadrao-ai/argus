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

/** The receipt's place among the receipts a person reviews in order, or null outside that list. */
export function receiptPlace(receiptId: string, receipts: readonly string[]): { index: number; total: number } | null {
  const index = receipts.indexOf(receiptId);
  return index < 0 ? null : { index: index + 1, total: receipts.length };
}

/**
 * The receipts an open receipt is walked among: its list as the server last answered. An open receipt that left the
 * list keeps its slot, before the first row that followed it and is still listed, so previous and next start from
 * where the person is.
 */
export function followedReceipts(openId: string | null, held: readonly string[], listed: readonly string[]): readonly string[] {
  const at = openId === null ? -1 : held.indexOf(openId);
  if (openId === null || at < 0 || listed.includes(openId)) return listed;
  const follower = held.slice(at + 1).find((id) => listed.includes(id));
  const slot = follower === undefined ? listed.length : listed.indexOf(follower);
  return [...listed.slice(0, slot), openId, ...listed.slice(slot)];
}

export function receiptNavigationActions(receiptId: string, receipts: readonly string[], open: (id: string) => void): ReviewShortcutActions {
  const index = receipts.indexOf(receiptId);
  if (index < 0) return {};
  const previous = receipts[index - 1];
  const next = receipts[index + 1];
  return { ...(previous ? { previous: () => open(previous) } : {}), ...(next ? { next: () => open(next) } : {}) };
}
