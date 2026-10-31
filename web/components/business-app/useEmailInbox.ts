"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { BusinessEmailInboxGroup } from "@/lib/business-email";
import type { BusinessDataSource } from "./business-data";
import { loadFailure, type LoadFailure } from "./bandeja-sources";

export type EmailInbox = Readonly<{
  /** Null until this Business has answered. An empty list is an answer with nothing in it. */
  groups: BusinessEmailInboxGroup[] | null;
  failure: LoadFailure | null;
  /** Asks again and settles when that ask finishes, including a failure. */
  refresh: () => Promise<void>;
}>;

type Loaded = { key: string | null; groups: BusinessEmailInboxGroup[] | null; failure: LoadFailure | null };

/**
 * The inbox groups, apart from receipts, notes and the deliveries list.
 * A failure here leaves those lists as they were.
 */
export function useEmailInbox({ source, enabled, revision, businessKey }: { source: BusinessDataSource; enabled: boolean; revision: number; businessKey: string | null }): EmailInbox {
  const [loaded, setLoaded] = useState<Loaded>({ key: businessKey, groups: null, failure: null });
  const [attempt, setAttempt] = useState(0);
  const waiters = useRef<Array<() => void>>([]);
  const refresh = useCallback(() => new Promise<void>((resolve) => {
    waiters.current.push(resolve);
    setAttempt((value) => value + 1);
  }), []);
  useEffect(() => {
    const finish = () => {
      const pending = waiters.current.splice(0);
      pending.forEach((resolve) => resolve());
    };
    if (!enabled) {
      finish();
      return undefined;
    }
    let current = true;
    const settle = () => { if (current) finish(); };
    if (!source.emailInbox) {
      setLoaded({ key: businessKey, groups: [], failure: null });
      settle();
      return () => { current = false; };
    }
    const load = source.emailInbox;
    void (async () => {
      try {
        const groups = await load();
        if (!current) return;
        setLoaded({ key: businessKey, groups, failure: null });
      } catch (error) {
        if (!current) return;
        setLoaded((value) => ({ key: businessKey, groups: value.key === businessKey ? value.groups : null, failure: loadFailure(error) }));
      } finally {
        settle();
      }
    })();
    return () => { current = false; };
  }, [source, enabled, revision, businessKey, attempt]);
  const mine = loaded.key === businessKey;
  return { groups: mine ? loaded.groups : null, failure: mine ? loaded.failure : null, refresh };
}
