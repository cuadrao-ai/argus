export const AUTH_LINK_FLOWS = ["recovery", "email_change", "invite"] as const;

export type AuthLinkFlow = (typeof AUTH_LINK_FLOWS)[number];

/** What was refused: a used or expired link, a link missing a part, or a link the provider would not verify. */
export type AuthLinkProblem = "expired" | "malformed" | "rejected";

export type AuthLinkErrorView = { problem: AuthLinkProblem } & (
  | {
      kind: "request";
      flow: "recovery" | "email_change";
      href: string;
      email: string | null;
    }
  | { kind: "invite" }
);

const REQUEST_PATH = {
  recovery: "/auth/forgot-password",
  email_change: "/account/security",
} as const;

const REFERENCE = /^[A-Za-z0-9_-]{4,64}$/;

export function prefilledEmail(value: string | null | undefined): string {
  return readableEmail(value) ?? "";
}

/** The confirm route's own refusal, by the error_code it set; see auth-confirm.ts. */
export function confirmErrorView(search: string): AuthLinkErrorView {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const code = params.get("error_code");
  const problem: AuthLinkProblem = isUsedOrExpired(params) ? "expired" : code === "malformed_link" ? "malformed" : "rejected";
  const named = params.get("type");
  const flow = isFlow(named) ? named : "recovery";
  if (flow === "invite") return { problem, kind: "invite" };
  return { problem, kind: "request", flow, email: null, href: requestHref(flow, null) };
}

/** The reference the confirm route logged with its refusal, when the URL still carries it. */
export function confirmReference(search: string): string | null {
  const value = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search).get("ref");
  return value && REFERENCE.test(value) ? value : null;
}

/** The shared screen itself, and the confirm route's error page, which keeps the reference the route logged. */
export function rendersOwnLinkError(pathname: string): boolean {
  return pathname === "/auth/link-error" || pathname === "/auth/confirm/error";
}

export function notFoundHref(signedIn: boolean, home: string): string {
  return signedIn ? home : "/?auth=login";
}

export function mapAuthLinkError(input: {
  search: string;
  hash: string;
  pathname: string;
  knownEmail?: string | null;
}): AuthLinkErrorView | null {
  const params = mergedParams(input.search, input.hash);
  if (!isUsedOrExpired(params)) return null;
  const flow = flowFrom(params, input.pathname);
  if (!flow) return null;
  if (flow === "invite") return { problem: "expired", kind: "invite" };
  const email = readableEmail(params.get("email")) ?? readableEmail(input.knownEmail);
  return { problem: "expired", kind: "request", flow, email, href: requestHref(flow, email) };
}

export function authLinkErrorRedirect(input: {
  origin: string;
  pathname: string;
  searchParams: URLSearchParams;
}): URL | null {
  if (rendersOwnLinkError(input.pathname)) return null;
  const view = mapAuthLinkError({
    search: input.searchParams.toString(),
    hash: "",
    pathname: input.pathname,
  });
  if (!view) return null;
  const next = new URL("/auth/link-error", input.origin);
  for (const key of ["error", "error_code", "type", "email"]) {
    const value = input.searchParams.get(key);
    if (!value) continue;
    if (key === "type" && !isFlow(value)) continue;
    next.searchParams.set(key, value);
  }
  if (!next.searchParams.get("type")) {
    next.searchParams.set("type", view.kind === "invite" ? "invite" : view.flow);
  }
  return next;
}

export function requestHrefFor(
  flow: "recovery" | "email_change",
  email: string | null,
): string {
  return requestHref(flow, readableEmail(email));
}

function requestHref(flow: "recovery" | "email_change", email: string | null): string {
  const path = REQUEST_PATH[flow];
  if (!email) return path;
  return `${path}?${new URLSearchParams({ email }).toString()}`;
}

function mergedParams(search: string, hash: string): URLSearchParams {
  const query = new URLSearchParams(strip(search, "?"));
  const fragment = new URLSearchParams(strip(hash, "#"));
  for (const [key, value] of fragment) {
    if (!query.has(key)) query.set(key, value);
  }
  return query;
}

function strip(value: string, mark: string): string {
  return value.startsWith(mark) ? value.slice(1) : value;
}

function isUsedOrExpired(params: URLSearchParams): boolean {
  return params.get("error") === "access_denied" || params.get("error_code") === "otp_expired";
}

function flowFrom(params: URLSearchParams, pathname: string): AuthLinkFlow | null {
  const named = params.get("type") ?? params.get("flow");
  if (isFlow(named)) return named;
  if (pathname === "/auth/recovery" || pathname.startsWith("/auth/recovery/")) return "recovery";
  return null;
}

function isFlow(value: string | null): value is AuthLinkFlow {
  return AUTH_LINK_FLOWS.includes(value as AuthLinkFlow);
}

function readableEmail(value: string | null | undefined): string | null {
  if (!value) return null;
  const email = value.trim();
  if (email.length < 3 || email.length > 254) return null;
  if (/\s/.test(email) || email.includes("/") || email.includes("?") || email.includes("#") || email.includes("\\")) return null;
  const at = email.indexOf("@");
  if (at <= 0 || email.indexOf("@", at + 1) !== -1 || at === email.length - 1) return null;
  return email;
}
