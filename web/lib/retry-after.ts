export const RETRY_AFTER_FALLBACK_SECONDS = 15;
export const RETRY_AFTER_MIN_SECONDS = 1;
export const RETRY_AFTER_MAX_SECONDS = 120;

function clampRetryAfterSeconds(seconds: number): number {
  if (!Number.isFinite(seconds)) {
    return RETRY_AFTER_FALLBACK_SECONDS;
  }
  return Math.min(
    RETRY_AFTER_MAX_SECONDS,
    Math.max(RETRY_AFTER_MIN_SECONDS, Math.trunc(seconds)),
  );
}

const IMF_FIXDATE =
  /^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4} \d{2}:\d{2}:\d{2} GMT$/;
const RFC_850_DATE =
  /^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), \d{2}-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{2} \d{2}:\d{2}:\d{2} GMT$/;
const ASCTIME_DATE =
  /^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (?: \d|\d{2}) \d{2}:\d{2}:\d{2} \d{4}$/;

export function isHttpRetryAfterDate(value: string): boolean {
  return IMF_FIXDATE.test(value) || RFC_850_DATE.test(value) || ASCTIME_DATE.test(value);
}

/** Parse once; each recovery policy owns its bounds and missing-header fallback. */
export function parseRetryAfterDelaySeconds(
  value: string | null | undefined,
  nowMs: number = Date.now(),
): number | null {
  const text = value?.trim() ?? "";
  if (/^\d+$/.test(text)) {
    const seconds = Number(text);
    return Number.isFinite(seconds) ? seconds : null;
  }
  if (!isHttpRetryAfterDate(text)) {
    return null;
  }
  // HTTP dates are GMT, including obsolete asctime values without a zone.
  const parsed = Date.parse(ASCTIME_DATE.test(text) ? `${text} GMT` : text);
  return Number.isFinite(parsed) ? Math.ceil((parsed - nowMs) / 1000) : null;
}

export function parseRetryAfterSeconds(
  value: string | null | undefined,
  nowMs: number = Date.now(),
): number {
  return clampRetryAfterSeconds(
    parseRetryAfterDelaySeconds(value, nowMs) ?? RETRY_AFTER_FALLBACK_SECONDS,
  );
}

export function remainingRetryAfterSeconds(
  availableAtMs: number | undefined,
  nowMs: number,
): number {
  if (availableAtMs == null) {
    return 0;
  }
  return Math.max(0, Math.ceil((availableAtMs - nowMs) / 1000));
}

export function shouldKeepRetryAfterTicker(
  availableAtMs: number | undefined,
  nowMs: number,
): boolean {
  return remainingRetryAfterSeconds(availableAtMs, nowMs) > 0;
}
