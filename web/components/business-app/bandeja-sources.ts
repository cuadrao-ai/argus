import { classifyFailure, loadRecovery, referenceCode } from "@/lib/failure-screen";

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

/** The Bandeja's lists besides its receipts. */
export type BandejaSource = "notes" | "emails";
