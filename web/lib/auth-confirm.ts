const CONFIRM_TYPES = ["email", "signup", "magiclink", "recovery", "invite", "email_change"] as const;

export type AuthConfirmType = (typeof CONFIRM_TYPES)[number];

const TOKEN_HASH = /^(?:pkce_)?[a-f0-9]{32,128}$/;

export type LinkedAuthAction = "recovery" | "email_change";

export const AUTH_TEMPLATE_ORIGIN = "{{ .SiteURL }}";
export const AUTH_TEMPLATE_HASH = "{{ .TokenHash }}";

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
) => Promise<{ error: unknown }>;

export async function confirmAuthGet(request: Request, verify: AuthConfirmVerifier): Promise<Response> {
  const requestUrl = new URL(request.url);
  const decision = resolveAuthConfirm(requestUrl);
  const failure = new URL("/auth/confirm/error", requestUrl.origin);
  if (!decision.ok) return redirect(failure);
  try {
    const result = await verify({ token_hash: decision.tokenHash, type: decision.type });
    if (result.error) return redirect(failure);
  } catch {
    return redirect(failure);
  }
  return redirect(new URL(decision.next, requestUrl.origin));
}

function redirect(location: URL): Response {
  return new Response(null, {
    status: 303,
    headers: {
      Location: location.toString(),
      "Cache-Control": "no-store",
    },
  });
}
