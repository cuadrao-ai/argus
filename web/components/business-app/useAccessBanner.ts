"use client";

import { useCallback, useState } from "react";
import { useBusiness } from "./BusinessWorkspace";

/**
 * The one-time access line. The grant's `access_seen` flag is already the
 * server's memory of Entendido, per person and per business, so this hook
 * does not keep a second copy in the browser.
 */
export function useAccessBanner() {
  const { chosen, markAccessSeen } = useBusiness();
  const [busy, setBusy] = useState(false);
  const visible = Boolean(chosen && chosen.role !== "owner" && !chosen.access_seen);
  const dismiss = useCallback(async () => {
    setBusy(true);
    try {
      await markAccessSeen();
    } catch {
      return;
    } finally {
      setBusy(false);
    }
  }, [markAccessSeen]);
  return { visible, busy, dismiss };
}
