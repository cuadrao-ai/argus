import { parseRetryAfterDelaySeconds } from "./retry-after";

export const DAILY_CAP_RECOVERY_CODE = "daily_cap_reached";

export function dailyCapResetAtMs(
  retryAfter: string | null | undefined,
  nowMs: number = Date.now(),
): number {
  const seconds = parseRetryAfterDelaySeconds(retryAfter, nowMs);
  if (seconds !== null) {
    const resetAt = Math.round((nowMs + seconds * 1000) / 60_000) * 60_000;
    if (Number.isFinite(new Date(resetAt).getTime())) return resetAt;
  }
  const now = new Date(nowMs);
  return Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1);
}

export function formatDailyCapResetTime(
  resetAtMs: number,
  language: string,
  timeZone?: string,
): string {
  return new Intl.DateTimeFormat(language, {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    ...(timeZone ? { timeZone } : {}),
  }).formatToParts(resetAtMs).map((part) => {
    // One AM/PM convention for both supported languages, independent of ICU.
    return part.type === "dayPeriod"
      ? part.value.replace(/[.\s]/g, "").toUpperCase()
      // Keep the time and day period together on narrow screens.
      : part.value.replace(/[ \u00a0\u202f]/g, "\u00a0");
  }).join("");
}
