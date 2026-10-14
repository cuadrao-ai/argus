"use client";

import { useEffect, useRef } from "react";
import type { ReceiptDetail } from "@/lib/business-api";
import type { BusinessDataSource } from "./business-data";

export const READ_POLL_MS = 5000;
/** Two minutes of asking, then the page says so and leaves the rest to a person. */
export const READ_POLL_LIMIT = 24;

/** Runs `fn` after `ms`; the returned function cancels it. Tests pass a hand-driven clock. */
export type PollClock = (fn: () => void, ms: number) => () => void;

const realClock: PollClock = (fn, ms) => {
  const timer = setTimeout(fn, ms);
  return () => clearTimeout(timer);
};

/**
 * While the server says a read is pending, ask for the receipt again every
 * few seconds and stop the moment its state leaves pending, on unmount, or
 * after READ_POLL_LIMIT asks. The page shows what the server last said; it
 * never decides on its own that the read finished. A failed ask counts as one
 * ask and the next one still happens.
 */
export function useReceiptReadPoll({
  source,
  receiptId,
  pending,
  onSettled,
  onStalled,
  clock = realClock,
}: {
  source: Pick<BusinessDataSource, "receipt">;
  receiptId: string;
  pending: boolean;
  onSettled: (next: ReceiptDetail) => void;
  onStalled: () => void;
  clock?: PollClock;
}) {
  const latest = useRef({ onSettled, onStalled });
  useEffect(() => {
    latest.current = { onSettled, onStalled };
  });
  useEffect(() => {
    if (!pending) return;
    let current = true;
    let polls = 0;
    let request: AbortController | null = null;
    let cancel = () => {};
    const visible = () => document.visibilityState !== "hidden";
    const ask = async () => {
      cancel();
      if (request || !current || !visible()) return;
      const controller = new AbortController();
      request = controller;
      let next: ReceiptDetail | null = null;
      try {
        next = await source.receipt(receiptId, controller.signal);
      } catch {
        next = null;
      } finally { if (request === controller) request = null; }
      if (!current || controller.signal.aborted || !visible()) return;
      if (next && next.read_pending !== true) {
        latest.current.onSettled(next);
        return;
      }
      if (++polls < READ_POLL_LIMIT) cancel = clock(() => void ask(), READ_POLL_MS);
      else latest.current.onStalled();
    };
    const schedule = () => {
      cancel();
      if (visible()) cancel = clock(() => void ask(), READ_POLL_MS);
    };
    const wake = () => { if (visible()) void ask(); else { cancel(); request?.abort(); } };
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
  }, [source, receiptId, pending, clock]);
}
