export const AUTH_LINK_FLOWS = ["recovery", "email_change", "invite"] as const;

export type AuthLinkFlow = (typeof AUTH_LINK_FLOWS)[number];

export type AuthLinkErrorView =
  | {
      kind: "request";
      flow: "recovery" | "email_change";
      href: string;
      email: string | null;
    }
  | { kind: "invite" };

const REQUEST_PATH = {
  recovery: "/auth/forgot-password",
  email_change: "/account/security",
} as const;

export function prefilledEmail(value: string | null | undefined): string {
  return readableEmail(value) ?? "";
}

export function confirmErrorView(search: string): AuthLinkErrorView {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const type = params.get("type");
  const probe = new URLSearchParams(params);
  if (!isUsedOrExpired(probe)) probe.set("error", "access_denied");
  if (type !== "invite" && type !== "email_change" && type !== "recovery") probe.set("type", "recovery");
  return mapAuthLinkError({ search: probe.toString(), hash: "", pathname: "/" })
    ?? { kind: "request", flow: "recovery", email: null, href: requestHref("recovery", null) };
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
  if (flow === "invite") return { kind: "invite" };
  const email = readableEmail(params.get("email")) ?? readableEmail(input.knownEmail);
  return { kind: "request", flow, email, href: requestHref(flow, email) };
}

export function authLinkErrorRedirect(input: {
  origin: string;
  pathname: string;
  searchParams: URLSearchParams;
}): URL | null {
  if (input.pathname === "/auth/link-error") return null;
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
