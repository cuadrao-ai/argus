import { authLoginPathFromSearch } from "./landing-intent";

export type BusinessOnlyDecision =
  | { action: "next" }
  | { action: "redirect"; location: string };

// Paths the switch must leave alone: auth callbacks, account deletion and its
// API, legal pages, health, receipts, the Business shell, and static assets.
const STAY_PREFIXES = [
  "/auth",
  "/account",
  "/api",
  "/biz",
  "/r",
  "/_next",
  "/locales",
  "/icons",
  "/brand",
  "/email",
  "/fonts",
  "/dev",
] as const;

const STAY_EXACT = new Set(["/privacy", "/terms", "/health"]);

// Root is the guest chat entry. /chat is the guest-session landing and every
// legacy chat route under it. /login and /signup are the old consumer doors.
const CONSUMER_PREFIXES = ["/chat", "/login", "/signup"] as const;

function normalizePath(pathname: string): string {
  if (pathname.length > 1 && pathname.endsWith("/")) {
    return pathname.slice(0, -1);
  }
  return pathname || "/";
}

function lastSegmentHasExtension(pathname: string): boolean {
  const segment = pathname.split("/").pop() ?? "";
  return segment.includes(".");
}

function authMode(search: string): string | null {
  const params = new URLSearchParams(
    search.startsWith("?") ? search.slice(1) : search,
  );
  return params.get("auth");
}

export function decideBusinessOnlyWeb(input: {
  enabled: boolean;
  pathname: string;
  search: string;
}): BusinessOnlyDecision {
  if (!input.enabled) return { action: "next" };

  const pathname = normalizePath(input.pathname);
  if (lastSegmentHasExtension(pathname)) return { action: "next" };
  if (STAY_EXACT.has(pathname)) return { action: "next" };
  if (
    STAY_PREFIXES.some(
      (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
    )
  ) {
    return { action: "next" };
  }

  const consumer =
    pathname === "/" ||
    CONSUMER_PREFIXES.some(
      (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
    );
  if (!consumer) return { action: "next" };

  // Business sign-in and sign-up stay on this page so the age gate still has
  // a host. Request-access and the bare guest entry do not.
  if (pathname === "/") {
    const mode = authMode(input.search);
    if (mode === "login" || mode === "signup") return { action: "next" };
  }

  return {
    action: "redirect",
    location: authLoginPathFromSearch(input.search),
  };
}
