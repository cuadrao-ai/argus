"use client";

import { useEffect, useState } from "react";
import { getBusinessActivity, type BusinessActivityItem } from "@/lib/business-activity-api";

type Feed = { key: string; status: "ready" | "error"; items: BusinessActivityItem[]; next: string | null; more: "idle" | "loading" | "error"; reference?: string };

/**
 * The live Actividad history: the first page per Business (and per retry), then "Cargar más" on next_cursor. A failed
 * first page keeps the server's reference for the error state; a failed next page keeps the rows already shown.
 */
export function useActivityFeed(enabled: boolean, businessId: string | null) {
  const [attempt, setAttempt] = useState(0);
  const key = `${businessId ?? "none"}:${attempt}`;
  const [feed, setFeed] = useState<Feed | null>(null);
  useEffect(() => {
    // Wait for the Business: its first page is read once, for the Business it belongs to.
    if (!enabled || !businessId) return;
    const controller = new AbortController();
    getBusinessActivity(null, controller.signal).then(
      (page) => setFeed({ key, status: "ready", items: page.items, next: page.next_cursor, more: "idle" }),
      (error: { requestId?: string }) => { if (!controller.signal.aborted) setFeed({ key, status: "error", items: [], next: null, more: "idle", reference: error?.requestId }); },
    );
    return () => controller.abort();
  }, [enabled, businessId, key]);
  const current = feed?.key === key ? feed : null;
  const loadMore = () => {
    if (!current?.next || current.more === "loading") return;
    const cursor = current.next;
    setFeed({ ...current, more: "loading" });
    getBusinessActivity(cursor).then(
      (page) => setFeed((state) => (state?.key === key ? { ...state, items: [...state.items, ...page.items], next: page.next_cursor, more: "idle" } : state)),
      () => setFeed((state) => (state?.key === key ? { ...state, more: "error" } : state)),
    );
  };
  return {
    status: current?.status ?? "loading",
    items: current?.items ?? [],
    next: current?.next ?? null,
    more: current?.more ?? "idle",
    reference: current?.reference,
    retry: () => setAttempt((value) => value + 1),
    loadMore,
  } as const;
}
