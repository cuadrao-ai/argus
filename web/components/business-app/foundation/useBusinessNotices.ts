"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getBusinessNotices, markBusinessNoticesRead, type BusinessNotice } from "@/lib/business-notifications";

export type NoticesLoad = "loading" | "ready" | "failed";
export type BusinessNotices = {
  load: NoticesLoad;
  items: readonly BusinessNotice[];
  /** Goes up each time a later answer brings an unread notice the earlier ones did not hold. */
  arrivals: number;
  refresh: () => void;
  retry: () => void;
  markRead: (ids: readonly string[]) => void;
  remove: (id: string) => void;
};

/**
 * The person's notices as the server lists them. It asks once when the bell
 * mounts, when the tab comes back on screen and when the bell opens: no timer.
 * The list never follows the chosen Business.
 */
export function useBusinessNotices(enabled: boolean): BusinessNotices {
  const [state, setState] = useState<{ load: NoticesLoad; items: readonly BusinessNotice[] }>({ load: "loading", items: [] });
  const [arrivals, setArrivals] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const known = useRef<ReadonlySet<string> | null>(null);
  // Readings sent to the server: an answer that left before one of them landed must not turn it unread again.
  const sent = useRef(new Set<string>());
  // Rows taken out here. An answer or failure that left before the latest one is stale: it is dropped and the list asked again.
  const removals = useRef(0);
  const refresh = useCallback(() => setAttempt((value) => value + 1), []);
  useEffect(() => {
    if (!enabled) return undefined;
    const controller = new AbortController();
    const leftAt = removals.current;
    const stale = () => {
      if (controller.signal.aborted) return true;
      if (leftAt === removals.current) return false;
      refresh();
      return true;
    };
    getBusinessNotices(controller.signal).then((items) => {
      if (stale()) return;
      const before = known.current;
      if (before && items.some((item) => item.unread && !before.has(item.id))) setArrivals((value) => value + 1);
      known.current = new Set(items.map((item) => item.id));
      setState({ load: "ready", items: items.map((item) => (sent.current.has(item.id) ? { ...item, unread: false } : item)) });
    }, () => {
      if (!stale()) setState({ load: "failed", items: [] });
    });
    return () => controller.abort();
  }, [enabled, attempt, refresh]);
  useEffect(() => {
    if (!enabled) return undefined;
    const back = () => { if (document.visibilityState === "visible") refresh(); };
    document.addEventListener("visibilitychange", back);
    return () => document.removeEventListener("visibilitychange", back);
  }, [enabled, refresh]);
  const retry = useCallback(() => {
    setState({ load: "loading", items: [] });
    refresh();
  }, [refresh]);
  const markRead = useCallback((ids: readonly string[]) => {
    setState((current) => ({ ...current, items: current.items.map((item) => (ids.includes(item.id) ? { ...item, unread: false } : item)) }));
    ids.forEach((id) => sent.current.add(id));
    // The server owns what was read: if this does not reach it, its next answer lists them unread again.
    markBusinessNoticesRead(ids).catch(() => ids.forEach((id) => sent.current.delete(id)));
  }, []);
  const remove = useCallback((id: string) => {
    removals.current += 1;
    setState((current) => ({ ...current, items: current.items.filter((item) => item.id !== id) }));
  }, []);
  return { ...state, arrivals, refresh, retry, markRead, remove };
}
