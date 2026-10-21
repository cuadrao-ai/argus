import { grantNotLive } from "./business-grant";
import { authLoginPathFromSearch } from "./landing-intent";
import { parseRetryAfterDelaySeconds } from "./retry-after";

export const QUIET_UNAVAILABLE_MS = 30_000;
export const EMAIL_RETRY_FALLBACK_SECONDS = 60;
export const CUADRAO_ADMIN_EMAIL = "hola@cuadrao.ai";

export type FailureClass =
  | "session_ended"
  | "closed"
  | "removed"
  | "rate_limited"
  | "offline"
  | "unavailable"
  | "server"
  | "other";

function statusOf(error: unknown): number | null {
  if (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    typeof error.status === "number"
  ) {
    return error.status;
  }
  return null;
}

export function classifyFailure(
  error: unknown,
  options?: { fetch?: boolean; online?: boolean },
): FailureClass {
  if (options?.online === false) return "offline";
  if (grantNotLive(error)) return "removed";
  if (options?.fetch && error instanceof TypeError) return "offline";
  const status = statusOf(error);
  if (status === 401) return "session_ended";
  if (status === 403) return "closed";
  if (status === 429) return "rate_limited";
  if (status === 503) return "unavailable";
  if (status !== null && status >= 500) return "server";
  return "other";
}

/**
 * Refusals where the server says, on purpose, that this Business or this part
 * of it is not available. Asking again gets the same answer. Each one is its
 * status and its code together: any other 503, business_bank_unavailable
 * among them, is an outage that can pass.
 */
const REFUSED_FOR_GOOD: readonly (readonly [number, string])[] = [
  [404, "business_unavailable"],
  [503, "email_capture_unavailable"],
];

/** True when the server refused on purpose; a client that wraps the API error keeps it as its cause. */
export function refusedForGood(error: unknown): boolean {
  for (const candidate of [error, typeof error === "object" && error !== null ? (error as { cause?: unknown }).cause : undefined]) {
    if (typeof candidate !== "object" || candidate === null) continue;
    const { status, code } = candidate as { status?: unknown; code?: unknown };
    if (REFUSED_FOR_GOOD.some(([refusedStatus, refusedCode]) => status === refusedStatus && code === refusedCode)) return true;
  }
  return false;
}

/**
 * What a failed read can offer. Offline is the connection banner's to say;
 * a refusal for good offers no Reintentar and never blames the connection;
 * anything else can pass, so Reintentar stays.
 */
export type LoadRecovery = "offline" | "refused" | "retry";

export function loadRecovery(error: unknown, online = typeof navigator === "undefined" || navigator.onLine !== false): LoadRecovery {
  if (!online) return "offline";
  return refusedForGood(error) ? "refused" : "retry";
}

const REFERENCE = /^[A-Za-z0-9_-]{4,64}$/;

export function referenceCode(error: unknown): string {
  for (const key of ["requestId", "digest"] as const) {
    const value = typeof error === "object" && error !== null && key in error ? (error as Record<string, unknown>)[key] : undefined;
    if (typeof value === "string" && REFERENCE.test(value)) return value;
  }
  const bytes = new Uint8Array(4);
  crypto.getRandomValues(bytes);
  return `c${Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

/** How many characters of a reference a person reads; the full id stays for copy and support. */
export const SHORT_REFERENCE_LENGTH = 8;

export function shortReference(reference: string): string {
  return reference.slice(0, SHORT_REFERENCE_LENGTH);
}

export function emailRetrySeconds(header: string | null, nowMs = Date.now()): number {
  const parsed = parseRetryAfterDelaySeconds(header, nowMs);
  if (parsed === null || parsed < 1) return EMAIL_RETRY_FALLBACK_SECONDS;
  return Math.min(120, Math.trunc(parsed));
}

export function sessionEndedLoginPath(pathname: string, search: string): string {
  const login = authLoginPathFromSearch(search, pathname);
  const params = new URLSearchParams(login.slice(login.indexOf("?") + 1));
  params.set("notice", "session_ended");
  return `/?${params.toString()}`;
}

export function sessionEndedNotice(search: string): boolean {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  return params.get("notice") === "session_ended";
}

export type QuietClock = {
  now: () => number;
  sleep: (ms: number) => Promise<void>;
};

const realClock: QuietClock = {
  now: () => Date.now(),
  sleep: (ms) => new Promise((resolve) => {
    setTimeout(resolve, ms);
  }),
};

export function nextQuietRetryMs(startedAtMs: number, nowMs: number, gapMs = 2_000): number | null {
  const left = QUIET_UNAVAILABLE_MS - (nowMs - startedAtMs);
  if (left <= 0) return null;
  return Math.min(gapMs, left);
}

export async function runQuietRetries<T>(
  attempt: () => Promise<T>,
  clock: QuietClock = realClock,
): Promise<T> {
  const started = clock.now();
  for (;;) {
    try {
      return await attempt();
    } catch (error) {
      if (classifyFailure(error) !== "unavailable") throw error;
      const wait = nextQuietRetryMs(started, clock.now());
      if (wait === null) throw error;
      await clock.sleep(wait);
    }
  }
}
