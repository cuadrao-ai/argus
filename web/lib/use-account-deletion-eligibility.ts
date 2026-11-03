"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getAccountDeletionEligibility, type AccountDeletionEligibility } from "@/lib/account-deletion-api";
import { previewDeletionEligibility } from "@/lib/account-deletion-preview";
import { browserAuthGeneration } from "@/lib/browser-auth-generation";
import { serverRequestReference } from "@/lib/failure-screen";

/** How long an answer is reused before it is read again. The server checks again on delete. */
export const DELETION_ANSWER_FRESH_MS = 60_000;

/** The server's answer on deleting this account. A refresh keeps the last answer on
 * screen until the new one lands, so a surface that already has an answer never waits. */
export type AccountDeletionCheck = {
  answer: AccountDeletionEligibility | null;
  error: { reference: string | null } | null;
  /** Reads again now, as Reintentar does. */
  refresh: () => void;
};

export function useAccountDeletionEligibility(
  enabled: boolean,
  read?: () => Promise<AccountDeletionEligibility>,
): AccountDeletionCheck & { refreshIfStale: () => void } {
  // Chosen once, so a new function each render never restarts the read.
  const [reader] = useState(() => read ?? previewDeletionEligibility() ?? getAccountDeletionEligibility);
  const [answer, setAnswer] = useState<AccountDeletionEligibility | null>(null);
  const [error, setError] = useState<{ reference: string | null } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const answeredAt = useRef<number | null>(null);
  const lastAttempt = useRef(attempt);
  const refresh = useCallback(() => setAttempt(value => value + 1), []);
  const isFresh = () => answeredAt.current !== null && Date.now() - answeredAt.current < DELETION_ANSWER_FRESH_MS;
  const refreshIfStale = useCallback(() => {
    if (!isFresh()) setAttempt(value => value + 1);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    // Becoming enabled reuses an answer under a minute old; an asked-for refresh always reads.
    const asked = attempt !== lastAttempt.current;
    lastAttempt.current = attempt;
    if (!asked && isFresh()) return;
    let active = true;
    const generation = browserAuthGeneration();
    void reader().then(next => {
      if (!active || browserAuthGeneration() !== generation) return;
      answeredAt.current = Date.now();
      setAnswer(next);
      setError(null);
    }).catch(failure => {
      if (!active || browserAuthGeneration() !== generation) return;
      // A failed read never leaves an older yes behind it.
      answeredAt.current = null;
      setAnswer(null);
      setError({ reference: serverRequestReference(failure) });
    });
    return () => { active = false; };
  }, [enabled, reader, attempt]);

  return { answer, error, refresh, refreshIfStale };
}
