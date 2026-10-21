"use client";

import { useCallback, useEffect, useState } from "react";
import { emailDeliveriesNeedRefresh, type BusinessEmailDelivery } from "@/lib/business-email";
import type { BusinessDataSource } from "./business-data";

const POLL_MS = 5000;
const POLLS = 6;

export type EmailDeliveries = Readonly<{
  /** Newest first as the server lists them; null until the first answer for this business. */
  items: BusinessEmailDelivery[] | null;
  failed: boolean;
  refreshing: boolean;
  /** Emails were still moving after the short poll; a refresh asks again. */
  stalled: boolean;
  refresh: () => void;
}>;

type Loaded = { key: string | null; items: BusinessEmailDelivery[] | null; failed: boolean };

/**
 * The received emails, loaded with the workspace's records so the Bandeja
 * rows, every count and the Negocio history read one list. While an email is
 * still moving it polls a few times, then waits for a refresh.
 */
export function useEmailDeliveries({ source, enabled, revision, businessKey }: { source: BusinessDataSource; enabled: boolean; revision: number; businessKey: string | null }): EmailDeliveries {
  const [loaded, setLoaded] = useState<Loaded>({ key: businessKey, items: null, failed: false });
  const [attempt, setAttempt] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [stalled, setStalled] = useState(false);
  useEffect(() => {
    if (!enabled) return undefined;
    let current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let polls = 0;
    setStalled(false);
    setRefreshing(true);
    const load = async () => {
      try {
        const items = await source.emailDeliveries();
        if (!current) return;
        setLoaded({ key: businessKey, items, failed: false });
        if (!emailDeliveriesNeedRefresh(items)) return;
        if (polls++ < POLLS) timer = setTimeout(() => void load(), POLL_MS);
        else setStalled(true);
      } catch {
        if (current) setLoaded((value) => ({ key: businessKey, items: value.key === businessKey ? value.items : null, failed: true }));
      } finally {
        if (current) setRefreshing(false);
      }
    };
    void load();
    return () => { current = false; clearTimeout(timer); };
  }, [source, enabled, revision, businessKey, attempt]);
  const refresh = useCallback(() => setAttempt((value) => value + 1), []);
  const mine = loaded.key === businessKey;
  return { items: mine ? loaded.items : null, failed: mine && loaded.failed, refreshing, stalled, refresh };
}
