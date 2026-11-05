import type { RecoveryDisplay } from "./chat-recovery-display";
import { DAILY_CAP_RECOVERY_CODE } from "./daily-cap-reset-time";

export const DAILY_CAP_NOTICE_STORAGE_KEY = "argus:daily-cap-notice:v1";

export type DailyCapNoticeRecord = {
  accountId: string;
  resetAt: number;
  dismissed: boolean;
};

type NoticeStorage = {
  read: () => string | null;
  write: (value: string) => void;
  remove: () => void;
};

/** One tab-local observation of a server rejection, never a quota authority. */
export function createDailyCapNoticeState(storage: NoticeStorage, now = Date.now) {
  const listeners = new Set<() => void>();
  let accountId: string | undefined;
  let acceptingUpdates = true;
  let current: DailyCapNoticeRecord | null = null;
  try {
    const saved = JSON.parse(storage.read() ?? "null");
    if (saved && typeof saved.accountId === "string" && saved.accountId.trim()
      && typeof saved.resetAt === "number" && Number.isFinite(saved.resetAt)
      && Number.isFinite(new Date(saved.resetAt).getTime()) && saved.resetAt > now()
      && typeof saved.dismissed === "boolean") {
      current = { accountId: saved.accountId, resetAt: saved.resetAt, dismissed: saved.dismissed };
    } else {
      storage.remove();
    }
  } catch {
    try { storage.remove(); } catch { /* Storage can be blocked. */ }
  }

  function replace(next: DailyCapNoticeRecord | null) {
    current = next;
    try {
      if (next) storage.write(JSON.stringify(next));
      else storage.remove();
    } catch { /* Keep the notice usable in memory when storage is blocked. */ }
    listeners.forEach((listener) => listener());
  }

  function expire(owner: string | undefined) {
    if (acceptingUpdates && owner === accountId && current && current.resetAt <= now()) replace(null);
  }

  return {
    getAccount: () => accountId,
    getSnapshot: () => current,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    setAccount(nextAccountId: string | undefined) {
      acceptingUpdates = true;
      const previousAccountId = accountId;
      accountId = nextAccountId;
      // Unknown during initial /me loading must not discard a saved notice.
      if ((!nextAccountId && previousAccountId)
        || (nextAccountId && current && current.accountId !== nextAccountId)) {
        replace(null);
      }
      expire(nextAccountId);
    },
    record(owner: string | undefined, display: RecoveryDisplay | null): boolean {
      if (display?.kind !== "recovery_code" || display.code !== DAILY_CAP_RECOVERY_CODE) return false;
      if (!acceptingUpdates || !owner || owner !== accountId) return true;
      const resetAt = Date.parse(display.values?.resetAt ?? "");
      if (Number.isFinite(resetAt) && resetAt > now()) {
        replace({ accountId: owner, resetAt, dismissed: false });
      }
      return true;
    },
    dismiss(owner: string | undefined, resetAt: number) {
      if (acceptingUpdates && owner === accountId && current && current.accountId === owner && current.resetAt === resetAt) {
        replace({ ...current, dismissed: true });
      }
    },
    clear(owner: string | undefined, observed?: DailyCapNoticeRecord | null) {
      if (acceptingUpdates && owner === accountId && (observed === undefined || observed === current)) replace(null);
    },
    suspend: () => { acceptingUpdates = false; },
    expire,
  };
}
