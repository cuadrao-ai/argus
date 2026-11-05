"use client";

import { useCallback, useEffect, useLayoutEffect, useState, useSyncExternalStore } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { readSessionStored, removeSessionStored, writeSessionStored } from "@/lib/browser-storage";
import { createDailyCapNoticeState, DAILY_CAP_NOTICE_STORAGE_KEY } from "@/lib/daily-cap-notice-state";
import { DAILY_CAP_RECOVERY_CODE } from "@/lib/daily-cap-reset-time";
import { recoveryDisplayText, type RecoveryDisplay } from "@/lib/chat-recovery-display";
import FailureNotice from "./FailureNotice";

const serverSnapshot = () => null;

export function useDailyCapNotice(accountId: string | undefined) {
  const { t, i18n } = useTranslation();
  const [state] = useState(() => createDailyCapNoticeState({
    read: () => readSessionStored(DAILY_CAP_NOTICE_STORAGE_KEY),
    write: (value) => { writeSessionStored(DAILY_CAP_NOTICE_STORAGE_KEY, value); },
    remove: () => removeSessionStored(DAILY_CAP_NOTICE_STORAGE_KEY),
  }));
  const snapshot = useSyncExternalStore(state.subscribe, state.getSnapshot, serverSnapshot);
  const current = accountId && snapshot?.accountId === accountId ? snapshot : null;
  const active = Boolean(current && !current.dismissed);
  const [element, setElement] = useState<HTMLDivElement | null>(null);
  const [height, setHeight] = useState(0);

  useLayoutEffect(() => {
    state.setAccount(accountId);
    return () => state.suspend();
  }, [accountId, state]);

  useLayoutEffect(() => {
    if (!element) { setHeight(0); return; }
    const measure = () => setHeight(element.getBoundingClientRect().height);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const recheck = () => {
      clearTimeout(timer);
      state.expire(accountId);
      const saved = state.getSnapshot();
      if (accountId && saved?.accountId === accountId) {
        timer = setTimeout(recheck, Math.min(Math.max(saved.resetAt - Date.now(), 1), 2_147_483_647));
      }
    };
    recheck();
    window.addEventListener("focus", recheck);
    document.addEventListener("visibilitychange", recheck);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("focus", recheck);
      document.removeEventListener("visibilitychange", recheck);
    };
  }, [accountId, state, snapshot?.resetAt]);

  // Callers authorize the request immediately before dispatch. Read the current
  // scope here because guest bootstrap can establish it during an awaited send.
  const record = useCallback((display: RecoveryDisplay | null) => state.record(state.getAccount(), display), [state]);
  const clear = useCallback(() => state.clear(state.getAccount()), [state]);
  const captureSuccessClear = useCallback(() => {
    const observed = state.getSnapshot();
    return () => state.clear(state.getAccount(), observed);
  }, [state]);
  const notice = active && current ? (
    <div ref={setElement} className="pb-3">
      <FailureNotice testId="daily-cap-notice">
        <div className="flex items-start gap-2">
          <span className="min-w-0 flex-1">
            {recoveryDisplayText({
              kind: "recovery_code", code: DAILY_CAP_RECOVERY_CODE,
              values: { resetAt: new Date(current.resetAt).toISOString() },
            }, t, i18n.resolvedLanguage ?? i18n.language)}
          </span>
          <button
            type="button" aria-label={t("common.close")} title={t("common.close")}
            onClick={() => state.dismiss(accountId, current.resetAt)}
            className="-me-1 -mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-black/50 transition-colors hover:bg-black/5 hover:text-black/75 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/25 dark:text-white/55 dark:hover:bg-white/10 dark:hover:text-white/80 dark:focus-visible:ring-white/30"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </FailureNotice>
    </div>
  ) : null;

  return { notice, active, height: active ? height : 0, record, clear, captureSuccessClear };
}
