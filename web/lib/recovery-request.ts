import { isIP } from "node:net";

const LOCAL_RECOVERY_ORIGINS = new Set([
  "http://localhost:3000",
  "http://127.0.0.1:3000",
  "http://localhost:3001",
  "http://127.0.0.1:3001",
]);
const MAX_TRACKED_RECOVERY_KEYS = 2_048;
const MAX_RECOVERY_BODY_BYTES = 8_192;
const MAX_RECOVERY_EMAIL_LENGTH = 254;
const MAX_CLIENT_ADDRESS_LENGTH = 45;
const MAX_CAPTCHA_TOKEN_LENGTH = 4_096;

export class RecoveryCaptchaRejectedError extends Error {
  constructor() {
    super("Recovery CAPTCHA rejected");
    this.name = "RecoveryCaptchaRejectedError";
  }
}

function exactOrigin(value: string | undefined): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    if (
      !["http:", "https:"].includes(parsed.protocol) ||
      parsed.username ||
      parsed.password ||
      parsed.pathname !== "/" ||
      parsed.search ||
      parsed.hash
    ) {
      return null;
    }
    return parsed.origin;
  } catch {
    return null;
  }
}

function configuredRecoveryOrigin(
  value: string | undefined,
  environment: string | undefined,
): string | null {
  const origin = exactOrigin(value);
  if (!origin) return null;
  const protocol = new URL(origin).protocol;
  if (environment === "production") {
    return protocol === "https:" ? origin : null;
  }
  if (protocol === "http:" && !LOCAL_RECOVERY_ORIGINS.has(origin)) {
    return null;
  }
  return origin;
}

export function recoveryRedirectTarget({
  requestUrl,
  requestOrigin,
  configuredAppOrigin,
  environment,
}: {
  requestUrl: string;
  requestOrigin: string | null;
  configuredAppOrigin: string | undefined;
  environment: string | undefined;
}): string | null {
  const requestUrlOrigin = exactOrigin(new URL(requestUrl).origin);
  const browserOrigin =
    requestOrigin === null ? null : exactOrigin(requestOrigin ?? undefined);
  const configuredOrigin = configuredRecoveryOrigin(
    configuredAppOrigin,
    environment,
  );
  const isDevelopment = environment !== "production";
  const allowedOrigins = new Set<string>();
  if (configuredOrigin) allowedOrigins.add(configuredOrigin);
  if (isDevelopment) {
    LOCAL_RECOVERY_ORIGINS.forEach((origin) => allowedOrigins.add(origin));
  }
  if (
    requestOrigin !== null &&
    (!browserOrigin || !allowedOrigins.has(browserOrigin))
  ) {
    return null;
  }

  const redirectOrigin =
    configuredOrigin ??
    (requestUrlOrigin && LOCAL_RECOVERY_ORIGINS.has(requestUrlOrigin)
      ? requestUrlOrigin
      : null);
  return redirectOrigin ? `${redirectOrigin}/auth/recovery` : null;
}

export class RecoveryAttemptLimiter {
  private readonly attempts = new Map<string, number[]>();

  constructor(
    private readonly options: {
      limit: number;
      windowMs: number;
      now?: () => number;
      maxTrackedKeys?: number;
    },
  ) {}

  private compact(now: number): void {
    for (const [key, attempts] of this.attempts.entries()) {
      const recent = attempts.filter(
        (attempt) => now - attempt < this.options.windowMs,
      );
      if (recent.length === 0) {
        this.attempts.delete(key);
      } else if (recent.length !== attempts.length) {
        this.attempts.set(key, recent);
      }
    }
  }

  retryAfterMs(keys: string[]): number {
    const now = this.options.now?.() ?? Date.now();
    this.compact(now);
    const uniqueKeys = [...new Set(keys)];
    const recentByKey = uniqueKeys.map((key) => {
      const recent = this.attempts.get(key) ?? [];
      return { key, recent };
    });
    const retryAfter = recentByKey.reduce((longest, { recent }) => {
      if (recent.length < this.options.limit) return longest;
      return Math.max(longest, this.options.windowMs - (now - recent[0]));
    }, 0);
    if (retryAfter > 0) return retryAfter;
    const maxTrackedKeys = Math.max(
      1,
      Math.floor(this.options.maxTrackedKeys ?? MAX_TRACKED_RECOVERY_KEYS),
    );
    const unseenKeyCount = recentByKey.filter(
      ({ key }) => !this.attempts.has(key),
    ).length;
    if (this.attempts.size + unseenKeyCount > maxTrackedKeys) {
      return this.options.windowMs;
    }
    recentByKey.forEach(({ key, recent }) => {
      this.attempts.set(key, [...recent, now]);
    });
    return 0;
  }
}

