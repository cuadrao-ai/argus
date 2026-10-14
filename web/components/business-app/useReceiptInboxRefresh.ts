"use client";

import { useEffect, useRef } from "react";
import type { ReceiptActivityCounts, ReceiptSummary } from "@/lib/business-api";
import type { PollClock } from "./receipt-read-poll";
import type { BusinessDataSource } from "./business-data";

export const RECEIPT_DISCOVERY_MS = 15000;
export const RECEIPT_READING_MS = 5000;
const realClock: PollClock = (fn, ms) => { const timer = setTimeout(fn, ms); return () => clearTimeout(timer); };
type Page = { items: ReceiptSummary[]; activity: ReceiptActivityCounts | null };

export function useReceiptInboxRefresh({ source, active, reading, businessKey, onRefresh, clock = realClock }: {
  source: BusinessDataSource; active: boolean; reading: boolean; businessKey: string | null;
  onRefresh: (page: Page) => void; clock?: PollClock;
}) {
  const latest = useRef(onRefresh);
  useEffect(() => { latest.current = onRefresh; });
  useEffect(() => {
    if (source.mode !== "live") return;
    let current = true;
    let cancel = () => {};
    let request: AbortController | null = null;
    const visible = () => document.visibilityState !== "hidden";
    const schedule = () => {
      cancel();
      if (current && visible() && (active || reading)) cancel = clock(() => void refresh(), reading ? RECEIPT_READING_MS : RECEIPT_DISCOVERY_MS);
    };
    const refresh = async () => {
      if (!current || !visible() || request) return;
      const controller = new AbortController();
      request = controller;
      try {
        const page = source.receiptPage ? await source.receiptPage("inbox", controller.signal) : { items: await source.receipts("inbox"), activity: null };
        if (current && !controller.signal.aborted) latest.current(page);
      } catch { /* Keep the last server projection until the next refresh. */ }
      finally { if (request === controller) request = null; schedule(); }
    };
    const wake = () => {
      cancel();
      if (!visible()) { request?.abort(); return; }
      void refresh();
    };
    window.addEventListener("focus", wake);
    document.addEventListener("visibilitychange", wake);
    schedule();
    return () => {
      current = false;
      cancel();
      request?.abort();
      window.removeEventListener("focus", wake);
      document.removeEventListener("visibilitychange", wake);
    };
  }, [source, active, reading, businessKey, clock]);
}
