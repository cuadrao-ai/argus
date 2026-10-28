import { referenceCode } from "./failure-screen";
import { recoveryProof, recoveryProofLocation, sessionIdFromAccessToken } from "./recovery-proof";

const CONFIRM_TYPES = ["email", "signup", "magiclink", "recovery", "invite", "email_change"] as const;

export type AuthConfirmType = (typeof CONFIRM_TYPES)[number];

const TOKEN_HASH = /^(?:pkce_)?[a-f0-9]{32,128}$/;

export type LinkedAuthAction = "recovery" | "email_change" | "invite";

export const AUTH_TEMPLATE_ORIGIN = "{{ .SiteURL }}";
export const AUTH_TEMPLATE_HASH = "{{ .TokenHash }}";
export const AUTH_TEMPLATE_OTP = "{{ .Token }}";
export const AUTH_TEMPLATE_EMAIL = "{{ .Email }}";

export function authConfirmHref(appOrigin: string, tokenHash: string, type: string, nextPath: string): string {
  if (appOrigin === AUTH_TEMPLATE_ORIGIN) {
    if (tokenHash !== AUTH_TEMPLATE_HASH || !/^[a-z_]+$/.test(type) || !/^\/[A-Za-z0-9\-._~/?]*$/.test(nextPath)) {
      throw new Error("Invalid Auth origin");
    }
    return `${appOrigin}/auth/confirm?token_hash=${tokenHash}&type=${type}&next=${nextPath}`;
  }
  const url = new URL("/auth/confirm", appOrigin);
  if (url.protocol !== "https:" || url.username || url.password || url.pathname !== "/auth/confirm") {
    throw new Error("Invalid Auth origin");
  }
  url.searchParams.set("token_hash", tokenHash);
  url.searchParams.set("type", type);
  url.searchParams.set("next", nextPath);
  return url.href;
}

export function internalNextPath(value: string, origin: string): string | null {
  if (value.length === 0 || value.length > 2048) return null;
  if (value.startsWith("//") || /[\s\\]/.test(value)) return null;
  let url: URL;
  try {
    url = new URL(value, origin);
  } catch {
    return null;
  }
  if (url.origin !== origin || url.username || url.password) return null;
  if (url.protocol !== "https:" && url.protocol !== "http:") return null;
  const path = `${url.pathname}${url.search}${url.hash}`;
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("\\")) return null;
  return path;
}

export function confirmLinkNext(action: LinkedAuthAction, redirectTo: string, appOrigin: string): string {
  const fallback = action === "recovery" ? "/auth/recovery" : "/";
  if (!redirectTo) return fallback;
  return internalNextPath(redirectTo, appOrigin) ?? fallback;
}

export type ConfirmDecision =
  | { ok: true; tokenHash: string; type: AuthConfirmType; next: string }
  | { ok: false };

function isConfirmType(value: string): value is AuthConfirmType {
  return (CONFIRM_TYPES as readonly string[]).includes(value);
}

export function resolveAuthConfirm(requestUrl: URL): ConfirmDecision {
  const tokenHash = requestUrl.searchParams.get("token_hash") ?? "";
  const type = requestUrl.searchParams.get("type") ?? "";
  if (!TOKEN_HASH.test(tokenHash) || !isConfirmType(type)) return { ok: false };
  const nextParam = requestUrl.searchParams.get("next");
  const next = nextParam === null
    ? (type === "recovery" ? "/auth/recovery" : "/")
    : internalNextPath(nextParam, requestUrl.origin);
  if (!next) return { ok: false };
  return { ok: true, tokenHash, type, next };
}

export type AuthConfirmVerifier = (
  input: { token_hash: string; type: AuthConfirmType },
) => Promise<{
  error: unknown;
  data?: { session?: { access_token: string; user: { id: string } } | null } | null;
}>;

const ERROR_TOKEN = /^[A-Za-z0-9_]{1,64}$/;

/** Our own refusal codes; a provider refusal keeps the provider's code (otp_expired and the like). */
export const CONFIRM_MALFORMED_LINK = "malformed_link";
export const CONFIRM_VERIFY_FAILED = "verify_failed";

function errorToken(value: string | null): string | null {
  return value && ERROR_TOKEN.test(value) ? value : null;
}

function providerCode(error: unknown): string | null {
  if (!error || typeof error !== "object" || !("code" in error)) return null;
  return errorToken(typeof error.code === "string" ? error.code : null);
}

export function confirmErrorLocation(requestUrl: URL, type: string | null, code: string, reference: string): string {
  const params = new URLSearchParams();
  params.set("error_code", code);
  const named = errorToken(type ?? requestUrl.searchParams.get("type"));
  if (named) params.set("type", named);
  params.set("ref", reference);
  return `/auth/confirm/error?${params.toString()}`;
}

export type ConfirmRefusal = { reference: string; type: string | null; code: string };

export async function confirmAuthGet(
  request: Request,
  verify: AuthConfirmVerifier,
  report: (refusal: ConfirmRefusal) => void = (refusal) => console.warn("auth confirm refused", refusal),
): Promise<Response> {
  const requestUrl = new URL(request.url);
  const decision = resolveAuthConfirm(requestUrl);
  const refuse = (type: string | null, code: string) => {
    const reference = referenceCode(null);
    report({ reference, type, code });
    return redirect(confirmErrorLocation(requestUrl, type, code, reference));
  };
  if (!decision.ok) return refuse(null, CONFIRM_MALFORMED_LINK);
  let proof: string | null = null;
  try {
    const result = await verify({ token_hash: decision.tokenHash, type: decision.type });
    if (result.error) return refuse(decision.type, providerCode(result.error) ?? CONFIRM_VERIFY_FAILED);
    if (decision.type === "recovery") {
      const session = result.data?.session;
      const sessionId = session ? sessionIdFromAccessToken(session.access_token) : null;
      if (!session || !sessionId) return refuse(decision.type, CONFIRM_VERIFY_FAILED);
      proof = await recoveryProof(session.user.id, sessionId);
    }
  } catch {
    return refuse(decision.type, CONFIRM_VERIFY_FAILED);
  }
  return redirect(proof ? recoveryProofLocation(decision.next, proof) : decision.next);
}

function redirect(path: string): Response {
  return new Response(null, {
    status: 303,
    headers: {
      Location: path,
      "Cache-Control": "no-store",
    },
  });
}
