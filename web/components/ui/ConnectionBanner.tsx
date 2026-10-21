"use client";

import { useSyncExternalStore } from "react";
import { WifiOff } from "lucide-react";
import { useTranslation } from "react-i18next";

/** The space a docked banner takes at the top of the app; the bar and the page move down by it. */
export const BANNER_HEIGHT_PX = 40;

function subscribe(listener: () => void) {
  window.addEventListener("online", listener);
  window.addEventListener("offline", listener);
  return () => {
    window.removeEventListener("online", listener);
    window.removeEventListener("offline", listener);
  };
}

/** The browser's own word on the connection; the server render assumes online. */
export function useOnline(): boolean {
  return useSyncExternalStore(subscribe, () => navigator.onLine, () => true);
}

/**
 * A condition of the whole app, so it docks at the top and stays until the
 * connection is back. It never shows as a toast and never sits mid-page.
 */
export function ConnectionBanner() {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="connection-banner"
      style={{ height: BANNER_HEIGHT_PX }}
      className="absolute inset-x-0 top-0 z-[55] flex items-center justify-center gap-2 bg-[#172b26] px-4 text-[13px] font-medium text-[#FFFEFA] dark:bg-[#2f5a49]"
    >
      <WifiOff className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span className="truncate">{t("common.offline_banner", "You're offline. Nothing you do now is saved until the connection is back.")}</span>
    </div>
  );
}
