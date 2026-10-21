import { classifyFailure, referenceCode } from "@/lib/failure-screen";

/**
 * Why a list did not load. Offline is the connection banner's to say, so the
 * screen stays quiet and asks again when the connection is back; any other
 * failure is said inline with Reintentar, a server one with its reference.
 */
export type LoadFailure = Readonly<{ offline: boolean; reference: string | null }>;

export function loadFailure(error: unknown): LoadFailure {
  const offline = typeof navigator !== "undefined" && navigator.onLine === false;
  const kind = classifyFailure(error);
  return { offline, reference: kind === "server" || kind === "unavailable" ? referenceCode(error) : null };
}

/** Where one of the lists a screen is built from stands. A list that failed is never an empty one. */
export type SourceLoad = { state: "loading" } | { state: "ready" } | { state: "failed"; failure: LoadFailure };

export function sourceLoad(items: readonly unknown[] | null | undefined, failure: LoadFailure | null | undefined): SourceLoad {
  if (failure) return { state: "failed", failure };
  return items == null ? { state: "loading" } : { state: "ready" };
}

/** The Bandeja's lists besides its receipts: a receipts failure is the whole screen's, these are one line. */
export type BandejaSource = "notes" | "emails";
