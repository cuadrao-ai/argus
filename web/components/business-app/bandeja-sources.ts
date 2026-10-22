import { classifyFailure, loadRecovery, referenceCode } from "@/lib/failure-screen";
import { UNKNOWN_VALUE } from "./business-format";
import { inboxCount, problemCount, type CountRecords } from "./inbox-count";

/**
 * Why a list did not load. Offline is the connection banner's to say, so the
 * screen stays quiet and asks again when the connection is back; a refusal
 * for good is said inline with no Reintentar; any other failure is said
 * inline with Reintentar. A server failure carries its reference.
 */
export type LoadFailure = Readonly<{ offline: boolean; refused: boolean; reference: string | null }>;

export function loadFailure(error: unknown): LoadFailure {
  const recovery = loadRecovery(error);
  const kind = classifyFailure(error);
  return { offline: recovery === "offline", refused: recovery === "refused", reference: kind === "server" || kind === "unavailable" ? referenceCode(error) : null };
}

/** Where one of the lists a screen is built from stands. A list that failed is never an empty one. */
export type SourceLoad = { state: "loading" } | { state: "ready" } | { state: "failed"; failure: LoadFailure };

export function sourceLoad(items: readonly unknown[] | null | undefined, failure: LoadFailure | null | undefined): SourceLoad {
  if (failure) return { state: "failed", failure };
  return items == null ? { state: "loading" } : { state: "ready" };
}

/** The Bandeja's lists besides its receipts: a receipts failure is the whole screen's, these are one line. */
export type BandejaSource = "notes" | "emails";

export type BandejaLoads = Readonly<{ receipts: SourceLoad; notes: SourceLoad; emails: SourceLoad }>;

/**
 * The numbers the Bandeja's segments show. None while the receipts load; "-"
 * while any list is down, since a server number beside a list that failed
 * contradicts it; otherwise the server's number, or "-" when it sent none.
 */
export function bandejaCounts(loads: BandejaLoads, records: CountRecords): { review: number | string | undefined; problem: number | string | undefined } {
  if (loads.receipts.state !== "ready") return { review: undefined, problem: undefined };
  if (Object.values(loads).some((load) => load.state === "failed")) return { review: UNKNOWN_VALUE, problem: UNKNOWN_VALUE };
  return { review: inboxCount(records) ?? UNKNOWN_VALUE, problem: problemCount(records) ?? UNKNOWN_VALUE };
}
