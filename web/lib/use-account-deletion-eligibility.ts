"use client";

import { useCallback, useEffect, useState } from "react";
import { getAccountDeletionEligibility, type AccountDeletionEligibility } from "@/lib/account-deletion-api";
import { previewDeletionEligibility } from "@/lib/account-deletion-preview";
import { browserAuthGeneration } from "@/lib/browser-auth-generation";
import { serverRequestReference } from "@/lib/failure-screen";

/** The server's answer on deleting this account. A refresh keeps the last answer on
 * screen until the new one lands, so a surface that already has an answer never waits. */
export type AccountDeletionCheck = {
  answer: AccountDeletionEligibility | null;
  error: { reference: string | null } | null;
  refresh: () => void;
};

export function useAccountDeletionEligibility(
  enabled: boolean,
  read?: () => Promise<AccountDeletionEligibility>,
): AccountDeletionCheck {
  // Chosen once, so a new function each render never restarts the read.
  const [reader] = useState(() => read ?? previewDeletionEligibility() ?? getAccountDeletionEligibility);
  const [answer, setAnswer] = useState<AccountDeletionEligibility | null>(null);
  const [error, setError] = useState<{ reference: string | null } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const refresh = useCallback(() => setAttempt(value => value + 1), []);

  useEffect(() => {
    if (!enabled) return;
    let active = true;
    const generation = browserAuthGeneration();
    void reader().then(next => {
      if (!active || browserAuthGeneration() !== generation) return;
      setAnswer(next);
      setError(null);
    }).catch(failure => {
      if (!active || browserAuthGeneration() !== generation) return;
      // A failed read never leaves an older yes behind it.
      setAnswer(null);
      setError({ reference: serverRequestReference(failure) });
    });
    return () => { active = false; };
  }, [enabled, reader, attempt]);

  return { answer, error, refresh };
}
