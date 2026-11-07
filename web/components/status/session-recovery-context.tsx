"use client";

import { createContext, useEffect, useSyncExternalStore } from "react";
import { WEB_APP_NAME } from "@/lib/app-brand";
import type { SessionRecovery } from "@/lib/session-recovery";

export const SessionRecoveryContext = createContext<SessionRecovery | null>(null);

export function useSessionRecoveryState(recovery: SessionRecovery, start: boolean) {
  useEffect(() => {
    if (!start) return;
    const releaseTitle = recovery.onRetire(() => { document.title = WEB_APP_NAME; });
    const stop = recovery.start();
    return () => { stop(); releaseTitle(); };
  }, [recovery, start]);
  return useSyncExternalStore(recovery.subscribe, recovery.getSnapshot, recovery.getSnapshot);
}
