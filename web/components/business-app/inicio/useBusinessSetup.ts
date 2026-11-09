"use client";

import { useCallback, useEffect, useState } from "react";
import type { BusinessSetupStep } from "@/lib/business-setup-api";
import { useBusiness } from "../BusinessWorkspace";
import { canManageBusiness } from "../business-ui";

type Loaded = { business: string; steps: readonly BusinessSetupStep[] | null };

/**
 * The selected Business's setup steps as the server answered them, or null while unknown, unreadable, or for
 * someone who may not configure this Business. Null shows no guide: progress is never guessed. A reload, or
 * `refresh` once a step's own form closes, asks again and keeps the last answer for the same Business until the
 * new one lands.
 */
export function useBusinessSetup(): { steps: readonly BusinessSetupStep[] | null; refresh: () => void } {
  const { source, chosen, revision } = useBusiness();
  const allowed = canManageBusiness(chosen, source.mode === "live");
  const business = `${chosen?.space_id ?? "none"}:${chosen?.grant_id ?? "own"}`;
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [asked, setAsked] = useState(0);
  useEffect(() => {
    if (!allowed || !source.setup) return;
    const controller = new AbortController();
    source.setup(controller.signal).then(
      (setup) => { if (!controller.signal.aborted) setLoaded({ business, steps: setup.steps }); },
      () => { if (!controller.signal.aborted) setLoaded({ business, steps: null }); },
    );
    return () => controller.abort();
  }, [allowed, source, business, revision, asked]);
  const refresh = useCallback(() => setAsked((count) => count + 1), []);
  return { steps: allowed && loaded?.business === business ? loaded.steps : null, refresh };
}

/** Setup is open while a required step is not done. */
export const setupOpen = (steps: readonly BusinessSetupStep[] | null): steps is readonly BusinessSetupStep[] =>
  steps !== null && steps.some((step) => step.required && !step.done);
