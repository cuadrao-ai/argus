"use client";

import { useEffect, useRef } from "react";
import type { ReceiptActivityCounts, ReceiptSummary } from "@/lib/business-api";
import type { PollClock } from "./receipt-read-poll";
import type { BusinessDataSource } from "./business-data";

export const RECEIPT_DISCOVERY_MS = 15000;
export const RECEIPT_READING_MS = 5000;
const MAX_REFRESH_DELAY_MS = 60000;
const realClock: PollClock = (fn, ms) => { const timer = setTimeout(fn, ms); return () => clearTimeout(timer); };
type Page = { items: ReceiptSummary[]; activity: ReceiptActivityCounts | null };

export function useReceiptInboxRefresh({ source, active, reading, businessKey, onRefresh, clock = realClock }: {
  source: BusinessDataSource; active: boolean; reading: boolean; businessKey: string | null;
  onRefresh: (page: Page) => void; clock?: PollClock;
}) {
  const latest = useRef(onRefresh);
  const failures = useRef(0);
  useEffect(() => { latest.current = onRefresh; });
  useEffect(() => { failures.current = 0; }, [businessKey]);
  useEffect(() => {
    if (source.mode !== "live") return;
    let current = true;
    let cancel = () => {};
    let request: AbortController | null = null;
    const eligible = active || reading;
    const visible = () => document.visibilityState !== "hidden";
    const schedule = () => {
      cancel();
      const interval = reading ? RECEIPT_READING_MS : RECEIPT_DISCOVERY_MS;
      if (current && visible() && eligible) cancel = clock(() => void refresh(), Math.min(interval * 2 ** failures.current, MAX_REFRESH_DELAY_MS));
    };
    const refresh = async () => {
      if (!current || !visible() || request) return;
      const controller = new AbortController();
      request = controller;
      try {
        const page = source.receiptPage ? await source.receiptPage("inbox", controller.signal) : { items: await source.receipts("inbox"), activity: null };
        if (current && !controller.signal.aborted) {
          failures.current = 0;
          latest.current(page);
        }
      } catch {
        // Keep the last server projection; cancellation is not a failed refresh.
        if (current && !controller.signal.aborted) failures.current++;
      }
      finally { if (request === controller) request = null; schedule(); }
    };
    const wake = () => {
      cancel();
      if (!visible()) { request?.abort(); return; }
      if (eligible) void refresh();
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