type RecoveryRequestDependencies = {
  configuredAppOrigin: string | undefined;
  environment: string | undefined;
  trustedClientIpHeader?: string;
  limiter: RecoveryAttemptLimiter;
  globalLimiter: RecoveryAttemptLimiter;
  sendRecovery: (
    email: string,
    redirectTo: string,
    captchaToken: string,
  ) => Promise<void>;
};

const noStoreHeaders = {
  "Cache-Control": "no-store",
  "Content-Type": "application/json",
};

function jsonResponse(
  body: { accepted: boolean },
  status: number,
  headers?: Record<string, string>,
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...noStoreHeaders, ...headers },
  });
}

function clientAddress(
  request: Request,
  configuredHeader: string | undefined,
): string | null {
  const header = configuredHeader?.trim() || "CF-Connecting-IP";
  const value = request.headers.get(header)?.trim();
  if (!value) return "unknown";
  if (value.length > MAX_CLIENT_ADDRESS_LENGTH || isIP(value) === 0) {
    return null;
  }
  return value;
}

async function readRecoveryBody(
  request: Request,
): Promise<
  | { body: { email?: unknown; captcha_token?: unknown } }
  | { status: 400 | 413 | 415 }
> {
  const contentType = request.headers
    .get("content-type")
    ?.split(";", 1)[0]
    ?.trim()
    .toLowerCase();
  if (contentType !== "application/json") return { status: 415 };

  const declaredLength = request.headers.get("content-length");
  if (declaredLength) {
    const parsedLength = Number(declaredLength);
    if (!Number.isFinite(parsedLength) || parsedLength < 0) {
      return { status: 400 };
    }
    if (parsedLength > MAX_RECOVERY_BODY_BYTES) return { status: 413 };
  }
  if (!request.body) return { status: 400 };

  const reader = request.body.getReader();
  const decoder = new TextDecoder();
  let text = "";
  let byteLength = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      byteLength += value.byteLength;
      if (byteLength > MAX_RECOVERY_BODY_BYTES) {
        void reader.cancel().catch(() => undefined);
        return { status: 413 };
      }
      text += decoder.decode(value, { stream: true });
    }
    text += decoder.decode();
    const body: unknown = JSON.parse(text);
    if (typeof body !== "object" || body === null || Array.isArray(body)) {
      return { status: 400 };
    }
    return {
      body: body as { email?: unknown; captcha_token?: unknown },
    };
  } catch {
    return { status: 400 };
  }
}

function rateLimitResponse(retryAfterMs: number): Response {
  return jsonResponse({ accepted: false }, 429, {
    "Retry-After": String(Math.max(1, Math.ceil(retryAfterMs / 1_000))),
  });
}

export async function handleRecoveryRequest(
  request: Request,
  dependencies: RecoveryRequestDependencies,
): Promise<Response> {
  if (
    dependencies.environment === "production" &&
    !configuredRecoveryOrigin(
      dependencies.configuredAppOrigin,
      dependencies.environment,
    )
  ) {
    return jsonResponse({ accepted: false }, 503);
  }
  const requestOrigin = request.headers.get("origin");
  const redirectTo = recoveryRedirectTarget({
    requestUrl: request.url,
    requestOrigin,
    configuredAppOrigin: dependencies.configuredAppOrigin,
    environment: dependencies.environment,
  });
  if (!redirectTo) {
    return jsonResponse(
      { accepted: false },
      requestOrigin !== null ? 403 : 503,
    );
  }

  const bodyResult = await readRecoveryBody(request);
  if ("status" in bodyResult) {
    return jsonResponse({ accepted: false }, bodyResult.status);
  }
  const { body } = bodyResult;
  const address = clientAddress(request, dependencies.trustedClientIpHeader);
  if (!address) return jsonResponse({ accepted: false }, 400);

  const email =
    typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  if (
    email.length > MAX_RECOVERY_EMAIL_LENGTH ||
    !/^\S+@\S+\.\S+$/.test(email)
  ) {
    return jsonResponse({ accepted: true }, 202);
  }
  const captchaToken =
    typeof body.captcha_token === "string" ? body.captcha_token.trim() : "";
  if (!captchaToken || captchaToken.length > MAX_CAPTCHA_TOKEN_LENGTH) {
    return jsonResponse({ accepted: false }, 400);
  }

  const retryAfterMs = dependencies.limiter.retryAfterMs([
    `email:${email}`,
    `ip:${address}`,
  ]);
  if (retryAfterMs > 0) return rateLimitResponse(retryAfterMs);
  const globalRetryAfterMs = dependencies.globalLimiter.retryAfterMs(["global"]);
  if (globalRetryAfterMs > 0) return rateLimitResponse(globalRetryAfterMs);

  try {
    await dependencies.sendRecovery(email, redirectTo, captchaToken);
  } catch (error) {
    if (error instanceof RecoveryCaptchaRejectedError) {
      return jsonResponse({ accepted: false }, 502);
    }
    return jsonResponse({ accepted: true }, 202);
  }
  return jsonResponse({ accepted: true }, 202);
}
